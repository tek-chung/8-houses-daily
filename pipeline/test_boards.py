"""Platform boards: Crisis's Rosterfy board, read from its own feed.

Added 17 October 2026. Crisis's roles live on a board the page does not render, so
the weekly check held four of its 80-odd current offers. These tests hold:

  - the feed is parsed from named fields, using offers captured from the live board
    on 17 October 2026 (descriptions shortened);
  - only London offers (and remote ones) are kept, and a role the board places in
    Edinburgh or Birmingham never becomes a London record;
  - a place, disclosure check or interview the board does not state is "unknown",
    never filled in;
  - nothing a board produces skips the gate: new roles and critical changes wait
    for a person, and an unreadable board changes nothing.
"""
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from jsonschema import validate

import boards
import review
import run as runner
from fetchpage import FetchResult
from schema import ORG_SCHEMA, RECORD_SCHEMA

BASE = "https://mycrisisvolunteering.crisis.org.uk"
NOW = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)


def offer(oid, token, name, labels, *, location=None, venue="A venue", address="United Kingdom",
          timing="", disclosure="None", interview=None, age_limit=None, year="Year round",
          team="Local services", types=("Front of house roles",), closes=None, description="",
          is_public="Yes", can_apply="Yes", archived=0, virtual=0):
    return {
        "object": {"id": oid, "token": token, "is_archived": archived, "deleted_at": None,
                   "apps_close_timestamp": closes, "end_date": None},
        "nice": {"custom_role_name": name,
                 "custom_id_like_to_volunteer_in_or_around:array": list(labels),
                 "custom_time_commitment": timing,
                 "custom_disclosure_check_type": disclosure,
                 "custom_interview_required_for_this_role": interview,
                 "custom_age_limit_for_this_role": age_limit, "minimum_age": "",
                 "custom_christmas_or_year_round_role": year,
                 "custom_department:array": [team], "activity_type:array": list(types),
                 "public": is_public, "publish": "Yes", "can_self_apply": can_apply,
                 "updated_at__date": "16 Oct 2026"},
        "relations": {
            "job_title": {"object": {"frontend_name": name, "description": description}},
            "venue": {"object": {"frontend_name": venue, "is_virtual": virtual},
                      "nice": {"address_oneline": address}},
            "location": {"object": {"frontend_name": location}} if location else {}},
    }


# Offers as the live board returned them on 17 October 2026.
LIVE = [
    offer(4119, "A5LVGChqMGxkdAZQJUggM0o5RaWJ8l", "Welcome and Reception Volunteer",
          ["London - Croydon Skylight"], location="Croydon", venue="Crisis Skylight Croydon",
          address="12 Surrey Street, London, Greater London, England, United Kingdom, CR0 1RG",
          timing="Thursdays, ideally betwwen 10am - 4pm", disclosure="Basic Disclosure DBS",
          team="Local services", types=("Front of house roles", "Member/guest support roles"),
          closes="2026-11-13T00:00:00.000000Z",
          description="<p>As a Welcome and Reception Volunteer you will be the first point of "
                      "contact for many people who need to access our services.</p>"),
    offer(4166, "dYUu0WkQDRt1ehaGqVPRloSrxkl8RV", "Activities Lead Volunteer", ["Edinburgh"],
          location="Edinburgh", venue="Crisis Skylight Edinburgh",
          address="Cranston House, 271 Canongate, Edinburgh, City of Edinburgh, United Kingdom, EH8 8BQ",
          disclosure="Basic Disclosure (Scotland)", year=None),
    offer(4366, "I1UFjBDGjMgM95nKFTFlN9RXEAJ0no", "Retail Volunteer Shop Camden",
          ["Camden Shop - London", "London shops - all"], location="London Shop",
          venue="Camden Shop",
          address="22-24 Parkway, Camden, London, Greater London, England, United Kingdom, NW1 7HL",
          timing="4 hours or 1 full day per week", team="Shops",
          types=("Front of house roles", "Physically active roles", "Behind the scenes roles")),
    offer(6586, "5rxlVv8phbYgTDfXHsve7YBqXWoWQ0", "Delivery Driver Volunteer", ["Birmingham"],
          location="Birmingham", venue="Community",
          address="Suite 303, 25 Heath Mill Lane, Birmingham, West Midlands, England, United Kingdom, B9 4AE",
          disclosure="Basic Disclosure DBS", interview="No",
          age_limit="Over 23 and under 75 years of age"),
    offer(7399, "uNpSmgcd6e8eWZHvy8Z111IE0urV5l", "Wellbeing Volunteer, London",
          ["London - Christmas venue"], location="London Christmas - All Day Centres and Hotels",
          venue="All Day Centres and Hotels",
          timing="We expect volunteers to do 1 complete shift. Day centres 9:30am - 5:30pm",
          interview="Yes", year="Christmas", team="Christmas",
          types=("Activities and Entertainment", "Specialist roles")),
]


