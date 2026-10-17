"""Orchestrator. Spec §11.

    python pipeline/run.py --dry-run              everything, writes nothing
    python pipeline/run.py --only manna,crisis    a subset
    python pipeline/run.py                        the real thing

Writes two things: updated data/orgs/*.json for anything that passed the gate, and
pipeline/state/review.json listing what a human needs to look at. The GitHub Action
turns the second into a pull request.

Exit codes: 0 nothing needs review · 1 review needed · 2 the run itself broke.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ai import AIClient
from jsonschema import ValidationError, validate

import boards
import decay
from config import (CONFIRM_EXISTING_LISTINGS, CRITICAL_FIELDS, DEAD_LINK_AFTER_FAILURES,
                    ORGS_DIR, ROUTE_REVIEW, STATE)
from extract import confirm, extract, finalise, reproduces_source
from fetchpage import fetch
from gate import classify_fetch_failure, diff_fields, pair_roles, route_org
from schema import ORG_SCHEMA, RECORD_SCHEMA
from sitecheck import record_errors

REVIEW_OUT = STATE / "review.json"
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_orgs(only: list[str] | None) -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(ORGS_DIR.glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if only and doc["organisation"]["id"] not in only:
            continue
        out.append((p, doc))
    return out


def log(*a):
    print(*a, flush=True)


PROVIDER_FAILURES = frozenset({'auth', 'rejected', 'model_unavailable', 'rate_limited',
                               'network', 'provider_unavailable', 'input_too_large'})

# Facts on which a fresh reading may not quietly differ from a confirmed listing.
DISAGREE_ON = CRITICAL_FIELDS | {"who_can_apply"}


def _value(record: dict, dotted: str):
    cur = record
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def disagreements(pairs) -> list[str]:
    """Critical facts a fresh extraction states differently from the listing.

    A fresh reading that asserts nothing (unknown, null) does not contradict a
    value the confirmation pass found quoted on the page; one that asserts a
    different value does, and that goes to a person.
    """
    out = []
    for old, new in pairs:
        for f in diff_fields(old, new):
            if f in DISAGREE_ON and _value(new, f) not in (None, "unknown", []):
                out.append(f"{old.get('title')}: {f} {json.dumps(_value(old, f))} → "
                           f"{json.dumps(_value(new, f))}")
    return out


_NOT_HTML = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")


def known_role_pages(doc: dict) -> list[str]:
    """Pages the published listing was written from, other than the landing page.

    They are re-read every run even if the landing page no longer links them in a
    way the crawler can follow, so a role's details are checked against its own
    page rather than a one-line summary.
    """
    landing = doc["organisation"]["volunteer_url"].rstrip("/")
    out = []
    for role in doc.get("opportunities", []):
        for url in (role.get("apply_url"), role.get("provenance", {}).get("source_url")):
            if not url or not url.startswith(("http://", "https://")):
                continue
            key = url.split("#")[0].rstrip("/")
            if key == landing or key.lower().endswith(_NOT_HTML) or key in out:
                continue
            out.append(key)
    return out


def process(path: Path, doc: dict, client, dry: bool, site_check=record_errors) -> dict:
    org = doc["organisation"]
    old_roles = doc.get("opportunities", [])
    check = org.setdefault("check", {})
    check["last_attempt"] = NOW()
    url = org["volunteer_url"]
    report = {"org_id": org["id"], "name": org["name"], "url": url,
              "route": "auto", "reasons": [], "roles_before": len(old_roles),
              "roles_after": len(old_roles)}

    res = fetch(url, known_hash=check.get("content_hash"), cache_write=not dry,
                known_pages=known_role_pages(doc))

    def save_check():
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    if res.status == "blocked":
        check["link_status"] = "link_only"
        report.update(route="auto", outcome='link_only', reasons=["robots.txt disallows crawling; "
                                            "record set to link-only"])
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    if res.status == "failed" and res.refused:
        # The site answered but turned us away (bot protection, rate limit, or a
        # TLS chain only browsers can complete). Visitors can still reach it, so
        # this is not evidence of a dead link, and does not count towards one.
        report.update(route="auto", outcome='source_refused', reasons=[
            "site refused the automated check; link status unchanged", res.error or ""])
        save_check()
        return report

    if res.status == "failed":
        check["consecutive_failures"] = check.get("consecutive_failures", 0) + 1
        d = classify_fetch_failure(check["consecutive_failures"],
                                   DEAD_LINK_AFTER_FAILURES)
        if d.needs_review:
            check["link_status"] = "dead"
        report.update(route=d.route, outcome='source_failed', reasons=d.reasons + [res.error or ""])
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    check["consecutive_failures"] = 0
    check["etag"] = res.etag
    check["last_modified"] = res.last_modified
    check["link_status"] = "redirected" if res.redirected else "ok"
    report['fetched_content_hash'] = res.content_hash
    report['pages_read'] = list(res.pages_read)
    report['checked_at'] = check['last_attempt']
    # Volunteer platforms the page links to that no reader of ours covers: roles
    # there are invisible to this check, and the report must say so.
    covered = {urlparse(org.get("board", {}).get("base_url", "")).netloc,
               *org.get("platforms_acknowledged", [])}
    report['unread_platforms'] = [h for h in getattr(res, "platforms", []) or [] if h not in covered]

    if org.get("board"):
        # The landing page tells us the link works; the roles are on a board the page
        # does not render, so they are read from the board's own feed instead.
        return process_board(path, doc, old_roles, client, dry, site_check, report,
                             save_check, res.content_hash)

    if res.status == "unchanged":
        report['outcome'] = 'unchanged'
        check["last_success"] = NOW()
        report["reasons"] = ["page unchanged (304 or identical hash); "
                             "no extraction needed"]
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    if client is None:
        report.update(route=ROUTE_REVIEW, outcome='ai_unavailable', reasons=[
            "page changed or has no approved baseline; no enabled AI provider, "
            "so extraction is unavailable. Existing roles and last_success are unchanged."])
        save_check()
        return report

    if getattr(client, "budget_exhausted", False):
        report.update(route="auto", outcome='ai_deferred', reasons=[
            "AI allowance for this run is used up; queued first for the next run"])
        save_check()
        return report

    previous_extraction = check.get("last_extraction")

    def defer(reason):
        if previous_extraction is None:
            check.pop("last_extraction", None)
        else:
            check["last_extraction"] = previous_extraction
        report.update(route="auto", outcome='ai_deferred', reasons=[
            f"deferred to next run: {reason}"])
        save_check()
        return report

    def confirmed(reasons, advance_baseline):
        # The checked time, not "now", so a proposal from this same run is not
        # "out of date" when someone reviews it.
        check["last_success"] = check["last_attempt"]
        if advance_baseline:
            check["content_hash"] = res.content_hash
        report.update(route="auto", outcome="confirmed", reasons=reasons)
        save_check()
        return report

    check["last_extraction"] = NOW()

    # Does the page still support what we already publish? See extract.confirm.
    # A full confirmation of a listing, with nothing else on the page, ends here
    # and changes no record. When the page also lists other roles, or nothing is
    # listed, a fresh extraction is a second opinion: it reads the extra roles,
    # and if it contradicts a listed role on a critical fact nothing is confirmed
    # and the ordinary gate path decides.
    second_opinion, others = False, []
    if CONFIRM_EXISTING_LISTINGS:
        conf = confirm(client, org["name"], url, res.text, old_roles)
        if conf.deferred:
            return defer(conf.error)
        if conf.confirmed:
            report.update(model=conf.model_used, other_roles=conf.other_roles)
            if old_roles and not conf.other_roles:
                return confirmed([f"page still supports all {len(old_roles)} listed "
                                  "roles; nothing changed"], advance_baseline=True)
            second_opinion, others = True, conf.other_roles
        else:
            report["confirmation"] = (conf.error or "not confirmed: "
                                      + ", ".join(conf.unsupported))[:400]

    ex = extract(client, org["name"], url, res.text)
    if second_opinion and old_roles and (getattr(ex, "deferred", False) or ex.error):
        # The listing itself stands. The extra roles are read first next run: the
        # baseline does not move and the queue position is kept.
        if previous_extraction is None:
            check.pop("last_extraction", None)
        else:
            check["last_extraction"] = previous_extraction
        report["additions_unread"] = ex.error
        return confirmed([f"page still supports all {len(old_roles)} listed roles; it "
                          f"also mentions {', '.join(others)}, not read this run: "
                          f"{ex.error}"], advance_baseline=False)
    if getattr(ex, "deferred", False):
        return defer(ex.error)
    if ex.error:
        report.update(route=ROUTE_REVIEW, outcome='extraction_failed', reasons=[f"extraction failed: {ex.error}"])
        save_check()
        return report

    new_roles = []
    for r in ex.roles:
        rec = finalise(r, org["id"], url, ex.confidence, ex.verified, ex.unsupported)
        try:
            validate(rec, RECORD_SCHEMA)
        except ValidationError as exc:
            report.update(route=ROUTE_REVIEW, outcome='invalid_extraction',
                          reasons=[f"record failed schema: {exc.message}"])
            save_check()
            return report
        new_roles.append(rec)

    pairs, added, _ = pair_roles(old_roles, new_roles)
    for old, new in pairs:
        new['id'] = old['id']  # retain published links and visitors' saved IDs
        for hand_curated in ('role_zones', 'london_wide'):  # never extracted; keep them
            if hand_curated in old and hand_curated not in new:
                new[hand_curated] = old[hand_curated]
        if (old.get('postcode_district'), old.get('location_type')) == \
                (new.get('postcode_district'), new.get('location_type')):
            new['coords'] = old.get('coords')

    conflicts = disagreements(pairs) if second_opinion else []
    if conflicts:
        # Two readings of the page disagree on a fact that decides whether
        # someone can volunteer. Nothing is confirmed; the gate sees the full
        # extraction, and every critical change goes to a person as before.
        report["confirmation"] = ("confirmed, but a fresh reading disagrees on "
                                  + "; ".join(conflicts))[:400]
    elif second_opinion:
        # Only the roles the listing does not yet carry are proposed, beside the
        # current records unchanged, so approving adds and replaces nothing. The
        # gate still decides: a new role always needs a person.
        if not added:
            what = (f"page still supports all {len(old_roles)} listed roles; the others "
                    f"it mentions ({', '.join(others)}) are ones already listed"
                    if old_roles else "page still lists no roles")
            # Advance only when the two readings agree there is nothing new.
            return confirmed([what], advance_baseline=bool(old_roles) or not others)
        if old_roles:
            check["last_success"] = check["last_attempt"]
        taken = {r["id"] for r in old_roles}
        for new in added:
            base, n = new["id"], 2
            while new["id"] in taken:
                new["id"], n = f"{base}-{n}", n + 1
            taken.add(new["id"])
        new_roles = copy.deepcopy(old_roles) + added
        if old_roles:
            report["reasons_prefix"] = ["current listing confirmed against the page"]

    return route_and_publish(
        path, doc, old_roles, new_roles, ex.confidence, report, save_check, dry,
        site_check, res.content_hash, model=ex.model_used, page_notes=ex.page_notes,
        unsupported=ex.unsupported)


def route_and_publish(path, doc, old_roles, new_roles, confidence, report, save_check, dry,
                      site_check, content_hash, model=None, page_notes=None,
                      unsupported=None) -> dict:
    """The gate, then the site-build check, then publish or hold. One path for every
    source of roles (an extracted page or a platform board): no source gets a
    shorter route to a visitor."""
    org = doc["organisation"]
    check = org["check"]
    route, decisions = route_org(old_roles, new_roles, confidence)
    report.update(
        route=route,
        confidence=confidence,
        model=model,
        page_notes=page_notes,
        unsupported=unsupported or [],
        roles_after=len(new_roles),
        reasons=report.pop("reasons_prefix", []) + [r for d in decisions for r in d.reasons],
        changed_fields=sorted({f for d in decisions for f in d.changed_fields}),
    )

    if route != ROUTE_REVIEW:
        # Never auto-publish what the site build would refuse. One such record
        # stops the deploy and, through the tests, next week's refresh too.
        errors = site_check(org, new_roles)
        if errors:
            route = ROUTE_REVIEW
            report.update(route=route, reasons=report["reasons"] + [
                "the site build would refuse this update: " + "; ".join(errors)[:400]])

    if route == ROUTE_REVIEW:
        report['outcome'] = 'review_required'
        report["proposed"] = new_roles       # held, not written
        save_check()
        return report

    check["last_success"] = NOW()
    report['outcome'] = 'published'
    check["content_hash"] = content_hash
    doc["opportunities"] = new_roles
    if not dry:
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return report


def board_summariser(client, report):
    """A summary in the model's own words for a role new to the listing, or None.

    One call per new role and never for roles already listed, so a board does not
    use the daily AI allowance each week. The result is checked like any extraction:
    no run of eight words from the description.
    """
    if client is None or getattr(client, "budget_exhausted", False):
        return None
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['summary'],
              'properties': {'summary': {'type': 'string', 'minLength': 15, 'maxLength': 200}}}

    def summarise(offer):
        if getattr(client, "budget_exhausted", False) or len(offer.description) < 40:
            return None
        system, user = boards.paraphrase_prompt(offer)
        try:
            text = client.generate_structured(system, user, schema).json["summary"].strip()
        except Exception as exc:
            report.setdefault("summaries_skipped", []).append(f"{offer.id}: {type(exc).__name__}")
            return None
        if reproduces_source(text, offer.description):
            report.setdefault("summaries_skipped", []).append(f"{offer.id}: repeated source wording")
            return None
        return text
    return summarise


def process_board(path, doc, old_roles, client, dry, site_check, report, save_check, content_hash,
                  get=None) -> dict:
    """Roles read from the charity's platform feed. Same gate, same publish path."""
    org = doc["organisation"]
    board = org["board"]
    check = org["check"]
    try:
        offers = boards.load_offers(board, get=get)
    except boards.BoardError as exc:
        # Nothing changes and nothing is confirmed: a board we could not read says
        # nothing about its roles.
        report.update(route="auto", outcome='board_failed', reasons=[f"board not read: {exc}"])
        save_check()
        return report

    now_iso = NOW()
    paired_titles = {r["title"].casefold() for r in old_roles}
    summarise = board_summariser(client, report)
    # Summaries only for roles the listing does not already carry.
    only_new = (lambda offer: summarise(offer) if summarise and offer.title.casefold()
                not in paired_titles else None)
    new_roles, set_aside = boards.london_records(
        offers, org["id"], now_iso, org["volunteer_url"], only_new)
    report.update(board_offers=len(offers), board_set_aside=set_aside)
    for rec in new_roles:
        try:
            validate(rec, RECORD_SCHEMA)
        except ValidationError as exc:
            report.update(route=ROUTE_REVIEW, outcome='invalid_extraction',
                          reasons=[f"board record {rec['id']} failed schema: {exc.message}"])
            save_check()
            return report

    pairs, added, _ = pair_roles(old_roles, new_roles)
    for old, new in pairs:
        new['id'] = old['id']                   # keep published links and saved IDs
        if new["provenance"]["unsupported_fields"] and old.get("what_youd_do"):
            new["what_youd_do"] = old["what_youd_do"]    # unchanged wording, no churn
        for kept in ('role_zones', 'london_wide', 'coords'):
            if kept in old and (kept not in new or new[kept] is None):
                new[kept] = old[kept]
    taken = {r["id"] for r in old_roles} | {n["id"] for o, n in pairs}
    for new in added:
        base, n = new["id"], 2
        while new["id"] in taken:
            new["id"], n = f"{base}-{n}", n + 1
        taken.add(new["id"])
    check["last_extraction"] = now_iso
    return route_and_publish(path, doc, old_roles, new_roles, 1.0, report, save_check, dry,
                             site_check, content_hash, model="platform feed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="check source pages only; no AI calls or file writes")
    ap.add_argument("--only", default="", help="comma-separated org ids")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    # The AI allowance covers only a few pages per run. In filename order the same
    # charities would use it every week and the rest would never be extracted, so
    # the longest-unextracted go first.
    orgs = sorted(load_orgs(only), key=lambda item: (
        item[1]["organisation"].get("check", {}).get("last_extraction") or ""))
    if not orgs:
        log("No organisation files found in", ORGS_DIR)
        return 2

    configured_client = AIClient()
    client = configured_client if configured_client.available and not args.dry_run else None
    if client is None:
        log("WARNING: No enabled AI provider (or source-only dry run). Checking source pages without "
            "model calls; changed or unbaselined content will need review.")

    for p, doc in orgs:
        try:
            validate(doc["organisation"], ORG_SCHEMA)
        except ValidationError as exc:
            log(f"! {p.name}: organisation record invalid — {exc.message}")
            return 2

    reports = []
    for path, doc in orgs:
        name = doc["organisation"]["name"]
        try:
            rep = process(path, doc, client, args.dry_run)
        except Exception as exc:
            # Name the charity and keep the traceback: "Internal refresh error:
            # KeyError" alone left nothing to act on.
            import traceback
            log(f"Internal refresh error while checking {name}: {type(exc).__name__}: "
                f"{exc}. Stopping without publishing.")
            log(traceback.format_exc())
            return 2
        reports.append(rep)
        mark = "REVIEW" if rep["route"] == ROUTE_REVIEW else "ok    "
        log(f"{mark}  {name:<38} {'; '.join(rep['reasons'])[:88]}")
        if args.dry_run and rep.get('pages_read'):
            for page in rep['pages_read']:
                log(f"          read {page}")

    # Freshness as the site computes it: only charities that place notices
    # (site/build.py load() skips the rest), so the median the run reports is the
    # one that decides the banner readers see.
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ORGS_DIR.glob("*.json"))]
    listed = [d["organisation"] for d in docs if d.get("opportunities")]
    fresh = decay.compute(listed) if args.dry_run else decay.write(listed)

    needs = [r for r in reports if r["route"] == ROUTE_REVIEW]
    source_failures = [r for r in reports if r.get('outcome') == 'source_failed']
    ai_failures = [r for r in reports if r.get('outcome') in (
        'ai_unavailable', 'extraction_failed', 'invalid_extraction')]
    failures = source_failures + ai_failures
    human_review = [r for r in reports if r.get('outcome') == 'review_required']
    # Broken means the AI integration itself, not one awkward page: AI was needed
    # and not configured; every request failed for a provider-level reason (key,
    # model, quota, network); or no request could be sent at all for a reason
    # other than a used-up daily allowance (the allowance checkpoint could not be
    # pushed). One malformed answer or a failed copyright retry is an incomplete
    # check for the report, and no longer turns the whole job red.
    diags = configured_client.diagnostics
    ai_broken = (not args.dry_run and (
        (client is None and any(r.get('outcome') == 'ai_unavailable' for r in reports))
        or (client is not None and configured_client.calls > 0
            and configured_client.successful_calls == 0
            and any(d.get('reason') in PROVIDER_FAILURES for d in diags))
        or (client is not None and configured_client.calls == 0
            and any(r.get('outcome') == 'ai_deferred' for r in reports)
            and any(d.get('reason') == 'budget_exhausted'
                    and 'daily AI allowance exhausted' not in (d.get('message') or '')
                    for d in diags))))
    review = {"generated_at": NOW(), "dry_run": args.dry_run,
         "ai_configured": client is not None,
         "extraction_available": client is not None,
         "ai_broken": ai_broken,
         "ai_calls": configured_client.calls,
         "ai_successful_calls": configured_client.successful_calls,
         "confirmed_count": sum(r.get('outcome') == 'confirmed' for r in reports),
         "human_review_count": len(human_review), "failed_count": len(failures),
         "source_failed_count": len(source_failures), "ai_failed_count": len(ai_failures),
         "refused_count": sum(r.get('outcome') == 'source_refused' for r in reports),
         "deferred_count": sum(r.get('outcome') == 'ai_deferred' for r in reports),
         "published_count": sum(r.get('outcome') == 'published' for r in reports),
         "unchanged_count": sum(r.get('outcome') == 'unchanged' for r in reports),
         "results": reports,
         "ai_diagnostics": configured_client.diagnostics,
         "checked": len(reports), "needs_review": len(needs),
         "median_days_since_check": fresh["median_days_since_check"],
         "site_banner": fresh["site_banner"], "items": needs}
    if not args.dry_run:
        STATE.mkdir(parents=True, exist_ok=True)
        REVIEW_OUT.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

    log(f"\n{len(reports)} checked · {review['confirmed_count']} confirmed · "
        f"{review['unchanged_count']} unchanged · {len(human_review)} proposals need review · "
        f"{len(failures)} checks incomplete · {review['refused_count']} refused · "
        f"{review['deferred_count']} deferred · "
        f"median freshness {fresh['median_days_since_check']} days"
        + ("  [dry run, nothing written]" if args.dry_run else ""))
    if fresh["site_banner"]:
        log("! decay banner is ACTIVE — listings look unmaintained")

    return 1 if needs or failures else 0


if __name__ == "__main__":
    sys.exit(main())
