"""Schemas. Spec §10.1, §10.2.

Two schemas, deliberately different:

  EXTRACTION_SCHEMA  what the model is allowed to return
  RECORD_SCHEMA      what gets written to disk

The model never supplies id, org_id, coords or provenance. Those are assigned by
the pipeline. Keeping them out of the model's reach means a bad extraction cannot
rename a record, reassign it to another charity, move it on a map, or mark itself
as human-reviewed.
"""

# "unknown" added after Phase 0. dbs, status and who_can_apply all have one;
# commitment did not, so "their page does not say how often" was being filed as
# "flexible" — 5 of 18 flexible roles were really unknowns. That matters because
# flexible is a promise (you choose, so any frequency works) while unknown is an
# absence, and they behave oppositely behind a door: flexible belongs in all of
# them, unknown in none. Same reasoning as activity: "varies".
COMMITMENTS = ["one_off", "flexible", "weekly", "fortnightly", "monthly",
               "long_term", "unknown"]
WHEN = ["weekday_daytime", "weekday_evening", "weekend_daytime",
        "weekend_evening", "overnight", "flexible"]
# "varies" added after Phase 0: HandsOn London runs a rotating calendar of one-off
# projects rather than fixed roles. Picking one activity would be a fabrication.
# Roles marked "varies" appear when no activity filter is set and are excluded when
# one is, because we cannot promise a match we can't support.
# "practical" added after Phase 0: Providence Row runs a rooftop garden, and
# gardening, decorating and maintenance recur across charity day-lists. None of
# the other twelve activities describes it — shop_warehouse is a shop floor or a
# stockroom — so someone looking for outdoor work would never find it.
ACTIVITIES = ["cooking_serving", "befriending", "outreach", "advice", "mentoring",
              "teaching", "shop_warehouse", "practical", "admin", "fundraising",
              "campaigning", "hosting", "governance", "varies"]
# "required_unspecified" added after Phase 0: Depaul's Nightstop pages confirm a DBS
# check is required but never say which level. Collapsing that to "unknown" loses
# the actionable half of the fact — "you will definitely need a check" is very
# different guidance from "we don't know whether you need one".
DBS = ["none", "basic", "enhanced", "required_unspecified", "unknown"]
STATUS = ["open", "closed", "oversubscribed", "seasonal_closed", "unknown"]
# "own_home" added after Phase 0: Nightstop hosting happens at the volunteer's own
# address, so travel time is meaningless and the reach filter must not exclude it.
# Modelling it as "remote" would match correctly but describe it wrongly.
LOCATION_TYPES = ["in_person", "remote", "hybrid", "own_home"]
URL_SPECIFICITY = ["role", "org_volunteer_page", "org_homepage"]
WHO_CAN_APPLY = ["individual", "team_only", "either", "unknown"]

_SCREENING = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dbs", "references", "interview", "min_age", "induction"],
    "properties": {
        "dbs": {"type": "string", "enum": DBS},
        "references": {"type": ["boolean", "null"]},
        "interview": {"type": ["boolean", "null"]},
        "min_age": {"type": ["integer", "null"], "minimum": 13, "maximum": 80},
        "induction": {"type": ["string", "null"], "maxLength": 120},
    },
}

_OPPORTUNITY_CORE = {
    "title": {"type": "string", "minLength": 2, "maxLength": 80},
    "what_youd_do": {"type": "string", "minLength": 15, "maxLength": 220},
    "commitment": {"type": "string", "enum": COMMITMENTS},
    "min_term_months": {"type": ["integer", "null"], "minimum": 1, "maximum": 60},
    "typical_shift_hours": {"type": ["number", "null"], "minimum": 0.5, "maximum": 24},
    "when": {"type": "array", "items": {"type": "string", "enum": WHEN},
             "minItems": 1, "maxItems": 3},
    "specific_times": {"type": ["string", "null"], "maxLength": 80},
    "activity": {"type": "string", "enum": ACTIVITIES},
    "location_type": {"type": "string", "enum": LOCATION_TYPES},
    # Added after Phase 0 reconnaissance: Whitechapel Mission accepts no individual
    # volunteers at all, teams only. Listing such a role without saying so sends
    # individuals to be turned away — exactly the harm this site exists to prevent.
    "who_can_apply": {"type": "string", "enum": WHO_CAN_APPLY},
    "postcode_district": {"type": ["string", "null"],
                          "pattern": "^[A-Z]{1,2}[0-9][0-9A-Z]?$"},
    # The towns, cities or London boroughs the page names for THIS role, exactly as
    # written ("Bournemouth", "Hackney"). Added after St Mungo's Outreach Volunteer,
    # which the page offers in Bournemouth and Reading only, was shown as a London
    # role because it silently inherited the charity's boroughs. Every entry must
    # occur verbatim in the page (extract.check_places); a role whose places are all
    # outside London is kept in the data but not shown. Empty = the page names none.
    "stated_places": {"type": "array", "maxItems": 8,
                      "items": {"type": "string", "minLength": 2, "maxLength": 60}},
    "screening": _SCREENING,
    "skills": {"type": "array", "items": {"type": "string", "maxLength": 40},
               "maxItems": 6},
    # Who may apply, as distinct from what they can do. Added after Women at the
    # Well: "we are a women-only service and can only accept applications from
    # women", with the statutory exemption cited. That was being crammed into
    # `skills`, where it read as a competence and would have shown up beside
    # "cooking" in a skills filter. Groundswell's requirement for lived
    # experience and Nightstop's for a spare room are the same shape: a bar on
    # who is eligible, not a description of ability. Longer cap than skills
    # because these often need a clause to be honest.
    "eligibility": {"type": "array",
                    "items": {"type": "string", "maxLength": 100},
                    "maxItems": 4},
    "seasonal_window": {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": ["start_month", "end_month"],
        "properties": {
            "start_month": {"type": "integer", "minimum": 1, "maximum": 12},
            "end_month": {"type": "integer", "minimum": 1, "maximum": 12},
        },
    },
    "next_intake": {"type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "status": {"type": "string", "enum": STATUS},
    "apply_url": {"type": ["string", "null"], "pattern": "^https?://"},
    "url_specificity": {"type": "string", "enum": URL_SPECIFICITY},
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["roles"],
    "properties": {
        "roles": {
            "type": "array",
            "maxItems": 15,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_OPPORTUNITY_CORE.keys()),
                "properties": _OPPORTUNITY_CORE,
            },
        },
        "page_notes": {
            "type": ["string", "null"],
            "maxLength": 300,
            "description": "Anything a human reviewer should know. Not published.",
        },
    },
}

_PROVENANCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["extracted_at", "method", "reviewed_by_human", "confidence",
                 "source_url"],
    "properties": {
        "extracted_at": {"type": "string"},
        # "platform": read from fields of the charity's own volunteering platform.
        "method": {"type": "string", "enum": ["llm", "human", "placeholder", "platform"]},
        "reviewed_by_human": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_url": {"type": "string"},
        "verified_fields": {"type": "array", "items": {"type": "string"}},
        "unsupported_fields": {"type": "array", "items": {"type": "string"}},
    },
}

RECORD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    # stated_places is optional on stored records: records written before it
    # existed simply have none, which means "the page named no place".
    "required": [k for k in _OPPORTUNITY_CORE if k != "stated_places"]
                + ["id", "org_id", "provenance"],
    "properties": {
        **_OPPORTUNITY_CORE,
        "id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "org_id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "coords": {"type": ["array", "null"], "items": {"type": "number"},
                   "minItems": 2, "maxItems": 2},
        # Hand-curated, never extracted (so not in _OPPORTUNITY_CORE and invisible to
        # the model and the gate). Both record what the charity's own page says about
        # a role that has no single postcode:
        #   role_zones  - browsing-area ids the page names ("north, north-east and
        #                 south-east London"), for roles that span several areas.
        #   london_wide - the page says the role runs across London.
        "role_zones": {"type": "array", "uniqueItems": True, "maxItems": 7,
                       "items": {"type": "string",
                                 "enum": ["central", "north", "north-west", "east",
                                          "south-east", "south-west", "west"]}},
        "london_wide": {"type": "boolean"},
        "provenance": _PROVENANCE,
    },
}

ORG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "name", "website_url", "volunteer_url", "check"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "name": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "charity_number": {"type": ["string", "null"]},
        "website_url": {"type": "string"},
        "volunteer_url": {"type": "string"},
        "summary": {"type": ["string", "null"], "maxLength": 200},
        "coverage": {"type": "string",
                     "enum": ["borough", "multi_borough", "london_wide"]},
        "boroughs": {"type": "array", "items": {"type": "string"}},
        "focus_groups": {"type": "array", "items": {"type": "string"}},
        # A charity whose roles live on a platform the page does not render (see
        # pipeline/boards.py). Roles are then read from the platform's own feed.
        "board": {"type": "object", "additionalProperties": False,
                  "required": ["type", "base_url"],
                  "properties": {"type": {"type": "string", "enum": ["rosterfy", "assemble"]},
                                 "base_url": {"type": "string", "pattern": "^https://"},
                                 "region": {"type": "string", "enum": ["london"]}}},
        # Platform hosts a person has looked at and decided not to read automatically
        # (they stop being reported as unread roles).
        "platforms_acknowledged": {"type": "array", "items": {"type": "string"}},
        "lived_experience_roles": {"type": "boolean"},
        "robots_allowed": {"type": "boolean"},
        "check": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "last_attempt": {"type": ["string", "null"]},
                "last_success": {"type": ["string", "null"]},
                "last_extraction": {"type": ["string", "null"]},
                "link_status": {"type": "string",
                                "enum": ["ok", "redirected", "dead", "link_only"]},
                "content_hash": {"type": ["string", "null"]},
                "consecutive_failures": {"type": "integer", "minimum": 0},
                "etag": {"type": ["string", "null"]},
                "last_modified": {"type": ["string", "null"]},
            },
        },
    },
}

# Tool definition for the Anthropic Messages API. Forcing tool use is how we get
# schema-shaped output instead of prose we have to parse.
EXTRACTION_TOOL = {
    "name": "record_roles",
    "description": (
        "Record the volunteering roles described on this page. Return only roles "
        "the page actually describes. Use the literal string 'unknown' or null "
        "rather than inferring anything the page does not state."
    ),
    "input_schema": EXTRACTION_SCHEMA,
}