def records(items=LIVE, summarise=None):
    return boards.london_records(boards.parse_rosterfy(items, BASE), "crisis",
                                 "2026-10-17T21:00:00+00:00",
                                 "https://www.crisis.org.uk/get-involved/volunteer/", summarise)


# ------------------------------------------------------------------ region

def test_only_london_offers_become_records_and_the_rest_are_counted():
    recs, set_aside = records()
    assert [r["title"] for r in recs] == ["Welcome and Reception Volunteer",
                                          "Retail Volunteer Shop Camden",
                                          "Wellbeing Volunteer, London"]
    assert set_aside == 2          # Edinburgh and Birmingham


def test_a_role_the_board_places_outside_london_is_never_a_london_record():
    for item in (LIVE[1], LIVE[3]):
        assert not boards.is_london(boards.parse_rosterfy([item], BASE)[0])


def test_every_record_is_valid_and_ids_come_from_the_board():
    recs, _ = records()
    for rec in recs:
        validate(rec, RECORD_SCHEMA)
    assert [r["id"] for r in recs] == ["crisis-board-4119", "crisis-board-4366", "crisis-board-7399"]
    assert recs[0]["apply_url"] == f"{BASE}/roles/A5LVGChqMGxkdAZQJUggM0o5RaWJ8l"
    assert all(r["provenance"]["method"] == "platform" for r in recs)
    assert all(not r["provenance"]["reviewed_by_human"] for r in recs)


# ------------------------------------------------------------------ the facts

def test_place_disclosure_interview_and_timing_come_from_fields():
    welcome, shop, xmas = records()[0]
    assert welcome["stated_places"] == ["London", "Croydon"]
    assert welcome["screening"]["dbs"] == "basic"
    assert welcome["commitment"] == "weekly" and welcome["when"] == ["weekday_daytime"]
    assert welcome["specific_times"] == "Thursdays, ideally betwwen 10am - 4pm"
    assert shop["stated_places"] == ["London", "Camden"]
    assert shop["screening"]["dbs"] == "none" and shop["commitment"] == "weekly"
    assert shop["activity"] == "shop_warehouse"
    assert xmas["screening"]["interview"] is True
    assert xmas["commitment"] == "one_off" and xmas["seasonal_window"] == {"start_month": 12, "end_month": 12}
    assert xmas["stated_places"] == ["London"]


def test_what_the_board_does_not_say_is_unknown_never_filled_in():
    bare = offer(1, "tok", "Chef Volunteer, London", ["London - Christmas venue"], disclosure=None)
    rec = records([bare])[0][0]
    assert rec["screening"] == {"dbs": "unknown", "references": None, "interview": None,
                                "min_age": None, "induction": None}
    assert rec["commitment"] == "unknown" and rec["specific_times"] is None
    assert rec["eligibility"] == [] and rec["next_intake"] is None


@pytest.mark.parametrize("label,expected", [
    ("None", "none"), ("No DBS check needed", "none"), ("Basic Disclosure DBS", "basic"),
    ("Basic Disclosure (Scotland)", "basic"), ("Enhanced DBS with barred lists", "enhanced"),
    ("PVG scheme", "unknown"), ("DBS (level not given)", "required_unspecified"),
    (None, "unknown"), ("", "unknown")])
def test_disclosure_labels(label, expected):
    assert boards.dbs_value(label) == expected


def test_an_age_limit_the_board_states_is_kept_as_stated():
    item = offer(2, "tok", "Delivery Driver Volunteer, London", ["London"],
                 age_limit="Over 23 and under 75 years of age")
    assert records([item])[0][0]["eligibility"] == ["Over 23 and under 75 years of age"]


def test_descriptions_are_never_copied_from_the_board():
    recs, _ = records()
    source = boards.parse_rosterfy(LIVE, BASE)[0].description
    assert source and source not in recs[0]["what_youd_do"]
    assert recs[0]["what_youd_do"].startswith("Welcome and Reception Volunteer at Crisis Skylight Croydon")
    assert "built from structured fields" in " ".join(recs[0]["provenance"]["unsupported_fields"])


def test_a_model_summary_is_used_when_given():
    recs, _ = records(summarise=lambda o: "Greet people at the centre door and sign them in.")
    assert recs[0]["what_youd_do"] == "Greet people at the centre door and sign them in."


