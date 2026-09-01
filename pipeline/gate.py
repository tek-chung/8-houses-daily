"""The gate. Spec §11.3.

This is the safety-critical component. It decides what reaches a visitor without a
human looking at it. Three properties it must have:

  1. Pure. No I/O, no network, no clock. Given the same records it always returns
     the same routing, so it can be tested exhaustively.
  2. Fails closed. Anything it cannot classify goes to review. There is no path
     where an unrecognised change auto-publishes.
  3. Critical fields are absolute. No confidence score, no change size, and no
     configuration flag can send a screening, status or next_intake change down
     the auto path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from config import (CONFIDENCE_THRESHOLD, CRITICAL_FIELDS, ROUTE_AUTO,
                    ROUTE_REVIEW)

TITLE_MATCH_THRESHOLD = 0.72


@dataclass
class Decision:
    route: str
    reasons: list[str] = field(default_factory=list)
    changed_fields: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.route == ROUTE_REVIEW


def _flatten(rec: dict, prefix: str = "") -> dict:
    """Flatten to dotted keys so 'screening.dbs' is directly comparable."""
    out = {}
    for k, v in rec.items():
        if k in ("provenance", "id", "org_id", "coords"):
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, f"{key}."))
        elif isinstance(v, list):
            out[key] = tuple(sorted(str(x) for x in v))
        else:
            out[key] = v
    return out


def diff_fields(old: dict, new: dict) -> list[str]:
    fo, fn = _flatten(old), _flatten(new)
    keys = set(fo) | set(fn)
    return sorted(k for k in keys if fo.get(k) != fn.get(k))


def touches_critical(changed: list[str]) -> list[str]:
    return [c for c in changed if c in CRITICAL_FIELDS]


def classify_update(old: dict, new: dict, confidence: float) -> Decision:
    """An existing role, re-extracted."""
    changed = diff_fields(old, new)
    if not changed:
        return Decision(ROUTE_AUTO, ["no material change"], [])

    crit = touches_critical(changed)
    if crit:
        return Decision(ROUTE_REVIEW,
                        [f"critical field changed: {', '.join(crit)}"], changed)

    if confidence is None or confidence < CONFIDENCE_THRESHOLD:
        return Decision(ROUTE_REVIEW,
                        [f"confidence {confidence!r} below {CONFIDENCE_THRESHOLD}"],
                        changed)

    unknown = [f for f in CRITICAL_FIELDS
               if _flatten(new).get(f) in (None, "unknown")
               and _flatten(old).get(f) not in (None, "unknown")]
    if unknown:
        return Decision(ROUTE_REVIEW,
                        ["a previously known critical field became unknown: "
                         + ", ".join(sorted(unknown))], changed)

    return Decision(ROUTE_AUTO, ["non-critical fields only, confidence ok"], changed)


def classify_new(new: dict, confidence: float) -> Decision:
    """A role that wasn't in the last snapshot. Always reviewed. Spec §11.3."""
    return Decision(ROUTE_REVIEW, ["new role detected"], sorted(_flatten(new)))


def classify_disappeared(old: dict) -> Decision:
    """A role that vanished from the page.

    We do not delete it and we do not assert it closed — the page may simply have
    been restructured. We demote it to unknown and ask a human.
    """
    return Decision(ROUTE_REVIEW,
                    ["role no longer found on page; status set to unknown"],
                    ["status"])


def classify_fetch_failure(consecutive_failures: int, threshold: int) -> Decision:
    if consecutive_failures >= threshold:
        return Decision(ROUTE_REVIEW,
                        [f"fetch failed {consecutive_failures} times; link marked dead"],
                        ["check.link_status"])
    return Decision(ROUTE_AUTO,
                    [f"fetch failed ({consecutive_failures}); retrying next run"],
                    ["check.last_attempt"])


def pair_roles(old_roles: list[dict], new_roles: list[dict]
               ) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Match old roles to new ones.

    Titles are how roles are identified on a page, and titles get reworded. Pairing
    on exact title would report every rewording as one role removed plus one added,
    which floods review and loses history. So pair on title similarity, greedily,
    best match first.

    Returns (pairs, added, disappeared).
    """
    scores = []
    for i, o in enumerate(old_roles):
        for j, n in enumerate(new_roles):
            s = SequenceMatcher(None, o.get("title", "").lower(),
                                n.get("title", "").lower()).ratio()
            if s >= TITLE_MATCH_THRESHOLD:
                scores.append((s, i, j))
    scores.sort(reverse=True)

    used_o, used_n, pairs = set(), set(), []
    for s, i, j in scores:
        if i in used_o or j in used_n:
            continue
        used_o.add(i)
        used_n.add(j)
        pairs.append((old_roles[i], new_roles[j]))

    added = [n for j, n in enumerate(new_roles) if j not in used_n]
    gone = [o for i, o in enumerate(old_roles) if i not in used_o]
    return pairs, added, gone


def route_org(old_roles: list[dict], new_roles: list[dict],
              confidence: float) -> tuple[str, list[Decision]]:
    """Overall route for one organisation's page. Any single review wins."""
    pairs, added, gone = pair_roles(old_roles, new_roles)
    decisions = [classify_update(o, n, confidence) for o, n in pairs]
    decisions += [classify_new(n, confidence) for n in added]
    decisions += [classify_disappeared(o) for o in gone]

    if not decisions:
        return ROUTE_REVIEW, [Decision(ROUTE_REVIEW,
                                       ["no roles found on page at all"], [])]
    route = ROUTE_REVIEW if any(d.needs_review for d in decisions) else ROUTE_AUTO
    return route, decisions
