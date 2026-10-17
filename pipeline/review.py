"""Decide on the proposals the weekly check held back. Spec §11.3.

    python pipeline/review.py list                 what is waiting, one line each
    python pipeline/review.py show crisis          the changes, field by field
    python pipeline/review.py approve crisis       publish the proposal as reviewed
    python pipeline/review.py approve crisis --drop "Kitchen helper" --keep-missing
    python pipeline/review.py approve watw --same "Kitchen Volunteer=Drop-In Kitchen"
    python pipeline/review.py reject crisis        the current listing stays

Work on main, after `git fetch`. The proposals are read from the freshness/review
branch on origin or the local pipeline/state/review.json, whichever run is newer.
Decisions are written to data/orgs/*.json and noted in the local review.json. Then
commit data/ and push; the deploy runs. Without a terminal, use the "Review a
proposal" workflow in GitHub Actions, which does the same thing.

Approving is a human claim: every record you approve is marked
provenance.reviewed_by_human. Read the charity's page before you approve.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import ValidationError, validate

from config import ORGS_DIR, ROOT, STATE
from gate import diff_fields, pair_roles
from schema import ORG_SCHEMA, RECORD_SCHEMA
from sitecheck import site_errors

REVIEW = STATE / "review.json"


class ReviewError(Exception):
    """A decision that cannot be applied safely. Nothing has been written."""


# ------------------------------------------------------------------ loading

# The weekly job keeps one rolling branch and one PR. Older runs used a branch
# per date; those are still read if the rolling branch does not exist yet.
ROLLING_BRANCH = "refs/remotes/origin/freshness/review"


def _latest_review_branch() -> str | None:
    try:
        out = subprocess.run(
            ["git", "for-each-ref", "--sort=-refname", "--format=%(refname)",
             "refs/remotes/origin/freshness/"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    refs = [r.strip() for r in out.splitlines() if r.strip()]
    if ROLLING_BRANCH in refs:
        return ROLLING_BRANCH
    dated = [r for r in refs if r.startswith(ROLLING_BRANCH + "-")]
    return dated[0] if dated else None


def _read_branch(ref: str) -> dict | None:
    try:
        text = subprocess.run(["git", "show", f"{ref}:pipeline/state/review.json"],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout
        return json.loads(text)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def load_review(path: Path = REVIEW, prefer_newer: bool = True) -> dict:
    """The proposals to decide on: the local copy or the review branch, whichever
    is newer. A local copy used to win unconditionally, so after a week away the
    previous run's proposals were offered as if they were current."""
    local = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    ref = _latest_review_branch() if (prefer_newer or local is None) else None
    remote = _read_branch(ref) if ref else None
    if remote is not None and (local is None or
                               remote.get("generated_at", "") > local.get("generated_at", "")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(remote, indent=2) + "\n", encoding="utf-8")
        print(f"Loaded proposals from {ref.removeprefix('refs/remotes/')} "
              f"(run of {remote.get('generated_at', 'unknown date')})")
        review = remote
    elif local is not None:
        review = local
    else:
        raise ReviewError("No pipeline/state/review.json and no freshness/review branch "
                          "on origin. Run `git fetch` first.")
    if "results" not in review:
        raise ReviewError("This review.json predates per-charity results; "
                          "wait for the next refresh.")
    return review


def proposals(review: dict) -> list[dict]:
    return [r for r in review["results"] if r.get("outcome") == "review_required"]


def find(review: dict, org_id: str) -> dict:
    for r in proposals(review):
        if r["org_id"] == org_id:
            return r
    raise ReviewError(f"No proposal for {org_id!r}. `list` shows what is waiting.")


def org_path(org_id: str, orgs_dir: Path = ORGS_DIR) -> Path:
    path = orgs_dir / f"{org_id}.json"
    if not path.exists():
        raise ReviewError(f"{path.name} not found")
    return path