# ------------------------------------------------------------------ what is skipped

@pytest.mark.parametrize("kwargs", [{"is_public": "No"}, {"can_apply": "No"}, {"archived": 1}])
def test_offers_a_person_cannot_apply_for_are_skipped(kwargs):
    item = offer(3, "tok", "Chef Volunteer, London", ["London"], **kwargs)
    assert records([item])[0] == []


def test_borough_names_match_the_site():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
    from locations import BOROUGH_ZONES
    assert sorted(boards.LONDON_BOROUGHS) == sorted(BOROUGH_ZONES)


# ------------------------------------------------------------------ fetching

def test_the_feed_is_read_page_by_page_and_a_partial_read_is_refused(monkeypatch):
    monkeypatch.setattr("fetchpage.robots_allows", lambda url: True)
    pages = {"1": {"data": [LIVE[0]], "next_page_url": "x"}, "2": {"data": [LIVE[2]], "next_page_url": None}}
    seen = []

    def get(url, params):
        seen.append(dict(params)["page"])
        return pages[dict(params)["page"]]
    assert len(boards.fetch_rosterfy(BASE, NOW, get=get)) == 2 and seen == ["1", "2"]

    with pytest.raises(boards.BoardError):
        boards.fetch_rosterfy(BASE, NOW, get=lambda url, params: {"data": [], "next_page_url": "more"})
    with pytest.raises(boards.BoardError):
        boards.fetch_rosterfy(BASE, NOW, get=lambda url, params: {"unexpected": True})


def test_the_feed_uses_the_boards_own_filters():
    params = dict(boards._board_params(NOW))
    assert params["filter[2][attr]"] == "public" and params["filter[2][value]"] == "1"
    assert params["filter[0][value]"] == "2026-10-17T21:00:00Z"


# ------------------------------------------------------------------ Assemble (Centrepoint)

ASSEMBLE_BASE = "https://centrepoint.goassemble.com"


def assemble(oid, name, suffix, where, *, min_age=18, end="2026-10-30", status="Published",
             target="public", unlisted=False, kind="volunteer"):
    return {"id": oid, "display_name": name, "suffix": suffix, "status": status,
            "advert_target": target, "unlisted": unlisted, "advert_end_date": end,
            "minimum_age": 0, "updated_at": "2026-10-14 14:07:24",
            "public_url": f"{ASSEMBLE_BASE}/opportunities/{oid}-x", "advert_location": where,
            "long_advert": "As a Gardening Volunteer you'll be helping to maintain our green spaces.",
            "role_profile": {"type": kind, "minimum_age": min_age, "display_name": name,
                             "tasks": [{"task": "Perform gardening duties including weeding."}],
                             "skills": [{"skill": "Be reliable and have a positive outlook"},
                                        {"skill": "IT competent - able to use Microsoft Office "
                                                  "including Microsoft Teams"}]}}


# Centrepoint's board on 17 October 2026: three current opportunities.
CENTREPOINT = [
    assemble(125242, "Gardening Volunteer (Hammersmith and Fulham)", "Hammersmith and Fulham",
             {"address": "Woodstock Grove, W12, United Kingdom", "postcode": "W12", "city": "",
              "name": "Woodstock Grove, W12"}),
    assemble(125244, "Gardening Volunteer (Westminister)", "Westminister", {"name": "Westminster"}),
    assemble(118586, "Mini Bus Driver (Bradford)", "Bradford", min_age=21, end="2026-12-25",
             where={"address": "Coates Street, Bradford, BD5 7DL, United Kingdom",
                    "postcode": "BD5 7DL", "city": "Bradford", "name": "Coates Street, BD5 7DL"}),
]


def centrepoint_records(items=CENTREPOINT):
    return boards.london_records(boards.parse_assemble(items, ASSEMBLE_BASE), "centrepoint",
                                 "2026-10-17T21:00:00+00:00",
                                 "https://centrepoint.org.uk/support-us/volunteer")


def test_assemble_board_keeps_london_roles_and_sets_aside_bradford():
    recs, set_aside = centrepoint_records()
    assert [r["title"] for r in recs] == ["Gardening Volunteer (Hammersmith and Fulham)",
                                          "Gardening Volunteer (Westminister)"]
    assert set_aside == 1
    for rec in recs:
        validate(rec, RECORD_SCHEMA)
    assert recs[0]["stated_places"] == ["Hammersmith and Fulham"]
    assert recs[1]["stated_places"] == ["Westminster"]       # from the board's own location field
    assert recs[0]["apply_url"] == f"{ASSEMBLE_BASE}/opportunities/125242-x"


