"""Seed organisation stubs from the Phase 0 URL research.

    python pipeline/seed.py            # create any missing stubs
    python pipeline/seed.py --report   # show the triage without writing

Names and URLs come from the original PoC, which is to say from Tek's own research.
This script does not invent boroughs, charity numbers or roles — those come from the
census and extraction. It only creates the skeletons.

Editorial triage is applied here rather than silently at extraction time, because
two of the 34 entries are not organisations offering volunteering roles at all, and
four have URLs that point somewhere other than a volunteering page. Discovering
that during extraction would produce plausible-looking records for things that
aren't roles.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from config import ORGS_DIR

# ---------------------------------------------------------------- triage
# Not organisations with their own volunteering roles. Excluded from listings and
# handled elsewhere on the site instead.
NOT_A_ROLE_SOURCE = {
    "StreetLink": "A referral service for reporting someone sleeping rough, not a "
                  "volunteering opportunity. Belongs in /five-minutes/.",
    "Homeless Link": "A sector job board that aggregates other charities' roles. "
                     "Listing it would duplicate our own function. Belongs in "
                     "/about/ as an onward pointer, and in the §11.5 decay banner.",
}

# URLs that need a human to find the right page before extraction is meaningful.
# The census will confirm, but flagging now stops us extracting from a homepage and
# publishing a role that says "get in touch".
URL_SUSPECT = {
    "Simon Community": "homepage only — no volunteering path in the PoC",
    "Cardboard Citizens": "homepage only — no volunteering path in the PoC",
    "New Horizon Youth Centre": "points at a paid-jobs page, not volunteering",
    "The Big Issue Foundation": "points at reachvolunteering.org.uk, a third-party "
                                "platform — the freshness check would be watching "
                                "Reach rather than the charity",
}

# name, area, volunteer_url — from the PoC.
SEED = [
    ("Crisis", "london-wide", "https://www.crisis.org.uk/get-involved/volunteer/"),
    ("Shelter", "london-wide", "https://england.shelter.org.uk/support_us/volunteer"),
    ("St Mungo's", "london-wide", "https://www.mungos.org/get-involved/volunteer/"),
    ("Centrepoint", "london-wide", "https://centrepoint.org.uk/support-us/volunteer"),
    ("Thames Reach", "london-wide", "https://thamesreach.org.uk/support-us/volunteer/"),
    ("The Big Issue Foundation", "london-wide", "https://reachvolunteering.org.uk/org/big-issue-foundation"),
    ("Depaul UK", "london-wide", "https://www.depaul.org.uk/nightstop-volunteer/"),
    ("Emmaus", "london-wide", "https://emmaus.org.uk/support-us/volunteering/volunteer-roles/"),
    ("Single Homeless Project", "london-wide", "https://www.shp.org.uk/get-involved/volunteer/"),
    ("Glass Door", "south-west london", "https://www.glassdoor.org.uk/listing/category/volunteer-roles"),
    ("Simon Community", "central london", "https://www.simoncommunity.org.uk/"),
    ("Cardboard Citizens", "london-wide", "https://cardboardcitizens.org.uk/"),
    ("StreetLink", "london-wide", "https://thestreetlink.org.uk/start"),
    ("Streets of London", "london-wide", "https://www.streetsoflondon.org.uk/get-involved/volunteer"),
    ("HandsOn London", "london-wide", "https://www.handsonlondon.org.uk/volunteer"),
    ("Homeless Link", "london-wide", "https://jobs.homeless.org.uk/volunteer-jobs/"),
    ("Groundswell", "london-wide", "https://groundswell.org.uk/volunteer-opportunities/"),
    ("Housing Justice", "london-wide", "https://housingjustice.org.uk/donate-or-get-involved/volunteer"),
    ("New Horizon Youth Centre", "central london", "https://nhyouthcentre.org.uk/get-involved/jobs/"),
    ("akt", "london-wide", "https://www.akt.org.uk/volunteer/"),
    ("Stonewall Housing", "london-wide", "https://stonewallhousing.org/volunteer-opportunities/"),
    ("Women at the Well", "central london", "https://www.watw.org.uk/volunteer"),
    ("Solace Women's Aid", "london-wide", "https://www.solacewomensaid.org/get-involved/volunteer-with-us/"),
    ("The Passage", "central london", "https://passage.org.uk/volunteering/"),
    ("The Connection at St Martin's", "central london", "https://www.connection-at-stmartins.org.uk/volunteer/"),
    ("Spires", "south london", "https://www.spires.org.uk/"),
    ("Providence Row", "east london", "https://www.providencerow.org.uk/pages/68-volunteering-opportunities"),
    ("The Whitechapel Mission", "east london", "https://whitechapel.org.uk/volunteering"),
    ("SPEAR", "south-west london", "https://www.spearlondon.org/get-involved/be-a-volunteer/"),
    ("Ace of Clubs", "south london", "https://aceofclubs.org.uk/volunteer/"),
    ("North London Action for the Homeless", "north london", "https://www.nlah.org.uk/volunteer/"),
    ("Manna Society", "south london", "https://www.mannasociety.org.uk/how-you-can-help/volunteer-time/"),
    ("Spitalfields Crypt Trust", "east london", "https://sct.org.uk/support-us/volunteer/"),
    ("West London Mission", "central london", "https://www.wlm.org.uk/pages/category/volunteer-opportunities"),
]


def slug(name: str) -> str:
    s = name.lower().replace("'", "").replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def stub(name: str, area: str, url: str) -> dict:
    origin = re.match(r"(https?://[^/]+)", url)
    return {
        "organisation": {
            "id": slug(name),
            "name": name,
            "aliases": [],
            "charity_number": None,
            "website_url": (origin.group(1) + "/") if origin else url,
            "volunteer_url": url,
            "summary": None,
            # Boroughs are deliberately empty. The PoC recorded coarse compass
            # areas ("south london"), which are not boroughs, and guessing would
            # reintroduce exactly the location imprecision we set out to fix.
            "coverage": "london_wide" if area == "london-wide" else "multi_borough",
            "boroughs": [],
            "focus_groups": [],
            "lived_experience_roles": False,
            "check": {
                "last_attempt": None,
                "last_success": None,
                "link_status": "ok",
                "content_hash": None,
                "consecutive_failures": 0,
                "etag": None,
                "last_modified": None,
            },
        },
        "opportunities": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="show triage, write nothing")
    args = ap.parse_args()

    ORGS_DIR.mkdir(parents=True, exist_ok=True)
    made, existing, skipped, suspect = [], [], [], []

    # Match on name as well as slug. A hand-written record may legitimately use a
    # shorter id than the formal name slugs to ("whitechapel-mission" for "The
    # Whitechapel Mission"), and matching on slug alone creates a duplicate stub
    # that silently shadows real data.
    have_names, have_ids = set(), set()
    for f in ORGS_DIR.glob("*.json"):
        o = json.loads(f.read_text(encoding="utf-8"))["organisation"]
        have_ids.add(o["id"])
        have_names.add(o["name"].lower())

    for name, area, url in SEED:
        if name in NOT_A_ROLE_SOURCE:
            skipped.append((name, NOT_A_ROLE_SOURCE[name]))
            continue
        if name in URL_SUSPECT:
            suspect.append((name, URL_SUSPECT[name]))

        if slug(name) in have_ids or name.lower() in have_names:
            existing.append(name)
            continue
        path = ORGS_DIR / f"{slug(name)}.json"
        if not args.report:
            path.write_text(json.dumps(stub(name, area, url), indent=2) + "\n", encoding="utf-8")
        made.append(name)

    print(f"{len(SEED)} entries in the PoC research\n")
    print(f"  {len(existing):>2} already have data")
    print(f"  {len(made):>2} stubs {'would be' if args.report else ''} created")
    print(f"  {len(skipped):>2} excluded — not sources of volunteering roles\n")

    for n, why in skipped:
        print(f"  EXCLUDED  {n}\n            {why}")
    if suspect:
        print("\n  URLs needing a human before extraction is meaningful:")
        for n, why in suspect:
            print(f"    ~ {n}: {why}")
    print(f"\n  {len(existing) + len(made)} organisations in scope.")
    print("  Next: python pipeline/census.py   (no API key needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