def _assert_current(doc: dict, result: dict) -> None:
    """Refuse proposals overtaken by a later publish or decision."""
    check = doc["organisation"].get("check", {})
    if result.get("fetched_content_hash") and \
            check.get("content_hash") == result["fetched_content_hash"]:
        raise ReviewError("Already decided: this page version is already the "
                          "approved baseline.")
    last, seen = check.get("last_success"), result.get("checked_at")
    if last and seen and last > seen:
        raise ReviewError(f"Out of date: the listing was updated at {last}, after "
                          f"this proposal was made ({seen}). Wait for the next refresh.")


# ------------------------------------------------------------------ showing

def _value(record: dict, dotted: str):
    cur = record
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def describe(result: dict, doc: dict) -> str:
    old = doc.get("opportunities", [])
    new = result.get("proposed", [])
    pairs, added, gone = pair_roles(old, new)
    lines = [f"{result['name']} — {result['url']}",
             f"Checked {result.get('checked_at')} · model {result.get('model')} · "
             f"confidence {result.get('confidence')}"]
    if result.get("page_notes"):
        lines.append(f"Model's notes: {result['page_notes']}")
    lines.append("")
    for o, n in pairs:
        changed = diff_fields(o, n)
        if not changed:
            lines.append(f"= {n['title']}: no change")
            continue
        title = n["title"] if o["title"] == n["title"] else f"{o['title']} → {n['title']}"
        lines.append(f"~ {title}")
        for f in changed:
            lines.append(f"    {f}: {json.dumps(_value(o, f))} → {json.dumps(_value(n, f))}")
    for n in added:
        lines.append(f"+ NEW {n['title']} ({n['commitment']}, {n['activity']}, "
                     f"status {n['status']}, DBS {n['screening']['dbs']})")
        lines.append(f"    {n['what_youd_do']}")
        if n.get("apply_url"):
            lines.append(f"    apply: {n['apply_url']}")
    for o in gone:
        lines.append(f"- MISSING {o['title']} (no longer found on the page)")
    # Titles get reworded ("Drop-In Kitchen" → "Kitchen Volunteer"). Pairing is by
    # title, so suggest likely renames; --same keeps the published id and links.
    hints = [(n, o) for n in added for o in gone if n["activity"] == o["activity"]]
    if hints:
        lines += ["", "Possibly the same role renamed (same activity) — if so, approve with:"]
        lines += [f'    --same "{n["title"]}={o["title"]}"' for n, o in hints]
    unsupported = sorted({f"{n['title']}: {f}" for n in new
                          for f in n["provenance"].get("unsupported_fields", [])})
    if unsupported:
        lines += ["", "Not supported by the page, so set to unknown:"]
        lines += [f"    {u}" for u in unsupported]
    return "\n".join(lines)


# ------------------------------------------------------------------ deciding

def _site_errors(org_id: str) -> list[str]:
    """Run the site build's own data checks, so an approval cannot break the build."""
    return site_errors(org_id)


# Descriptive facts a reader relies on but the gate does not treat as critical. A
# re-extraction that leaves one blank usually means "this page does not say", not
# "this is no longer true": the first approvals (8 Oct 2026) erased hand-researched
# postcodes, commitments and eligibility that way. Critical fields (screening,
# status, next_intake) are deliberately not carried: unknown is the safe value.
CARRY_FORWARD = ("commitment", "min_term_months", "typical_shift_hours", "specific_times",
                 "postcode_district", "who_can_apply", "skills", "eligibility",
                 "seasonal_window", "role_zones", "london_wide")
_BLANK = (None, "unknown", [], "")


def carry_forward(old: dict, new: dict) -> list[str]:
    """Keep the current value of each descriptive field the new reading left blank."""
    kept = []
    for field in CARRY_FORWARD:
        if new.get(field) in _BLANK and old.get(field) not in _BLANK:
            if field == "postcode_district" and old.get("location_type") != new.get("location_type"):
                continue
            new[field] = copy.deepcopy(old[field])
            kept.append(field)
    if "postcode_district" in kept and new.get("coords") is None:
        new["coords"] = old.get("coords")
    return kept