def test_assemble_facts_come_from_fields_and_the_rest_is_unknown():
    rec = centrepoint_records()[0][0]
    assert rec["screening"]["min_age"] == 18 and rec["screening"]["dbs"] == "unknown"
    assert rec["commitment"] == "unknown" and rec["specific_times"] is None
    assert rec["skills"] == ["Be reliable and have a positive outlook"]   # long ones are not cut
    assert "gardening" not in rec["what_youd_do"].casefold() or "Volunteer" in rec["what_youd_do"]
    assert "As a Gardening Volunteer you'll be helping" not in rec["what_youd_do"]


@pytest.mark.parametrize("change", [{"status": "Draft"}, {"target": "internal"},
                                    {"unlisted": True}, {"kind": "staff"}])
def test_assemble_offers_the_public_cannot_see_are_skipped(change):
    item = assemble(9, "Gardening Volunteer", "Hackney", {"name": "Hackney"}, **change)
    assert centrepoint_records([item])[0] == []


def test_london_postcodes_count_and_other_postcodes_do_not():
    def place(address):
        return boards.Offer(id="1", title="X", url="https://e.org", address=address)
    for address in ("Woodstock Grove, W12, United Kingdom", "1 High St, SE1 9SG", "EC1A 1BB", "N16 5DT"):
        assert boards.is_london(place(address)), address
    for address in ("Coates Street, Bradford, BD5 7DL", "Cranston House, EH8 8BQ", "B9 4AE", "RG1 1AA"):
        assert not boards.is_london(place(address)), address


def test_assemble_feed_is_paged_and_a_malformed_page_is_refused():
    pages = {"1": {"data": [CENTREPOINT[0]], "meta": {"pagination": {"total_pages": 2}}},
             "2": {"data": [CENTREPOINT[1]], "meta": {"pagination": {"total_pages": 2}}}}
    got = boards.fetch_assemble(ASSEMBLE_BASE, get=lambda url, params: pages[dict(params)["page"]])
    assert len(got) == 2
    with pytest.raises(boards.BoardError):
        boards.fetch_assemble(ASSEMBLE_BASE, get=lambda url, params: {"data": []})


def test_board_type_decides_the_reader():
    got = boards.load_offers({"type": "assemble", "base_url": ASSEMBLE_BASE},
                             get=lambda url, params: {"data": CENTREPOINT,
                                                      "meta": {"pagination": {"total_pages": 1}}})
    assert len(got) == 3
    with pytest.raises(boards.BoardError):
        boards.load_offers({"type": "nope", "base_url": ASSEMBLE_BASE})


# ------------------------------------------------------------------ run.process

def crisis_doc(old_roles):
    org = {"id": "crisis", "name": "Crisis", "website_url": "https://www.crisis.org.uk/",
           "volunteer_url": "https://www.crisis.org.uk/get-involved/volunteer/",
           "board": {"type": "rosterfy", "base_url": BASE, "region": "london"},
           "check": {"last_attempt": None, "last_success": "2026-09-02T00:00:00+00:00",
                     "link_status": "ok", "content_hash": "old", "consecutive_failures": 0}}
    validate(org, ORG_SCHEMA)
    return {"organisation": org, "opportunities": old_roles}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "NOW", lambda: "2026-10-18T04:00:00+00:00")
    monkeypatch.setattr(runner, "fetch", lambda *a, **k: FetchResult(
        "changed", text="shell", content_hash="landing-v2"))
    monkeypatch.setattr("fetchpage.robots_allows", lambda url: True)
    path = tmp_path / "crisis.json"
    return path


def run_board(path, doc, items, client=None):
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = runner.process_board(path, doc, doc["opportunities"], client, False,
                                  lambda org, roles: [], {"org_id": "crisis"}, lambda: None,
                                  "landing-v2", get=lambda url, params: {"data": items, "next_page_url": None})
    return report


def test_new_board_roles_wait_for_a_person_and_nothing_is_written(harness):
    doc = crisis_doc([])
    report = run_board(harness, doc, LIVE)
    assert report["outcome"] == "review_required" and report["route"] == "review"
    assert len(report["proposed"]) == 3 and report["board_set_aside"] == 2
    assert doc["opportunities"] == []                 # held, not published


