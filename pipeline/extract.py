"""Extraction. Spec §11.2.

Three things happen here, and only the first is the obvious one.

1. Extract. Forced tool use against EXTRACTION_SCHEMA, so we get schema-shaped
   output rather than prose to parse.

2. Verify the critical fields against the source text. A model's self-reported
   confidence is weakly calibrated and easy to be optimistic about, so we don't ask
   for one. Instead a second pass is shown each critical claim alongside the page
   and asked whether the page actually supports it. Anything unsupported is forced
   to unknown before it can reach the gate. Confidence is then *derived* from the
   proportion of critical claims that survived — an observable, not an opinion.

3. Check for reproduction. Prompt instructions are necessary but not sufficient, so
   the paraphrase rule is enforced mechanically: any shared verbatim run of
   MAX_VERBATIM_SHINGLE words with the source page fails the extraction.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from jsonschema import ValidationError, validate

from config import (MAX_TOKENS, MAX_VERBATIM_SHINGLE, MODEL_ESCALATE,
                    MODEL_PRIMARY)
from schema import EXTRACTION_SCHEMA, EXTRACTION_TOOL

PROMPT = (Path(__file__).parent / "prompts" / "extract.md").read_text(encoding="utf-8")

CRITICAL_CLAIMS = [
    ("screening.dbs", "the DBS or criminal record check required"),
    ("screening.min_age", "the minimum age"),
    ("screening.references", "whether references are required"),
    ("screening.interview", "whether an interview is required"),
    ("screening.induction", "the induction or training required"),
    ("status", "whether the role is currently open to new volunteers"),
    ("next_intake", "the date of the next intake"),
]

UNKNOWN_FOR = {"screening.dbs": "unknown", "status": "unknown"}


@dataclass
class Extraction:
    roles: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    page_notes: str | None = None
    verified: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    error: str | None = None
    model_used: str | None = None


# --------------------------------------------------------------- copyright guard

def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shingles(text: str, n: int) -> set[tuple[str, ...]]:
    w = _words(text)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def reproduces_source(candidate: str, source: str,
                      n: int = MAX_VERBATIM_SHINGLE) -> tuple[str, ...] | None:
    """Return the first verbatim n-word run shared with the source, or None."""
    if len(_words(candidate)) < n:
        return None
    src = _shingles(source, n)
    for sh in _shingles(candidate, n):
        if sh in src:
            return sh
    return None


# --------------------------------------------------------------- field access

def _get(rec: dict, dotted: str):
    cur = rec
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set(rec: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = rec
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


# --------------------------------------------------------------- model calls

def _call(client, model: str, system: str, user: str, tool: dict | None):
    kwargs = dict(model=model, max_tokens=MAX_TOKENS, system=system,
                  messages=[{"role": "user", "content": user}])
    if tool:
        kwargs["tools"] = [tool]
        kwargs["tool_choice"] = {"type": "tool", "name": tool["name"]}
    return client.messages.create(**kwargs)


def _tool_input(response) -> dict | None:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    return None


def _extract_once(client, model: str, org_name: str, url: str,
                  page_text: str) -> tuple[dict | None, str | None]:
    user = (f"Charity: {org_name}\nPage: {url}\n\n"
            f"--- page text begins ---\n{page_text}\n--- page text ends ---")
    try:
        resp = _call(client, model, PROMPT, user, EXTRACTION_TOOL)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    data = _tool_input(resp)
    if data is None:
        return None, "model returned no tool call"
    try:
        validate(data, EXTRACTION_SCHEMA)
    except ValidationError as exc:
        return None, f"schema validation failed: {exc.message}"
    return data, None


# --------------------------------------------------------------- verification

VERIFY_SYSTEM = """You are checking whether a page supports specific factual claims.

For each claim you will be given a field, what it means, and the value that was
extracted. Decide whether the page text genuinely states or clearly implies that
value. Be strict: absence of contradiction is not support. If the page is silent on
something, the claim is NOT supported.

