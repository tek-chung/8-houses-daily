"""One place to look: a status issue that opens, updates and closes itself.

Every refresh and every deploy finishes by calling this. When something needs you,
it opens a GitHub issue (GitHub emails you), keeps it current while the problem
lasts, comments when things get worse or new decisions arrive, and closes it
when there is nothing left to do. No open status issue means nothing needs you.

Why: from 8 to 16 October 2026 the refresh and the deploy both failed every time,
and the only sign was a red cross on a page nobody had reason to open. The paper
went eight days without a new edition, with nobody told.

    python pipeline/health.py refresh --job-status success --run-url URL --repo-url URL
    python pipeline/health.py deploy  --job-status failure --run-url URL --repo-url URL \
                                      --cloudflare false
    ...add --print to show the issue instead of writing it to GitHub.

Uses the gh CLI preinstalled on GitHub's runners. Prints nothing secret: the
review report it reads never contains keys.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import SITE_BANNER_AFTER_DAYS, STATE

LEVELS = {"ok": 0, "attention": 1, "broken": 2}
LABELS = {"refresh": "status: refresh", "deploy": "status: deploy"}
TITLES = {
    ("refresh", "broken"): "Refresh is broken — needs you",
    ("refresh", "attention"): "Refresh: something is waiting for you",
    ("deploy", "broken"): "Deploy is failing — readers are seeing an old edition",
    ("deploy", "attention"): "Deploy: GitHub cannot publish the site yet",
}
# Days before the 60-day "publication suspended" banner at which to warn.
BANNER_WARNING_DAYS = 15
_MARKER = re.compile(r"<!-- health level=(\w+) waiting=([\w,-]*) -->")


@dataclass
class Assessment:
    key: str
    level: str
    headline: str
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)


def _name(r):
    return f"**{r.get('name', r.get('org_id'))}** (`{r.get('org_id')}`)"


def _short(reasons, n=160):
    text = "; ".join(dict.fromkeys(x for x in reasons if x))
    return text if len(text) <= n else text[:n - 1] + "…"


def ai_advice(review: dict) -> list[str]:
    """What to do about an AI failure, from the provider's own error categories."""
    if not review.get("ai_configured"):
        return ["No AI provider is enabled, so changed pages could not be read. Either "
                "the `GEMINI_API_KEY` repository secret is missing, or the "
                "`AI_GEMINI_FREE_TIER_CONFIRMED` repository variable is not `true`. "
                "Settings → Secrets and variables → Actions. See docs/ai-setup.md."]
    diags = review.get("ai_diagnostics") or []
    statuses = {d.get("status") for d in diags}
    reasons = {d.get("reason") for d in diags}
    out = []
    if "auth" in reasons:
        out.append("Gemini refused the API key (HTTP 401/403). In Google AI Studio, make "
                   "a new key in the same Free Tier project and replace the "
                   "`GEMINI_API_KEY` secret (Settings → Secrets and variables → Actions).")
    if 400 in statuses:
        out.append("Gemini rejected the request (HTTP 400). An invalid or deleted key also "
                   "gives 400, so check the key first. If the key is fine, the message in "
                   "the run summary names the part of the request it refused; locally, "
                   "`py pipeline\\ai.py schema-check` pinpoints it.")
    if 404 in statuses or "model_unavailable" in reasons:
        out.append("The configured Gemini models are no longer available. Locally, run "
                   "`py pipeline\\ai.py models`, then set the `AI_GEMINI_MODELS` repository "
                   "variable to two current Flash-Lite models, comma-separated.")
    if "rate_limited" in reasons:
        out.append("Gemini's free daily quota was used up. This normally clears by itself "
                   "and the pages are retried next week. Only if it happens two weeks "
                   "running: something else is using the same Google project.")
    if reasons & {"network", "provider_unavailable"}:
        out.append("Gemini could not be reached or was failing (HTTP 5xx). Usually "
                   "temporary; it is retried next week.")
    held = [d.get("message") or "" for d in diags if d.get("reason") == "budget_exhausted"]
    if any(m and "daily AI allowance exhausted" not in m for m in held):
        out.append("The run could not record its AI allowance in git before calling "
                   "Gemini, so it sent nothing. Usually someone pushed to `main` during "
                   "the run: start it again (Actions → Weekly freshness check → Run "
                   "workflow). If it repeats, check Settings → Actions → General → "
                   "Workflow permissions is “Read and write”.")
    if not out:
        out.append("Every AI request failed. The provider diagnostics in the run summary "
                   "give the category and HTTP status.")
    return out