def test_an_unreadable_board_changes_nothing_and_confirms_nothing(harness):
    doc = crisis_doc([])
    path = harness
    path.write_text(json.dumps(doc), encoding="utf-8")

    def broken(url, params):
        raise boards.BoardError("board feed answered HTTP 503")
    report = runner.process_board(path, doc, [], None, False, lambda o, r: [],
                                  {"org_id": "crisis"}, lambda: None, "landing-v2", get=broken)
    assert report["outcome"] == "board_failed" and "503" in report["reasons"][0]
    assert doc["opportunities"] == [] and doc["organisation"]["check"]["last_success"].startswith("2026-09-02")


def test_an_unchanged_board_publishes_without_review_and_keeps_ids(harness):
    first = crisis_doc([])
    recs, _ = records()
    # the listing already holds exactly what the board says now
    doc = crisis_doc(copy.deepcopy(recs))
    doc["opportunities"][0]["id"] = "crisis-welcome-and-reception"      # a published id
    report = run_board(harness, doc, LIVE)
    assert report["outcome"] == "published", report["reasons"]
    assert doc["opportunities"][0]["id"] == "crisis-welcome-and-reception"
    assert doc["organisation"]["check"]["last_success"] == "2026-10-18T04:00:00+00:00"


def test_a_role_that_leaves_the_board_is_not_dropped_without_a_person(harness):
    recs, _ = records()
    doc = crisis_doc(copy.deepcopy(recs))
    report = run_board(harness, doc, LIVE[:3])          # the Christmas role has gone
    assert report["outcome"] == "review_required"
    assert any("no longer found" in r for r in report["reasons"])
    assert len(doc["opportunities"]) == 3


def test_a_changed_disclosure_check_is_held_for_review(harness):
    recs, _ = records()
    doc = crisis_doc(copy.deepcopy(recs))
    changed = copy.deepcopy(LIVE)
    changed[0]["nice"]["custom_disclosure_check_type"] = "Enhanced DBS"
    report = run_board(harness, doc, changed)
    assert report["outcome"] == "review_required"
    assert any("screening.dbs" in r for r in report["reasons"])


def test_a_model_summary_is_only_asked_for_roles_new_to_the_listing(harness):
    recs, _ = records()
    doc = crisis_doc(copy.deepcopy(recs[:2]))            # welcome + shop already listed
    asked = []

    class Client:
        budget_exhausted = False

        def generate_structured(self, system, user, schema):
            asked.append(user.splitlines()[0])
            return SimpleNamespace(json={"summary": "Take part in the Christmas wellbeing sessions."})
    items = copy.deepcopy(LIVE)
    items[4]["relations"]["job_title"]["object"]["description"] = "<p>" + "Run sessions for guests. " * 5 + "</p>"
    run_board(harness, doc, items, client=Client())
    assert asked == ["Role: Wellbeing Volunteer, London"]


def test_a_summary_that_repeats_the_description_is_refused(harness):
    doc = crisis_doc([])
    sentence = "Welcome people through the door and make them feel safe and expected today"

    class Client:
        budget_exhausted = False

        def generate_structured(self, system, user, schema):
            return SimpleNamespace(json={"summary": sentence})
    items = copy.deepcopy(LIVE)
    items[0]["relations"]["job_title"]["object"]["description"] = f"<p>{sentence} and more.</p>"
    report = run_board(harness, doc, items, client=Client())
    assert "repeated source wording" in " ".join(report["summaries_skipped"])
    assert report["proposed"][0]["what_youd_do"] != sentence


# ------------------------------------------------------------------ WordPress role feeds
# Captured from the live St Mungo's `volunteer_role` feed on 17 October 2026.

def wp(title, slug, status="publish"):
    return {"status": status, "title": {"rendered": title}, "modified": "2026-10-15T14:42:34",
            "link": f"https://www.mungos.org/volunteer_role/{slug}/"}


MUNGOS_FEED = [
    wp("Roma Casework Volunteer  (Roma or Romanian Speaking)", "roma-casework-volunteer"),
    wp("Workshop Assistant Volunteer", "workshop-assistant-volunteer"),
    wp("Women&#8217;s Sewing Group Volunteer", "53914"),
    wp("Hub Support Volunteer", "bournemouth-outreach-and-hub-support-volunteer"),
    wp("Cooking Group Volunteer", "cooking-group-volunteer"),
    wp("Draft role", "draft", status="draft"),
]


def held(title, slug=None):
    return {"title": title,
            "apply_url": f"https://www.mungos.org/volunteer_role/{slug}/" if slug
            else "https://www.mungos.org/get-involved/volunteer/current-volunteering-opportunities/"}


