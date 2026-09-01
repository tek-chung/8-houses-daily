"""Tests for the gate. Run: python -m pytest pipeline/test_gate.py -q

The gate is the only thing standing between a model's output and a claim about
someone else's safeguarding requirements. These tests exist so that a future
refactor cannot quietly open that path.
"""
import pytest

from config import ROUTE_AUTO, ROUTE_REVIEW, CRITICAL_FIELDS
from gate import (classify_disappeared, classify_fetch_failure, classify_new,
                  classify_update, diff_fields, pair_roles, route_org)


def role(**over):
    base = {
        "title": "Kitchen shift",
        "what_youd_do": "Cook and serve lunch, then help clear down.",
        "commitment": "weekly",
        "min_term_months": None,
        "typical_shift_hours": 3,
        "when": ["weekend_daytime"],
        "specific_times": "Saturdays 9am to noon",
        "activity": "cooking_serving",
        "location_type": "in_person",
        "postcode_district": "SE1",
        "screening": {"dbs": "none", "references": False, "interview": False,
                      "min_age": 18, "induction": "Trial shift first"},
        "skills": [],
        "seasonal_window": None,
        "next_intake": None,
        "status": "open",
        "apply_url": "https://example.org/volunteer",
        "url_specificity": "role",
    }
    screening = over.pop("screening", None)
    base.update(over)
    if screening:
        base["screening"] = {**base["screening"], **screening}
    return base


# --------------------------------------------------------------- critical fields

@pytest.mark.parametrize("change", [
    {"screening": {"dbs": "enhanced"}},
    {"screening": {"dbs": "unknown"}},
    {"screening": {"min_age": 21}},
    {"screening": {"references": True}},
    {"screening": {"interview": True}},
    {"screening": {"induction": "Two-day training"}},
    {"status": "closed"},
    {"status": "oversubscribed"},
    {"next_intake": "2026-10-01"},
])
def test_critical_change_never_auto_publishes(change):
    """No confidence score sends a critical change down the auto path."""
    d = classify_update(role(), role(**change), confidence=1.0)
    assert d.route == ROUTE_REVIEW


def test_every_declared_critical_field_is_actually_gated():
    """Guards against a field being added to CRITICAL_FIELDS but never compared."""
    values = {"screening.dbs": "enhanced", "screening.references": True,
              "screening.interview": True, "screening.min_age": 25,
              "screening.induction": "New training", "status": "closed",
              "next_intake": "2027-01-01"}
    assert set(values) == set(CRITICAL_FIELDS), "test fixture out of sync with config"
    for dotted, val in values.items():
        new = role()
        if "." in dotted:
            outer, inner = dotted.split(".")
            new[outer] = {**new[outer], inner: val}
        else:
            new[dotted] = val
        assert classify_update(role(), new, 1.0).route == ROUTE_REVIEW, dotted


# --------------------------------------------------------------- non-critical

def test_no_change_auto_publishes():
    assert classify_update(role(), role(), 0.99).route == ROUTE_AUTO


def test_description_change_auto_publishes_when_confident():
    d = classify_update(role(), role(what_youd_do="Serve lunch and wash up after."),
                        confidence=0.93)
    assert d.route == ROUTE_AUTO
    assert d.changed_fields == ["what_youd_do"]


def test_low_confidence_routes_to_review():
    d = classify_update(role(), role(typical_shift_hours=4), confidence=0.5)
    assert d.route == ROUTE_REVIEW


def test_none_confidence_routes_to_review():
    """Fails closed rather than treating a missing score as passing."""
    assert classify_update(role(), role(skills=["cooking"]), None).route == ROUTE_REVIEW


def test_shift_hours_change_is_not_critical():
    d = classify_update(role(), role(typical_shift_hours=4), confidence=0.95)
    assert d.route == ROUTE_AUTO


# --------------------------------------------------------------- lifecycle

def test_new_role_always_reviewed():
    assert classify_new(role(), confidence=1.0).route == ROUTE_REVIEW


def test_disappeared_role_reviewed_not_deleted():
    d = classify_disappeared(role())
    assert d.route == ROUTE_REVIEW
    assert "status" in d.changed_fields


def test_fetch_failure_below_threshold_retries_quietly():
    assert classify_fetch_failure(1, threshold=2).route == ROUTE_AUTO


def test_fetch_failure_at_threshold_reviewed():
    assert classify_fetch_failure(2, threshold=2).route == ROUTE_REVIEW


# --------------------------------------------------------------- pairing

def test_reworded_title_pairs_rather_than_churning():
    old = [role(title="Kitchen shift")]
    new = [role(title="Kitchen shifts")]
    pairs, added, gone = pair_roles(old, new)
    assert len(pairs) == 1 and not added and not gone


def test_genuinely_different_role_is_treated_as_new():
    pairs, added, gone = pair_roles([role(title="Kitchen shift")],
                                    [role(title="Trustee")])
    assert not pairs and len(added) == 1 and len(gone) == 1


def test_one_new_one_kept():
    old = [role(title="Kitchen shift")]
    new = [role(title="Kitchen shift"), role(title="Charity shop assistant")]
    pairs, added, gone = pair_roles(old, new)
    assert len(pairs) == 1 and len(added) == 1 and not gone


# --------------------------------------------------------------- org routing

def test_empty_extraction_is_reviewed_not_published():
    """A page that returns nothing must never silently wipe an org's roles."""
    route, decisions = route_org([role()], [], confidence=0.99)
    assert route == ROUTE_REVIEW


def test_no_roles_either_side_is_reviewed():
    route, _ = route_org([], [], confidence=0.99)
    assert route == ROUTE_REVIEW


def test_one_critical_change_holds_back_the_whole_page():
    old = [role(title="Kitchen shift"), role(title="Trustee")]
    new = [role(title="Kitchen shift", screening={"dbs": "enhanced"}),
           role(title="Trustee")]
    route, _ = route_org(old, new, confidence=0.99)
    assert route == ROUTE_REVIEW


def test_clean_page_auto_publishes():
    old = [role(title="Kitchen shift")]
    new = [role(title="Kitchen shift", what_youd_do="Cook lunch and clear down after.")]
    route, _ = route_org(old, new, confidence=0.95)
    assert route == ROUTE_AUTO


# --------------------------------------------------------------- diffing

def test_provenance_is_not_a_material_change():
    old, new = role(), role()
    old["provenance"] = {"confidence": 0.9}
    new["provenance"] = {"confidence": 0.4}
    assert diff_fields(old, new) == []


def test_list_order_is_not_a_material_change():
    a = role(when=["weekend_daytime", "flexible"])
    b = role(when=["flexible", "weekend_daytime"])
    assert diff_fields(a, b) == []
