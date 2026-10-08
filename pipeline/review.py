"""Decide on the proposals the weekly check held back. Spec §11.3.

    python pipeline/review.py list                 what is waiting, one line each
    python pipeline/review.py show crisis          the changes, field by field
    python pipeline/review.py approve crisis       publish the proposal as reviewed
    python pipeline/review.py approve crisis --drop "Kitchen helper" --keep-missing
    python pipeline/review.py approve watw --same "Kitchen Volunteer=Drop-In Kitchen"
    python pipeline/review.py reject crisis        the current listing stays

Work on main. The proposals are read from pipeline/state/review.json; if there is
none, from the newest freshness/review-* branch on origin (run `git fetch` first).
Decisions are written to data/orgs/*.json and noted in the local review.json. Then
commit data/ and push; Cloudflare deploys it. Close the review PR afterwards.

Approving is a human claim: every record you approve is marked
provenance.reviewed_by_human. Read the charity's page before you approve.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import ValidationError, validate

from config import ORGS_DIR, ROOT, STATE
from gate import diff_fields, pair_roles
from schema import ORG_SCHEMA, RECORD_SCHEMA

REVIEW = STATE / "review.json"


class ReviewError(Exception):
    """A decision that cannot be applied safely. Nothing has been written."""


# ------------------------------------------------------------------ loading

def _latest_review_branch() -> str | None:
    try:
        out = subprocess.run(
            ["git", "for-each-ref", "--sort=-refname", "--format=%(refname)",
             "refs/remotes/origin/freshness/"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    refs = [r for r in out.splitlines() if r.strip()]
    return refs[0] if refs else None


def load_review(path: Path = REVIEW) -> dict:
    if not path.exists():
        ref = _latest_review_branch()
        if not ref:
            raise ReviewError("No pipeline/state/review.json and no freshness/review-* "
                              "branch on origin. Run `git fetch` first.")
        text = subprocess.run(["git", "show", f"{ref}:pipeline/state/review.json"],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Loaded proposals from {ref.removeprefix('refs/remotes/')}")
    review = json.loads(path.read_text(encoding="utf-8"))
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
    spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
    build = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "site"))
    try:
        spec.loader.exec_module(build)
        orgs, opps, fresh, _ = build.load()
        errors = build.check(orgs, opps, fresh)
    finally:
        sys.path.remove(str(ROOT / "site"))
    return [e for e in errors if e.startswith(org_id)]


def approve(result: dict, path: Path, drop: list[str] = (), keep_missing: bool = False,
            site_check=None, same: list[str] = ()) -> dict:
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
    args = ap.parse_args(argv)

    try:
        review = load_review(args.path)
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
            doc = approve(result, path, args.drop, args.keep_missing, same=args.same)
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