def test_feed_roles_we_do_not_hold_are_reported_and_drafts_are_ignored():
    feed = boards.fetch_wordpress({"url": "https://x/wp"}, get=lambda u, p: MUNGOS_FEED)
    gaps = boards.feed_gaps(feed, [held("Roma Casework Volunteer", "roma-casework-volunteer"),
                                   held("Workshop Assistant Volunteer", "workshop-assistant-volunteer"),
                                   held("Cooking Group Volunteer", "cooking-group-volunteer")])
    assert gaps["missing"] == ["Women’s Sewing Group Volunteer", "Hub Support Volunteer"]
    assert gaps["gone"] == [] and gaps["listed"] == 5


def test_a_held_role_whose_page_left_the_feed_is_reported_but_others_are_not():
    feed = boards.fetch_wordpress({"url": "https://x/wp"}, get=lambda u, p: MUNGOS_FEED)
    gaps = boards.feed_gaps(feed, [held("Old Role", "old-role"), held("Gardening Group Volunteer")])
    assert gaps["gone"] == ["Old Role"]          # the listing-page link makes no claim


def test_a_malformed_or_partial_wordpress_feed_is_refused(monkeypatch):
    with pytest.raises(boards.BoardError):
        boards.fetch_wordpress({"url": "https://x/wp"}, get=lambda u, p: {"code": "rest_no_route"})
    with pytest.raises(boards.BoardError):
        boards.fetch_wordpress({"url": "https://x/wp"},
                               get=lambda u, p: [{"status": "publish", "title": {"rendered": ""}}])
    monkeypatch.setattr(boards, "WP_PER_PAGE", 1)
    with pytest.raises(boards.BoardError):       # never ends: refuse a partial read
        boards.fetch_wordpress({"url": "https://x/wp"}, get=lambda u, p: MUNGOS_FEED[:1])


def test_feed_params_are_sent():
    seen = []
    boards.fetch_wordpress({"url": "https://x/wp", "params": {"job_type": 124}},
                           get=lambda u, p: seen.append(dict(p)) or [])
    assert seen[0]["job_type"] == "124" and seen[0]["per_page"] == "100"


def test_org_schema_accepts_a_feed_and_the_data_files_that_use_it_validate():
    import glob
    for path in glob.glob("../data/orgs/*.json") + glob.glob("data/orgs/*.json"):
        validate(json.load(open(path, encoding="utf-8"))["organisation"], ORG_SCHEMA)


# ------------------------------------------------------------------ Better Impact (Shelter)
# Fixtures are the live London search and detail pages of 17 October 2026, trimmed
# to the fields the reader uses (GUIDs lengthened with zeros).

BI = "https://app.betterimpact.com"
ENT = "3649308b-8a14-4513-8a59-a4087e2a2ee8"
BI_BOARD = {"type": "betterimpact", "base_url": BI, "region": "london",
            "params": {"EnterpriseGuid": ENT, "SearchType": "SuitabilityClassification",
                       "SearchId": "3526"},
            "collapse": [{"match": r"\bshop$", "title": "Community Shop Volunteer", "id": "shops",
                          "url": BI + "/PublicEnterprise/EnterpriseSearch?x=1"}]}


def g(prefix):
    return prefix + "-0000-0000-0000-000000000000"


BI_ROLES = {
    g("7e531ffc"): ("Lived Experience Coordination Volunteer",
                    "Do you want to help?\n\nLocation: Hub/community/home based location, London.\n\n"
                    "Suggested contribution: Approximately 7 - 14 hours per month, flexible\n\n"
                    "Availability: at a time that suits you\n\n[Volunteering Team: please add any "
                    "relevant information about Criminal Record Checks here.]"),
    g("a349c694"): ("Crouch End Shop", "Location: Shop in Crouch End, N8 8PT\n\nAvailability: "
                    "The shop is open Monday - Saturday 10:00-18:00.\n\nSome roles involve a basic "
                    "criminal record check."),
    g("2d41a88a"): ("Highgate Shop", "Location: Shop in Highgate, N6 5HX\n\nAvailability: The shop "
                    "is open Monday - Saturday."),
    g("4ec25ece"): ("St Albans Shop", "Location: Shelter, 9 High Street, St Albans, Hertfordshire, "
                    "AL3 4ED\n\nAvailability: Coming early November."),
    g("b1fed740"): ("Volunteer Van Driver's Mate", "Location: South London\n\nThe Van Driver’s "
                    "Mate role can be any time between Monday-Friday."),
}