def _domain(url: str | None) -> str:
    return urlparse(url or "").netloc.replace("www.", "")


def carry_platform_note(old: dict, new: dict) -> bool:
    """Keep a reviewer's note that this charity recruits on another domain.

    The build refuses an apply link off the charity's own domain unless a person
    reviewed the record and named that domain in provenance.unsupported_fields
    (Shelter on app.betterimpact.com, Big Issue on bigissue.com). A re-extraction
    cannot carry that note, so without this every approval for those charities
    was refused by the site check however correct the proposal was.
    """
    domain = _domain(new.get("apply_url"))
    if not domain or domain != _domain(old.get("apply_url")):
        return False
    notes = [n for n in old.get("provenance", {}).get("unsupported_fields", [])
             if domain in n]
    fields = new.setdefault("provenance", {}).setdefault("unsupported_fields", [])
    missing = [n for n in notes if n not in fields]
    fields.extend(missing)
    return bool(missing)


def approve(result: dict, path: Path, drop: list[str] = (), keep_missing: bool = False,
            site_check=None, same: list[str] = (), take_blanks: bool = False,
            carried: list | None = None) -> dict:
    original = path.read_text(encoding="utf-8")
    doc = json.loads(original)
    _assert_current(doc, result)
    org = doc["organisation"]
    proposed = copy.deepcopy(result.get("proposed") or [])
    if not proposed and not keep_missing:
        raise ReviewError("The proposal has no roles. Use --keep-missing to keep the "
                          "current ones, or reject it.")

    titles = {r["title"].casefold(): r for r in proposed}
    for title in drop:
        if title.casefold() not in titles:
            raise ReviewError(f"--drop {title!r}: no proposed role has that title")
        proposed.remove(titles[title.casefold()])

    old_roles = doc.get("opportunities", [])
    renamed = set()
    for pair in same:
        new_title, sep, old_title = pair.partition("=")
        if not sep:
            raise ReviewError(f'--same {pair!r}: use "New title=Old title"')
        new = next((r for r in proposed if r["title"].casefold() == new_title.strip().casefold()), None)
        old = next((r for r in old_roles if r["title"].casefold() == old_title.strip().casefold()), None)
        if new is None or old is None:
            raise ReviewError(f'--same {pair!r}: no proposed role "{new_title.strip()}" '
                              f'or no current role "{old_title.strip()}"')
        new["id"] = old["id"]          # keep published links and visitors' saved roles
        if (old.get("postcode_district"), old.get("location_type")) == \
                (new.get("postcode_district"), new.get("location_type")):
            new["coords"] = old.get("coords")
        renamed.add(old["id"])

    by_id = {r["id"]: r for r in old_roles}
    for record in proposed:
        if record["id"] in by_id:
            carry_platform_note(by_id[record["id"]], record)
    if not take_blanks:
        for record in proposed:
            if record["id"] in by_id:
                kept = carry_forward(by_id[record["id"]], record)
                if kept and carried is not None:
                    carried.append((record["title"], kept))

    for record in proposed:
        record["provenance"]["reviewed_by_human"] = True
    if keep_missing:
        _, _, gone = pair_roles(old_roles, result.get("proposed") or [])
        for old in (o for o in gone if o["id"] not in renamed):
            kept = copy.deepcopy(old)
            kept["status"] = "unknown"   # we no longer see it, so we cannot say it is open
            proposed.append(kept)

    ids = [r["id"] for r in proposed]
    if len(ids) != len(set(ids)):
        raise ReviewError("Two roles would share an id; drop one of them")
    for record in proposed:
        try:
            validate(record, RECORD_SCHEMA)
        except ValidationError as exc:
            raise ReviewError(f"{record['title']}: {exc.message}") from None

    doc["opportunities"] = proposed
    check = org.setdefault("check", {})
    check["content_hash"] = result["fetched_content_hash"]
    check["last_success"] = result["checked_at"]
    check["consecutive_failures"] = 0
    validate(org, ORG_SCHEMA)

    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    errors = (site_check or _site_errors)(org["id"])
    if errors:
        path.write_text(original, encoding="utf-8")
        raise ReviewError("The site build would reject this, so nothing was changed:\n  "
                          + "\n  ".join(errors))
    return doc