def assess_refresh(review: dict | None, job_status: str) -> Assessment:
    if review is None:
        if job_status == "success":
            return Assessment("refresh", "ok", "Nothing to report.")
        return Assessment("refresh", "broken",
            "The refresh stopped before it checked any charity page.", [
            ("What to do", [
                "Open the run (link below). The first red step says why.",
                "If it is **Test the gate, content isolation and site build**, a safety "
                "test failed, so nothing was checked or published. Locally: "
                "`$env:PYTHONPATH = \"pipeline\"; py -m pytest pipeline/ site/ -q` shows "
                "which. A record you edited or approved by hand is the usual cause, and "
                "the failure names it.",
                "If it is **Run the check**, the run log in the `freshness-run` "
                "artifact ends with the error and the charity it was checking."])])

    results = review.get("results", [])
    by = lambda *outcomes: [r for r in results if r.get("outcome") in outcomes]
    sections, level, headline = [], "ok", "Nothing needs you."

    if review.get("ai_broken"):
        level, headline = "broken", "The AI check is not working, so changed pages are not being read."
        sections.append(("What to do", ai_advice(review)))
    elif job_status != "success":
        level, headline = "broken", "A step of the refresh failed after the pages were checked."
        sections.append(("What to do", [
            "Open the run (link below); the red step says what failed. If it was a "
            "push, someone changed `main` during the run: start the workflow again "
            "(Actions → Weekly freshness check → Run workflow)."]))

    banner = review.get("site_banner")
    median = review.get("median_days_since_check")
    if banner:
        level = max(level, "attention", key=LEVELS.get)
        headline = headline if level == "broken" else \
            "The paper is printing “publication suspended” on every page."
        sections.append(("Freshness", [
            f"Half the charities have not been confirmed for {median} days or more. The "
            "banner lifts by itself as checks succeed; the decisions below are the way "
            "to speed that up."]))
    elif median is not None and median >= SITE_BANNER_AFTER_DAYS - BANNER_WARNING_DAYS:
        level = max(level, "attention", key=LEVELS.get)
        if level != "broken":
            headline = (f"Listings are going stale: median {median} days since a successful "
                        f"check. At {SITE_BANNER_AFTER_DAYS} the whole paper says "
                        "“publication suspended”.")
        sections.append(("Freshness", [
            f"Median {median} days since a successful check (the banner appears at "
            f"{SITE_BANNER_AFTER_DAYS}). Deciding the proposals below resets the charities "
            "concerned."]))

    waiting = by("review_required")
    if waiting:
        level = max(level, "attention", key=LEVELS.get)
        if level == "attention" and not banner and headline == "Nothing needs you.":
            headline = (f"{len(waiting)} charit{'y has' if len(waiting) == 1 else 'ies have'} "
                        "changes waiting for your decision.")
        sections.append(("Decisions waiting", [
            "Nothing is published until you decide; meanwhile those notices stop "
            "asserting screening and status after 21 days, so the paper stays honest.",
            "Read the changes in the open **Freshness review** pull request, and the "
            "charity's own page. Then **Actions → Review a proposal → Run workflow** with "
            "the charity id and approve or reject.", ""] +
            [f"- {_name(r)}: {r.get('roles_before')} → {r.get('roles_after')} roles — "
             f"{_short(r.get('reasons', []))}" for r in waiting]))

    broken_boards = by("board_failed")
    if broken_boards:
        level = max(level, "attention", key=LEVELS.get)
        if headline == "Nothing needs you.":
            headline = "A volunteering platform could not be read."
        sections.append(("Platform boards that could not be read", [
            "Their roles are left exactly as they were and nothing was confirmed. It "
            "usually clears by itself; if the same board is here two weeks running, open "
            "it in a browser and check the address in the charity's `board` setting.", ""] +
            [f"- {_name(r)}: {_short(r.get('reasons', []))}" for r in broken_boards]))

    gaps = [r for r in results if r.get("unread_platforms")]
    if gaps:
        level = max(level, "attention", key=LEVELS.get)
        if headline == "Nothing needs you.":
            headline = "Some charities keep roles on platforms the check cannot read."
        sections.append(("Roles we cannot see", [
            "These charities link to a volunteering platform that the check does not read, "
            "so any roles there are missing from the listing. Check each by hand, and "
            "either add a `board` reader for it or list the host under "
            "`platforms_acknowledged` in `data/orgs/<id>.json` once you have looked.", ""] +
            [f"- {_name(r)}: {', '.join(r['unread_platforms'])}" for r in gaps]))

    feed_gaps = [r for r in results if (r.get("feed_gaps") or {}).get("missing")
                 or (r.get("feed_gaps") or {}).get("gone")]
    if feed_gaps:
        level = max(level, "attention", key=LEVELS.get)
        if headline == "Nothing needs you.":
            headline = "A charity's own role list differs from our listing."
        lines = ["The charity's own role feed and our listing disagree. Open the role "
                 "page, then add the role (or retire it) in `data/orgs/<id>.json`.", ""]
        for r in feed_gaps:
            gap = r["feed_gaps"]
            if gap.get("missing"):
                lines.append(f"- {_name(r)} lists, and we do not hold: "
                             + "; ".join(gap["missing"]))
            if gap.get("gone"):
                lines.append(f"- {_name(r)}: held but no longer in its feed: "
                             + "; ".join(gap["gone"]))
        sections.append(("Roles the charity lists that we do not", lines))

    feed_broken = [r for r in results if r.get("feed_error")]
    if feed_broken:
        sections.append(("Role feeds that could not be read", [
            "The completeness check was skipped for these; nothing was changed.", ""] +
            [f"- {_name(r)}: {r['feed_error']}" for r in feed_broken]))

    dead = by("source_failed")
    if dead:
        level = max(level, "attention", key=LEVELS.get)
        if headline == "Nothing needs you.":
            headline = "Some charity links are failing."
        sections.append(("Links that fail", [
            "These pages failed twice or more, in ways a browser would also hit. Open each "
            "one. If the charity moved its volunteering page, put the new address in "
            "`volunteer_url` in `data/orgs/<id>.json`. If the problem is on their side "
            "(an expired certificate), nothing to do; their notices already show as not "
            "checked recently.", ""] +
            [f"- {_name(r)}: {_short(r.get('reasons', []))}" for r in dead]))

    info = []
    incomplete = by("extraction_failed", "invalid_extraction", "ai_unavailable")
    if incomplete and not review.get("ai_broken"):
        info.append("Not readable by the AI this week, retried next week (nothing to do "
                    "unless the same charity is here three weeks running):")
        info += [f"- {_name(r)}: {_short(r.get('reasons', []), 120)}" for r in incomplete]
    unread = [r for r in results if r.get("additions_unread")]
    if unread:
        info.append("Listing confirmed, but other roles the page mentions could not be "
                    "read this week (retried next week):")
        info += [f"- {_name(r)}: {', '.join(r.get('other_roles', []))[:120]}" for r in unread]
    refused = by("source_refused")
    if refused:
        info.append(f"{len(refused)} site(s) turn away automated checks from GitHub's "
                    "servers: " + ", ".join(r.get("name", r["org_id"]) for r in refused)
                    + ". Their notices show as not checked recently. Nothing to do.")
    deferred = by("ai_deferred")
    if deferred:
        info.append(f"{len(deferred)} page(s) waited for next week's AI allowance. "
                    "Nothing to do.")
    counts = (f"This run: {review.get('confirmed_count', 0)} confirmed, "
              f"{review.get('unchanged_count', 0)} unchanged, "
              f"{review.get('published_count', 0)} updated by themselves, "
              f"{len(waiting)} waiting for you.")
    sections.append(("For information", [counts] + info))
    return Assessment("refresh", level, headline, sections, sorted(r["org_id"] for r in waiting))