def bi_list(guids=None):
    lis = "".join(
        f'<li>\n    <a href="/PublicEnterprise/EnterpriseGvi?enterpriseGuid={ENT}&amp;gviGuid={gid}'
        f'&amp;searchUrl=https%253a%252f%252fapp.betterimpact.com" class="regularLink">{name} </a>\n'
        f'<button type="button" class="ui-icon">i</button></li>'
        for gid, (name, _) in BI_ROLES.items() if guids is None or gid in guids)
    return ("<html><head><title>MyImpactPage - Shelter - Search Volunteer Opportunities by Where "
            f"would you like to volunteer? - London</title></head><body><ul>{lis}</ul></body></html>")


def bi_detail(gid):
    name, text = BI_ROLES[gid]
    esc = text.replace("&", "&amp;").replace('"', "&quot;")
    return (f'<html><head><meta property="og:title" content="\n    {name} \n" />'
            f'<meta property="og:description" content="\n   {name}\n\n{esc}\n" /></head></html>')


def bi_get(calls=None, drop_detail=None):
    def get(url, params):
        if calls is not None:
            calls.append((url, dict(params)))
        if url.endswith("EnterpriseSearch"):
            return bi_list()
        gid = dict(params)["gviGuid"]
        if gid == drop_detail:
            return "<html>nothing</html>"
        return bi_detail(gid)
    return get


def bi_records(**kw):
    offers = boards.load_offers(BI_BOARD, get=bi_get(**kw))
    return boards.london_records(offers, "shelter", "2026-10-17T21:00:00+00:00",
                                 BI + "/x", collapse=BI_BOARD["collapse"])


def test_betterimpact_reads_each_opportunity_page_and_sends_the_enterprise_id():
    calls = []
    offers = boards.load_offers(BI_BOARD, get=bi_get(calls))
    assert [o.title for o in offers][:2] == ["Lived Experience Coordination Volunteer", "Crouch End Shop"]
    details = [c for c in calls if c[0].endswith("EnterpriseGvi")]
    assert len(details) == 5 and all(c[1]["enterpriseGuid"] == ENT for c in details)
    assert calls[0][1]["SearchId"] == "3526"


def test_betterimpact_uses_the_location_line_and_never_the_shop_opening_hours():
    offers = {o.title: o for o in boards.load_offers(BI_BOARD, get=bi_get())}
    lived = offers["Lived Experience Coordination Volunteer"]
    assert lived.address == "Hub/community/home based location, London."
    assert lived.timing == "Approximately 7 - 14 hours per month, flexible"
    assert offers["Crouch End Shop"].timing is None       # "open Monday - Saturday" is the shop's
    assert "placeholder" in lived.notes[0] and not offers["Highgate Shop"].notes


def test_a_shop_in_st_albans_is_set_aside_and_london_shops_become_one_role():
    records, aside = bi_records()
    assert aside == 1
    titles = sorted(r["title"] for r in records)
    assert titles == ["Community Shop Volunteer", "Lived Experience Coordination Volunteer",
                      "Volunteer Van Driver's Mate"]
    shop = next(r for r in records if r["title"] == "Community Shop Volunteer")
    assert "2 charity shops" in shop["what_youd_do"] and shop["id"] == "shelter-board-shops"
    assert shop["stated_places"] == ["London"] and shop["url_specificity"] == "org_volunteer_page"
    for r in records:
        validate(r, RECORD_SCHEMA)


def test_betterimpact_never_claims_a_disclosure_check_or_a_placeholder_as_fact():
    records, _ = bi_records()
    for r in records:
        assert r["screening"]["dbs"] == "unknown" and r["screening"]["interview"] is None
    lived = next(r for r in records if r["title"].startswith("Lived"))
    assert any("placeholder" in f for f in lived["provenance"]["unsupported_fields"])
    assert lived["stated_places"] == ["London"] and lived["apply_url"].endswith(g("7e531ffc"))


def test_betterimpact_refuses_a_partial_read_or_a_page_it_does_not_recognise():
    with pytest.raises(boards.BoardError):
        boards.load_offers(BI_BOARD, get=bi_get(drop_detail=g("2d41a88a")))
    with pytest.raises(boards.BoardError):
        boards.load_offers(BI_BOARD, get=lambda u, p: "<html>Sign in to continue</html>")
    with pytest.raises(boards.BoardError):
        boards.load_offers({**BI_BOARD, "params": {}}, get=bi_get())


def test_org_schema_accepts_the_betterimpact_board():
    doc = json.load(open(next(p for p in ("../data/orgs/shelter.json", "data/orgs/shelter.json")
                              if __import__("os").path.exists(p)), encoding="utf-8"))
    validate(doc["organisation"], ORG_SCHEMA)
    assert doc["organisation"]["board"]["type"] == "betterimpact"


# ------------------------------------------------------------------ Simply Volunteer London
# Cards copied from the live role search on 17 October 2026 (descriptions trimmed).