A value of "unknown" or null is always supported — it asserts nothing.

Reply with a JSON object only, no prose: {"field": true|false, ...} using the exact
field names given."""


def _verify(client, url: str, page_text: str,
            role: dict) -> tuple[list[str], list[str], str | None]:
    claims = {}
    for dotted, meaning in CRITICAL_CLAIMS:
        val = _get(role, dotted)
        if val in (None, "unknown"):
            continue          # asserts nothing, nothing to verify
        claims[dotted] = (meaning, val)

    if not claims:
        return [], [], None

    lines = "\n".join(f"- {f}: {meaning} — extracted value: {json.dumps(v)}"
                      for f, (meaning, v) in claims.items())
    user = (f"Role: {role.get('title')}\nPage: {url}\n\nClaims to check:\n{lines}\n\n"
            f"--- page text begins ---\n{page_text}\n--- page text ends ---")
    try:
        resp = _call(client, MODEL_PRIMARY, VERIFY_SYSTEM, user, None)
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        verdicts = json.loads(m.group(0)) if m else {}
    except Exception as exc:
        # Verification failing is not permission to publish. Treat every claim as
        # unsupported so the gate sees low confidence and routes to review.
        return [], list(claims), f"verification failed: {type(exc).__name__}: {exc}"

    ok = [f for f in claims if verdicts.get(f) is True]
    bad = [f for f in claims if f not in ok]
    return ok, bad, None


def extract(client, org_name: str, url: str, page_text: str) -> Extraction:
    """Extract, verify, and derive confidence. Never raises."""
    data, err = _extract_once(client, MODEL_PRIMARY, org_name, url, page_text)
    model_used = MODEL_PRIMARY
    if data is None:
        data, err2 = _extract_once(client, MODEL_ESCALATE, org_name, url, page_text)
        model_used = MODEL_ESCALATE
        if data is None:
            return Extraction(error=f"{err} / escalated: {err2}")

    roles = data.get("roles", [])
    notes = data.get("page_notes")

    # Copyright guard, before anything else is done with the text.
    for r in roles:
        hit = reproduces_source(r.get("what_youd_do", ""), page_text)
        if hit:
            return Extraction(
                error="extraction reproduced source text verbatim: "
                      f"{' '.join(hit)!r} in role {r.get('title')!r}",
                page_notes=notes)

    all_ok, all_bad, verify_errs = [], [], []
    for r in roles:
        ok, bad, verr = _verify(client, url, page_text, r)
        if verr:
            verify_errs.append(verr)
        for f in bad:
            _set(r, f, UNKNOWN_FOR.get(f))     # demote unsupported claims
        all_ok += [f"{r.get('title')}::{f}" for f in ok]
        all_bad += [f"{r.get('title')}::{f}" for f in bad]

    checked = len(all_ok) + len(all_bad)
    confidence = 1.0 if checked == 0 else round(len(all_ok) / checked, 3)
    if verify_errs:
        confidence = 0.0

    if notes and verify_errs:
        notes = f"{notes} | {'; '.join(verify_errs)}"
    elif verify_errs:
        notes = "; ".join(verify_errs)

    return Extraction(roles=roles, confidence=confidence, page_notes=notes,
                      verified=all_ok, unsupported=all_bad, model_used=model_used)


def finalise(role: dict, org_id: str, url: str, confidence: float,
             verified: list[str], unsupported: list[str]) -> dict:
    """Attach the fields the model is not allowed to supply. Spec §10.2."""
    slug = re.sub(r"[^a-z0-9]+", "-", role["title"].lower()).strip("-")[:48]
    return {
        **role,
        "id": f"{org_id}-{slug}",
        "org_id": org_id,
        "coords": None,
        "provenance": {
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": "llm",
            "reviewed_by_human": False,
            "confidence": confidence,
            "source_url": url,
            "verified_fields": verified,
            "unsupported_fields": unsupported,
        },
    }
