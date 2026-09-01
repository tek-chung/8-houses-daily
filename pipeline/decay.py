"""Graceful decay. Spec §11.5.

The failure mode this project is most likely to hit is not a bug — it is the
maintainer getting busy. So the site is built to notice its own neglect: at 21 days
it stops asserting things it can no longer stand behind, and at 60 days it says
plainly that nobody is looking after it.

This module writes data/freshness.json. The site reads it at build time. Nothing
here needs a network or a model, which is the point: decay must keep working after
everything else has stopped.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from config import (FRESHNESS_OUT, SITE_BANNER_AFTER_DAYS,
                    SUPPRESS_ASSERTIVE_AFTER_DAYS)

# Fields the site must stop showing once a record is stale. These are exactly the
# claims we cannot stand behind without a recent check.
ASSERTIVE_FIELDS = ["screening", "status", "next_intake", "specific_times"]


def _days_since(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0, (now - then).days)


def compute(orgs: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    per_org, ages = {}, []

    for org in orgs:
        check = org.get("check", {}) or {}
        age = _days_since(check.get("last_success"), now)
        link = check.get("link_status", "ok")

        if age is None:
            state, suppress = "never_checked", True
        elif age >= SUPPRESS_ASSERTIVE_AFTER_DAYS:
            state, suppress = "stale", True
        else:
            state, suppress = "fresh", False

        if link in ("dead", "link_only"):
            suppress = True

        per_org[org["id"]] = {
            "days_since_check": age,
            "state": state,
            "link_status": link,
            "suppress_assertive": suppress,
            "suppress_fields": ASSERTIVE_FIELDS if suppress else [],
        }
        if age is not None:
            ages.append(age)

    ages.sort()
    median = ages[len(ages) // 2] if ages else None
    oldest = ages[-1] if ages else None

    site_banner = (median is not None and median >= SITE_BANNER_AFTER_DAYS) \
        or (median is None and bool(orgs))

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "median_days_since_check": median,
        "oldest_days_since_check": oldest,
        "orgs_total": len(orgs),
        "orgs_suppressed": sum(1 for v in per_org.values()
                               if v["suppress_assertive"]),
        "site_banner": site_banner,
        "site_banner_copy": (
            "These listings aren't being kept up to date at the moment. Please check "
            "each charity's own page before relying on anything here — or try Reach "
            "Volunteering or the Homeless Link job board."
        ) if site_banner else None,
        "thresholds": {
            "suppress_assertive_after_days": SUPPRESS_ASSERTIVE_AFTER_DAYS,
            "site_banner_after_days": SITE_BANNER_AFTER_DAYS,
        },
        "orgs": per_org,
    }


def write(orgs: list[dict]) -> dict:
    report = compute(orgs)
    FRESHNESS_OUT.parent.mkdir(parents=True, exist_ok=True)
    FRESHNESS_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
