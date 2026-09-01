"""Scrapability census. No API key, no model, no writes to org data.

    python pipeline/census.py                  # all organisations
    python pipeline/census.py --only crisis,shelter
    python pipeline/census.py --limit 5        # a quick look

Answers one question — *can we read this page at all?* — and keeps it strictly
separate from *what does it say?*. That separation matters: extraction costs money
and produces claims that need reviewing, whereas this costs nothing but politeness
and produces a decision about whether to extract at all.

Run this before the first real extraction. If it reports that most pages are
client-rendered, the project needs a headless browser and that is a different
conversation. Finding out now costs an afternoon; finding out afterwards means
unpicking a hundred unreliable records.

Writes docs/census.md (read this) and pipeline/state/census.json (for tooling).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import httpx

from config import (MIN_MAIN_CONTENT_CHARS, ORGS_DIR, REQUEST_TIMEOUT_SECONDS,
                    ROOT, STATE, USER_AGENT)
from fetchpage import (_get, cms_updated, find_role_links, full_text,
                       looks_client_rendered, main_content, robots_allows)

CENSUS_JSON = STATE / "census.json"
CENSUS_MD = ROOT / "docs" / "census.md"

VERDICTS = {
    "clean": "Ready to extract",
    "thin": "Real page, but no role detail on it — treat as link-only",
    "client_rendered": "Content loads via JavaScript — needs a different URL, or a "
                       "headless browser",
    "blocked": "robots.txt disallows — link only, never extract",
    "redirected": "URL has moved — update it before extracting",
    "dead": "Broken — needs a new URL",
}


def survey_one(org: dict) -> dict:
    url = org["volunteer_url"]
    row = {"id": org["id"], "name": org["name"], "url": url,
           "robots_allowed": None, "http_status": None, "final_url": None,
           "main_chars": None, "boilerplate_ratio": None, "role_links": [],
           "cms_updated": None, "verdict": None, "note": None}

    try:
        row["robots_allowed"] = robots_allows(url)
    except Exception as exc:
        row["robots_allowed"] = None
        row["note"] = f"robots.txt check failed: {type(exc).__name__}"

    if row["robots_allowed"] is False:
        row["verdict"] = "blocked"
        return row

    try:
        r = _get(url, {"User-Agent": USER_AGENT,
                       "Accept": "text/html,application/xhtml+xml"})
    except Exception as exc:
        row.update(verdict="dead", note=f"{type(exc).__name__}: {exc}")
        return row

    row["http_status"] = r.status_code
    row["final_url"] = str(r.url)
    if r.status_code >= 400:
        row.update(verdict="dead", note=f"HTTP {r.status_code}")
        return row

    html = r.text
    main, whole = main_content(html), full_text(html)
    row["main_chars"] = len(main)
    row["boilerplate_ratio"] = round(1 - len(main) / len(whole), 3) if whole else None
    row["cms_updated"] = cms_updated(html)
    try:
        row["role_links"] = find_role_links(html, url)
    except Exception:
        row["role_links"] = []

    if len(main) < MIN_MAIN_CONTENT_CHARS:
        # Two very different problems look identical by character count, and they
        # lead to opposite decisions. Separate them explicitly.
        if looks_client_rendered(html):
            row["verdict"] = "client_rendered"
            row["note"] = (f"only {len(main)} chars extractable and the page has a "
                           "framework mount point — content is rendered in-browser")
        else:
            row["verdict"] = "thin"
            row["note"] = (f"only {len(main)} chars, but it is real prose — this "
                           "page genuinely doesn't describe roles. Link-only.")
    elif row["final_url"].rstrip("/") != url.rstrip("/"):
        row["verdict"] = "redirected"
        row["note"] = f"now serves {row['final_url']}"
    elif len(main) < 1200 and not row["role_links"]:
        row["verdict"] = "thin"
        row["note"] = "no role sub-pages found and little text — likely a "\
                      "'get in touch' page rather than described roles"
    else:
        row["verdict"] = "clean"
    return row


def write_markdown(rows: list[dict]) -> None:
    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r)
    order = ["clean", "thin", "redirected", "client_rendered", "blocked", "dead"]
    n = len(rows)
    clean = len(by.get("clean", []))

    lines = [
        "# Scrapability census",
        "",
        f"**Generated** {datetime.now(timezone.utc):%d %B %Y, %H:%M} UTC  ",
        f"**Surveyed** {n} organisations. No extraction ran; nothing was written to "
        "org data.",
        "",
        "## Verdict",
        "",
        "| Verdict | Count | Means |",
        "|---|---:|---|",
    ]
    for v in order:
        if v in by:
            lines.append(f"| {v} | {len(by[v])} | {VERDICTS[v]} |")

    lines += ["", "## What to do next", ""]
    if n and clean / n >= 0.7:
        lines.append(
            f"**{clean} of {n} pages are ready to extract.** That's a healthy "
            "majority — proceed with `python pipeline/run.py`. Everything will land "
            "in a review PR, because §11.3 routes all new roles to review "
            "regardless of confidence. The first PR will be large; that is correct "
            "for a cold start and it happens once.")
    elif n and clean / n >= 0.4:
        lines.append(
            f"**Only {clean} of {n} pages are ready.** Extract those, and treat the "
            "rest as link-only for now — a card that links out honestly is better "
            "than a card with invented detail. Revisit the `thin` and `redirected` "
            "ones by hand; they are usually a wrong URL rather than a hard problem.")
    else:
        lines.append(
            f"**Only {clean} of {n} pages are ready. Stop and reconsider.** At this "
            "rate the extraction pipeline is not the right tool. Options: ship "
            "link-only cards for everything (still useful, and honest), pursue §19 "
            "Q3 and ask the charities for data directly, or add a headless browser "
            "to CI — which is a real ongoing maintenance cost and works against "
            "assumption A4.")

    if "client_rendered" in by:
        lines += ["", f"The {len(by['client_rendered'])} client-rendered page(s) "
                  "load their content with JavaScript. Before reaching for a "
                  "headless browser, check whether the site has a plain-HTML "
                  "volunteering page elsewhere — often it does."]
    if "blocked" in by:
        lines += ["", f"The {len(by['blocked'])} blocked page(s) have asked crawlers "
                  "not to read them. Respect that: mark them `link_only`, show the "
                  "card with a link and no asserted detail, and never extract."]

    lines += ["", "## Per organisation", "",
              "| Organisation | Verdict | Main text | Boilerplate | Role links | "
              "CMS date | Note |", "|---|---|---:|---:|---:|---|---|"]
    for v in order:
        for r in sorted(by.get(v, []), key=lambda x: x["name"]):
            bp = f"{r['boilerplate_ratio']:.0%}" if r["boilerplate_ratio"] else "—"
            lines.append(
                f"| [{r['name']}]({r['url']}) | {r['verdict']} | "
                f"{r['main_chars'] or 0:,} | {bp} | {len(r['role_links'])} | "
                f"{r['cms_updated'] or '—'} | {r['note'] or ''} |")

    lines += ["", "## Role sub-pages found", "",
              "These are the pages extraction would read in addition to the "
              "landing page. Worth a skim — if something here is obviously not a "
              "role, tighten the filters in `fetchpage._ROLE_LINK_BLOCK`.", ""]
    for r in rows:
        if r["role_links"]:
            lines.append(f"**{r['name']}**")
            lines += [f"- {l}" for l in r["role_links"]]
            lines.append("")

    CENSUS_MD.parent.mkdir(parents=True, exist_ok=True)
    CENSUS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated org ids")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    orgs = []
    for p in sorted(ORGS_DIR.glob("*.json")):
        o = json.loads(p.read_text(encoding="utf-8"))["organisation"]
        if only and o["id"] not in only:
            continue
        orgs.append(o)
    if args.limit:
        orgs = orgs[:args.limit]

    if not orgs:
        print(f"No organisation files in {ORGS_DIR}. Run pipeline/seed.py first.")
        return 2

    print(f"Surveying {len(orgs)} pages at one request/second. "
          f"Roughly {len(orgs) * 3 // 60 + 1} minute(s).\n")
    print(f"{'organisation':<38} {'verdict':<16} {'main':>7} {'boiler':>7} {'links':>5}")
    print("-" * 78)

    rows = []
    for o in orgs:
        row = survey_one(o)
        rows.append(row)
        bp = f"{row['boilerplate_ratio']:.0%}" if row["boilerplate_ratio"] else "—"
        print(f"{o['name'][:37]:<38} {row['verdict']:<16} "
              f"{row['main_chars'] or 0:>7} {bp:>7} {len(row['role_links']):>5}")

    STATE.mkdir(parents=True, exist_ok=True)
    CENSUS_JSON.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "surveyed": len(rows), "rows": rows}, indent=2) + "\n", encoding="utf-8")
    write_markdown(rows)

    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"\nWrote {CENSUS_MD.relative_to(ROOT)} — read that before extracting.")
    return 0 if tally.get("clean", 0) else 1


if __name__ == "__main__":
    sys.exit(main())
