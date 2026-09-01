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
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from jsonschema import ValidationError, validate

import decay
from config import (DEAD_LINK_AFTER_FAILURES, ORGS_DIR, ROUTE_REVIEW, STATE)
from extract import extract, finalise
from fetchpage import fetch
from gate import classify_fetch_failure, route_org
from schema import ORG_SCHEMA, RECORD_SCHEMA

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


def process(path: Path, doc: dict, client, dry: bool) -> dict:
    org = doc["organisation"]
    old_roles = doc.get("opportunities", [])
    check = org.setdefault("check", {})
    check["last_attempt"] = NOW()
    url = org["volunteer_url"]
    report = {"org_id": org["id"], "name": org["name"], "url": url,
              "route": "auto", "reasons": [], "roles_before": len(old_roles),
              "roles_after": len(old_roles)}

    res = fetch(url, known_hash=check.get("content_hash"))

    if res.status == "blocked":
        check["link_status"] = "link_only"
        report.update(route="auto", reasons=["robots.txt disallows crawling; "
                                            "record set to link-only"])
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    if res.status == "failed":
        check["consecutive_failures"] = check.get("consecutive_failures", 0) + 1
        d = classify_fetch_failure(check["consecutive_failures"],
                                   DEAD_LINK_AFTER_FAILURES)
        if d.needs_review:
            check["link_status"] = "dead"
        report.update(route=d.route, reasons=d.reasons + [res.error or ""])
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    check["consecutive_failures"] = 0
    check["etag"] = res.etag
    check["last_modified"] = res.last_modified
    check["link_status"] = "redirected" if res.redirected else "ok"

    if res.status == "unchanged":
        check["last_success"] = NOW()
        report["reasons"] = ["page unchanged (304 or identical hash); "
                             "no extraction needed"]
        if not dry:
            path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return report

    ex = extract(client, org["name"], url, res.text)
    if ex.error:
        report.update(route=ROUTE_REVIEW, reasons=[f"extraction failed: {ex.error}"])
        return report

    new_roles = []
    for r in ex.roles:
        rec = finalise(r, org["id"], url, ex.confidence, ex.verified, ex.unsupported)
        try:
            validate(rec, RECORD_SCHEMA)
        except ValidationError as exc:
            report.update(route=ROUTE_REVIEW,
                          reasons=[f"record failed schema: {exc.message}"])
            return report
        new_roles.append(rec)

    route, decisions = route_org(old_roles, new_roles, ex.confidence)
    report.update(
        route=route,
        confidence=ex.confidence,
        model=ex.model_used,
        page_notes=ex.page_notes,
        unsupported=ex.unsupported,
        roles_after=len(new_roles),
        reasons=[r for d in decisions for r in d.reasons],
        changed_fields=sorted({f for d in decisions for f in d.changed_fields}),
    )

    if route == ROUTE_REVIEW:
        report["proposed"] = new_roles       # held, not written
        return report

    check["last_success"] = NOW()
    check["content_hash"] = res.content_hash
    doc["opportunities"] = new_roles
    if not dry:
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch, extract and gate, but write nothing")
    ap.add_argument("--only", default="", help="comma-separated org ids")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",") if s.strip()] or None
    orgs = load_orgs(only)
    if not orgs:
        log("No organisation files found in", ORGS_DIR)
        return 2

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log("ANTHROPIC_API_KEY is not set.")
        return 2
    client = anthropic.Anthropic(api_key=key)

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
        except Exception as exc:                       # never let one page stop the run
            rep = {"org_id": doc["organisation"]["id"], "name": name,
                   "route": ROUTE_REVIEW,
                   "reasons": [f"unhandled error: {type(exc).__name__}: {exc}"]}
        reports.append(rep)
        mark = "REVIEW" if rep["route"] == ROUTE_REVIEW else "ok    "
        log(f"{mark}  {name:<38} {'; '.join(rep['reasons'])[:88]}")

    all_orgs = [json.loads(p.read_text(encoding="utf-8"))["organisation"]
                for p in sorted(ORGS_DIR.glob("*.json"))]
    fresh = decay.compute(all_orgs) if args.dry_run else decay.write(all_orgs)

    needs = [r for r in reports if r["route"] == ROUTE_REVIEW]
    STATE.mkdir(parents=True, exist_ok=True)
    REVIEW_OUT.write_text(json.dumps(
        {"generated_at": NOW(), "dry_run": args.dry_run,
         "checked": len(reports), "needs_review": len(needs),
         "median_days_since_check": fresh["median_days_since_check"],
         "site_banner": fresh["site_banner"], "items": needs}, indent=2) + "\n", encoding="utf-8")

    log(f"\n{len(reports)} checked · {len(needs)} need review · "
        f"median freshness {fresh['median_days_since_check']} days"
        + ("  [dry run, nothing written]" if args.dry_run else ""))
    if fresh["site_banner"]:
        log("! decay banner is ACTIVE — listings look unmaintained")

    return 1 if needs else 0


if __name__ == "__main__":
    sys.exit(main())