def svl_card(title, org, slug, tag="Hackney"):
    return ('<div class="card shadow-0 border rounded-3"><div class="card-body"><div class="row">'
            f'<div class="tag bg-success text-truncate">\n {tag}</div>'
            f'<h5 class="text-success">{title}</h5><span class="text-danger">Organisation :\n'
            f'    {org}</span><p class="text mb-4">Short text</p>'
            f'<a href="https://simplyvolunteerlondon.uk/role/{slug}">Details</a></div></div></div>')


def svl_page(*cards, next_page=None):
    nxt = f'<a href="roles-search?page={next_page}">next</a>' if next_page else ""
    return "<html><title>Find Volunteer Roles | Simply Volunteer London</title>" + "".join(cards) + nxt


SVL = {"type": "simplyvolunteer", "url": "https://simplyvolunteerlondon.uk/roles-search",
       "params": {"keyword": "Housing Justice", "organisation": "Housing Justice"}}


def test_only_cards_for_the_organisation_count_and_pages_are_followed():
    pages = {1: svl_page(svl_card("Volunteer Community Connector", "Housing Justice", "5247/22/hackney/vcc"),
                         svl_card("Walk Leader", "Walk+Talk", "5601/22/hackney/walk"), next_page=2),
             2: svl_page(svl_card("Citadel Mentor: Empowering Lives, Ending Homelessness",
                                  "Housing Justice", "3578/21/greenwich/citadel"))}
    seen = []

    def get(url, params):
        seen.append(dict(params))
        return pages[int(dict(params).get("page", 1))]
    roles = boards.fetch_feed(SVL, get=get)
    assert [r.title for r in roles] == ["Volunteer Community Connector",
                                        "Citadel Mentor: Empowering Lives, Ending Homelessness"]
    assert roles[0].link == "https://simplyvolunteerlondon.uk/role/5247/22/hackney/vcc"
    assert seen[0] == {"keyword": "Housing Justice"} and seen[1]["page"] == "2"


def test_an_organisation_with_no_roles_there_is_an_empty_answer_not_an_error():
    cfg = {**SVL, "params": {"keyword": "SHP", "organisation": "Single Homeless Project"}}
    assert boards.fetch_feed(cfg, get=lambda u, p: svl_page()) == []
    assert boards.fetch_feed(cfg, get=lambda u, p: svl_page(
        svl_card("Citizens Advice role", "Citizens Advice - Bromley", "1/2/x/y"))) == []


def test_simplyvolunteer_refuses_a_page_it_does_not_recognise_or_cannot_read():
    with pytest.raises(boards.BoardError):
        boards.fetch_feed(SVL, get=lambda u, p: "<html>Maintenance</html>")
    with pytest.raises(boards.BoardError):
        boards.fetch_feed(SVL, get=lambda u, p: svl_page('<div class="card shadow-0">broken</div>'))
    with pytest.raises(boards.BoardError):
        boards.fetch_feed({**SVL, "params": {"keyword": "x"}}, get=lambda u, p: svl_page())
    with pytest.raises(boards.BoardError):
        boards.fetch_feed({**SVL, "type": "rss"}, get=lambda u, p: svl_page())


def test_a_role_on_the_platform_that_we_do_not_hold_is_reported():
    feed = boards.fetch_feed(SVL, get=lambda u, p: svl_page(
        svl_card("Volunteer Community Connector", "Housing Justice", "5247/22/hackney/vcc"),
        svl_card("Citadel Mentor: Empowering Lives", "Housing Justice", "3578/21/greenwich/citadel")))
    held_roles = [{"title": "Citadel Volunteer", "apply_url": "https://housingjustice.org.uk/x"}]
    gaps = boards.feed_gaps(feed, held_roles)
    assert gaps["missing"] == ["Volunteer Community Connector", "Citadel Mentor: Empowering Lives"]
    assert boards.feed_gaps([], held_roles)["missing"] == []


def test_a_feed_failure_is_reported_and_never_changes_roles(tmp_path, monkeypatch):
    doc = crisis_doc([])
    doc["organisation"]["feed"] = SVL
    boom = lambda u, p: (_ for _ in ()).throw(boards.BoardError("board answered HTTP 503"))
    monkeypatch.setattr(runner, "fetch", lambda *a, **k: FetchResult(
        status="unchanged", text=None, content_hash="h", platforms=[]))
    path = tmp_path / "o.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = runner.process(path, doc, None, True, lambda o, r: [], feed_get=boom)
    assert report["feed_error"] == "board answered HTTP 503" and "feed_gaps" not in report