def assess_deploy(job_status: str, cloudflare: bool) -> Assessment:
    if job_status != "success":
        return Assessment("deploy", "broken",
            "The site did not build or pass its checks, so nothing new reached readers.", [
            ("What to do", [
                "Open the run (link below). If **Build** failed, the log lists the "
                "records the build refused and why. Fix or revert that record in "
                "`data/orgs/`.",
                "If **Validate the site** failed, run the tests locally: "
                "`$env:PYTHONPATH = \"pipeline\"; py -m pytest site/ -q`.",
                "The live site keeps its last good edition meanwhile; it does not break."])])
    if not cloudflare:
        return Assessment("deploy", "attention",
            "Builds pass, but GitHub has no Cloudflare credentials, so the live site "
            "changes only when you deploy it by hand.", [
            ("What to do, once", [
                "1. Token: open https://dash.cloudflare.com/?to=/:account/api-tokens "
                "(Account API tokens) → **Create Token** → under *Permission policies* "
                "open **Custom** → **Edit Cloudflare Workers** → limit it to your one "
                "account → create it and copy the token. Cloudflare shows it only once.",
                "2. Account ID: Cloudflare dashboard → **Workers & Pages** → *Account "
                "Details* → copy **Account ID** (or press Ctrl+K and search "
                "“Copy account ID”).",
                "3. This repository → **Settings** → **Secrets and variables** → "
                "**Actions** → **New repository secret**, twice: `CLOUDFLARE_API_TOKEN` "
                "= the token, `CLOUDFLARE_ACCOUNT_ID` = the account ID.",
                "4. Actions → Build and deploy → Run workflow. This issue closes itself "
                "when the deploy succeeds.",
                "Until then, every approval and every daily rebuild (which keeps the "
                "masthead date and the freshness rules current) waits for a manual "
                "`npx wrangler deploy`."])])
    return Assessment("deploy", "ok", "Deployed.")