def reject(result: dict, path: Path) -> dict:
    """The current listing is still right for this page. Stop proposing this version."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    _assert_current(doc, result)
    doc["organisation"].setdefault("check", {})["content_hash"] = result["fetched_content_hash"]
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def _note(review: dict, org_id: str, decision: str, path: Path = REVIEW) -> None:
    for r in review["results"]:
        if r["org_id"] == org_id and r.get("outcome") == "review_required":
            r["outcome"] = decision
    results = review["results"]
    human = [r for r in results if r.get("outcome") == "review_required"]
    source_failures = [r for r in results if r.get("outcome") == "source_failed"]
    ai_failures = [r for r in results if r.get("outcome") in (
        "ai_unavailable", "extraction_failed", "invalid_extraction")]
    unresolved = {"review_required", "source_failed", "ai_unavailable",
                  "extraction_failed", "invalid_extraction"}
    review["items"] = [r for r in results if r.get("route", "review") == "review"
                       and r.get("outcome") in unresolved]
    review["human_review_count"] = len(human)
    review["source_failed_count"] = len(source_failures)
    review["ai_failed_count"] = len(ai_failures)
    review["failed_count"] = len(source_failures) + len(ai_failures)
    review["needs_review"] = len(review["items"])
    path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", type=Path, default=REVIEW, help="review.json to read")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for name in ("show", "approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("org_id")
        if name == "approve":
            p.add_argument("--drop", action="append", default=[], metavar="TITLE",
                           help="leave out a proposed role (repeatable)")
            p.add_argument("--keep-missing", action="store_true",
                           help="keep roles no longer found, with status unknown")
            p.add_argument("--same", action="append", default=[], metavar="NEW=OLD",
                           help="a proposed role is a renamed current one; keep its id")
            p.add_argument("--take-blanks", action="store_true",
                           help="accept blank descriptive fields instead of keeping current values")
    args = ap.parse_args(argv)

    try:
        # An explicit --path means exactly that file; the default is compared with
        # the review branch and the newer run wins.
        review = load_review(args.path, prefer_newer=args.path == REVIEW)
        if args.command == "list":
            waiting = proposals(review)
            if not waiting:
                print("Nothing waiting for review.")
            for r in waiting:
                print(f"{r['org_id']:<38} {r['roles_before']} → {r['roles_after']} roles · "
                      f"{'; '.join(r['reasons'])[:80]}")
            return 0
        result = find(review, args.org_id)
        path = org_path(args.org_id)
        if args.command == "show":
            print(describe(result, json.loads(path.read_text(encoding="utf-8"))))
            return 0
        if args.command == "approve":
            carried = []
            doc = approve(result, path, args.drop, args.keep_missing, same=args.same,
                          take_blanks=args.take_blanks, carried=carried)
            for title, fields in carried:
                print(f"  kept current {', '.join(fields)} for {title} (page silent; "
                      f"--take-blanks to clear)")
            _note(review, args.org_id, "approved", args.path)
            print(f"Approved: {len(doc['opportunities'])} roles written to "
                  f"data/orgs/{path.name}. Commit data/ and push to publish.")
        else:
            reject(result, path)
            _note(review, args.org_id, "rejected", args.path)
            print(f"Rejected: current listing kept; this page version will not be "
                  f"proposed again. Commit data/orgs/{path.name} and push.")
        return 0
    except ReviewError as exc:
        print(f"Not done: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
