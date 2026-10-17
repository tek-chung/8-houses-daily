"""The site build's own invariants, callable from the pipeline.

The build refuses to publish when a record would mislead a reader (spec §11.5,
site/build.py check()). Anything the pipeline writes must pass the same checks
*before* it is written. Otherwise one bad record stops the deploy, and because
the weekly refresh runs the site tests first, it stops the refresh as well. The
whole paper then freezes with nobody told. That happened between 8 and 16 October
2026, through a test fixture rather than a record, and nothing published since
reached a reader.
"""
from __future__ import annotations

import importlib.util
import sys

from config import ROOT

_build = None


def _load_build():
    global _build
    if _build is None:
        spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(ROOT / "site"))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(ROOT / "site"))
        _build = module
    return _build


def errors_for(org_id: str, errors: list[str], roles: list[dict]) -> list[str]:
    """The build's errors that concern one organisation.

    Errors are prefixed with the record id. Role ids do not always start with the
    organisation id ("watw-kitchen" belongs to women-at-the-well), so matching on
    the prefix let 20 roles' errors through unnoticed.
    """
    ids = {org_id} | {r.get("id") for r in roles if r.get("org_id") == org_id}
    return [e for e in errors if e.split(":", 1)[0] in ids]


def record_errors(org: dict, roles: list[dict]) -> list[str]:
    """Build invariants for one organisation's proposed records, checked in memory."""
    build = _load_build()
    from decay import compute
    return errors_for(org["id"], build.check({org["id"]: org}, roles, compute([org])), roles)


def site_errors(org_id: str) -> list[str]:
    """Build invariants over the data directory as it now stands, for one organisation."""
    build = _load_build()
    orgs, opps, fresh, _ = build.load()
    return errors_for(org_id, build.check(orgs, opps, fresh), opps)