def render(a: Assessment, run_url: str, repo_url: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = [f"**{a.headline}**", ""]
    for heading, body in a.sections:
        if body:
            lines += [f"### {heading}", ""]
            for line in body:
                # Markdown runs adjacent lines together; list items stay tight.
                lines += [line] if line.startswith("- ") or not line else [line, ""]
            lines.append("")
    lines += ["---",
              f"Updated by [this {a.key} run]({run_url}) at "
              f"{now.strftime('%H:%M UTC on %d %b %Y').lstrip('0')}. This issue opens, "
              "updates and closes itself; you never need to close it. What each message "
              f"means: [docs/operations.md]({repo_url}/blob/main/docs/operations.md).",
              f"<!-- health level={a.level} waiting={','.join(a.waiting)} -->"]
    return "\n".join(lines) + "\n"


def _gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


def sync(a: Assessment, run_url: str, repo_url: str, gh=_gh, keep_broken=False) -> str:
    """Make GitHub's status issue match the assessment. Returns what was done.

    keep_broken: leave a "broken" issue alone. A review decision knows what is
    still waiting, but not whether the refresh itself has been fixed.
    """
    label = LABELS[a.key]
    found = json.loads(gh(["issue", "list", "--label", label, "--state", "open",
                           "--json", "number,body", "--limit", "1"]) or "[]")
    issue = found[0] if found else None
    if keep_broken and issue is not None:
        m = _MARKER.search(issue.get("body") or "")
        if m and m.group(1) == "broken":
            return "left broken"
    if a.level == "ok":
        if issue is None:
            return "nothing"
        gh(["issue", "comment", str(issue["number"]), "--body",
            f"All clear as of [this run]({run_url}). Closing."])
        gh(["issue", "close", str(issue["number"])])
        return "closed"

    body = render(a, run_url, repo_url)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
    title = TITLES[(a.key, a.level)]
    try:
        if issue is None:
            try:
                gh(["label", "create", label, "--color", "B60205", "--force",
                    "--description", "Opened and closed automatically by the pipeline"])
            except subprocess.CalledProcessError:
                pass   # the label exists already, or labels are restricted
            gh(["issue", "create", "--title", title, "--label", label, "--body-file", f.name])
            return "opened"
        number = str(issue["number"])
        m = _MARKER.search(issue.get("body") or "")
        before = m.group(1) if m else "attention"
        seen = set(filter(None, (m.group(2) if m else "").split(",")))
        gh(["issue", "edit", number, "--title", title, "--body-file", f.name])
        new = [w for w in a.waiting if w not in seen]
        if LEVELS[a.level] > LEVELS.get(before, 1):
            gh(["issue", "comment", number, "--body", f"Worse since last time: {a.headline} "
                f"([run]({run_url})). The issue above says what to do."])
        elif a.key == "refresh" and a.level == "broken":
            gh(["issue", "comment", number, "--body",
                f"Still broken this week ([run]({run_url})). {a.headline}"])
        elif new:
            gh(["issue", "comment", number, "--body",
                f"New decision{'s' if len(new) > 1 else ''} waiting: "
                + ", ".join(f"`{w}`" for w in new) + f" ([run]({run_url}))."])
        return "updated"
    finally:
        Path(f.name).unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("workflow", choices=["refresh", "deploy"])
    ap.add_argument("--job-status", required=True)
    ap.add_argument("--run-url", required=True)
    ap.add_argument("--repo-url", required=True)
    ap.add_argument("--review", type=Path, default=STATE / "review.json")
    ap.add_argument("--cloudflare", default="true")
    ap.add_argument("--print", action="store_true", help="show the issue; touch nothing")
    ap.add_argument("--keep-broken", action="store_true",
                    help="after a review decision: never downgrade a broken issue")
    args = ap.parse_args(argv)

    if args.workflow == "refresh":
        review = None
        if args.review.exists():
            review = json.loads(args.review.read_text(encoding="utf-8"))
            if review.get("dry_run"):
                return 0
        a = assess_refresh(review, args.job_status)
    else:
        a = assess_deploy(args.job_status, args.cloudflare == "true")

    if args.print:
        print(f"[{a.level}] {TITLES.get((a.key, a.level), 'no issue')}\n")
        print(render(a, args.run_url, args.repo_url))
        return 0
    try:
        done = sync(a, args.run_url, args.repo_url, keep_broken=args.keep_broken)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        print(f"::warning::Could not update the status issue: {detail.strip()[:300]}")
        return 0
    print(f"Status issue ({a.key}, {a.level}): {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
