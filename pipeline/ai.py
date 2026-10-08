"""Bounded structured AI for scheduled jobs. No browser code, keys or paid fallback.

Daily reservations are atomic locally. CI checkpoints a whole run's allowance to
Git before its first request, retaining the reservation even if the runner dies.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from jsonschema import Draft202012Validator, ValidationError, validate

from config import ROOT, STATE

# Two models with separate free-tier quotas (500 requests/day each in October 2026).
# A 'latest' alias would add nothing: it can resolve to the primary model.
DEFAULT_GEMINI_MODELS = 'gemini-3.5-flash-lite,gemini-3.1-flash-lite'
# A full pass is ~110 calls (one extraction per page, one verification per role).
# 6 s between calls keeps 60k-character pages under the 250k tokens/minute limit.
DEFAULT_LIMITS = {'gemini': ('150', '6000'), 'openrouter': ('20', '5000')}
DEFAULT_RUN_CALLS = '150'
DEFAULT_MAX_INPUT_BYTES = 262144  # accommodates the fetcher's 60,000-char cap + schema

class AIUnavailable(Exception):
    """Expected provider/quota failure; existing records must be retained."""


# Gemini's structured output accepts only part of JSON Schema, and rejects a whole
# request with HTTP 400 "Request contains an invalid argument" otherwise. Found by
# `python pipeline/ai.py schema-check` on 8 October 2026: string length/pattern
# keywords and array minItems/maxItems are rejected on 3.5 Flash-Lite, although
# the documentation lists the latter. They are removed from what Gemini receives
# and restated as descriptions, so the model still sees the limits; every response
# is still validated locally against the full schema.
_GEMINI_UNSUPPORTED = frozenset({'minLength', 'maxLength', 'pattern', 'uniqueItems',
                                 'minItems', 'maxItems', '$schema', '$id', '$comment'})


def _limits_note(schema: dict) -> str | None:
    notes = []
    lo, hi = schema.get('minItems'), schema.get('maxItems')
    if lo is not None and hi is not None:
        notes.append(f'{lo} to {hi} items.')
    elif hi is not None:
        notes.append(f'At most {hi} items.')
    elif lo is not None:
        notes.append(f'At least {lo} items.')
    if schema.get('maxLength') is not None:
        notes.append(f"At most {schema['maxLength']} characters.")
    return ' '.join(notes) or None


def gemini_schema(schema):
    """Project a JSON Schema onto the keywords Gemini accepts, keeping limits as text."""
    if isinstance(schema, dict):
        out = {}
        for key, value in schema.items():
            if key in _GEMINI_UNSUPPORTED:
                continue
            if key == 'properties' and isinstance(value, dict):
                out[key] = {name: gemini_schema(sub) for name, sub in value.items()}
            else:
                out[key] = gemini_schema(value)
        note = _limits_note(schema)
        if note and note not in out.get('description', ''):
            out['description'] = f"{out['description']} {note}" if out.get('description') else note
        return out
    if isinstance(schema, list):
        return [gemini_schema(item) for item in schema]
    return schema


_SECRETISH = re.compile(r'[A-Za-z0-9_\-]{24,}')


def provider_message(response) -> str | None:
    """A short, redacted error summary. Never the raw body; never anything key-like."""
    try:
        error = response.json().get('error')
    except (ValueError, AttributeError):
        return None
    if isinstance(error, dict):
        parts = [str(error.get('status') or error.get('code') or ''), str(error.get('message') or '')]
    elif isinstance(error, str):
        parts = [error]
    else:
        return None
    text = ' '.join(' '.join(p for p in parts if p).split())
    return _SECRETISH.sub('[redacted]', text)[:200] or None


def utc_day():
    return datetime.now(timezone.utc).date().isoformat()


class ProviderFailure(Exception):
    def __init__(self, kind: str, status: int | None = None, retry_after: float = 0,
                 message: str | None = None):
        self.kind, self.status, self.retry_after = kind, status, retry_after
        self.message = message  # redacted summary only, see provider_message()
        super().__init__(kind)  # never include provider response bodies or keys


@dataclass(frozen=True)
class Provider:
    name: str
    models: tuple[str, ...]
    key: str = field(repr=False)
    confirmed_free: bool = False
    daily_calls: int = 20
    interval: float = 5.0
    estimated_cost: float = 0.0


@dataclass
class Result:
    json: dict
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class Ledger:
    def __init__(self, path: Path, checkpoint: Callable | None = None):
        self.path, self.checkpoint = path, checkpoint

    def reserve(self, provider: Provider, calls: int, daily_usd: float) -> int:
        """Reserve up to `calls` from today's allowance; return how many were granted.

        Granting only what is left (rather than all-or-nothing) matters for a second
        run on the same UTC day: run #8 asked for 150 with 130 left and got none.
        """
        if (not math.isfinite(provider.estimated_cost) or provider.estimated_cost < 0
                or not math.isfinite(daily_usd) or daily_usd < 0):
            raise ValueError('Invalid AI price or budget')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        deadline = time.monotonic() + 10
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise AIUnavailable('usage ledger is locked; no request sent')
                time.sleep(0.05)
        try:
            data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
            day = utc_day()
            usage = data.setdefault(day, {'providers': {}, 'reserved_usd': 0.0})
            used = usage['providers'].get(provider.name, 0)
            grant = min(calls, provider.daily_calls - used)
            if provider.estimated_cost > 0:
                spare = daily_usd - usage['reserved_usd']
                grant = min(grant, math.floor(spare / provider.estimated_cost + 1e-9))
            if grant < 1:
                raise AIUnavailable('daily AI allowance exhausted; no request sent')
            cost = provider.estimated_cost * grant
            usage['providers'][provider.name] = used + grant
            usage['reserved_usd'] += cost
            pending = self.path.with_suffix('.tmp')
            pending.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            os.replace(pending, self.path)
            if self.checkpoint:
                self.checkpoint()  # failure prevents all subsequent network calls
        finally:
            lock.unlink()
        return grant


def git_checkpoint():
    """Only the authorised CI job uses its ordinary checkout authentication."""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('Git usage checkpoints are restricted to GitHub Actions')
    branch = os.environ['GITHUB_REF_NAME']
    commands = [
        ['git', 'add', 'pipeline/state/ai_usage.json'],
        ['git', 'diff', '--cached', '--name-only'],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    if result.stdout.strip() != 'pipeline/state/ai_usage.json':
        raise AIUnavailable('usage checkpoint contained unexpected staged changes')
    bot = ['-c', 'user.name=freshness-bot', '-c', 'user.email=freshness-bot@users.noreply.github.com']
    ledger = 'pipeline/state/ai_usage.json'
    def git(*args, check=True):
        return subprocess.run(['git', *args], cwd=ROOT, check=check, capture_output=True)
    try:
        git(*bot, 'commit', '-m', 'Reserve refresh AI allowance')
        for attempt in range(3):
            if git('push', 'origin', f'HEAD:{branch}', check=False).returncode == 0:
                return
            # Rejected. If someone else changed the ledger, our reservation was
            # computed from stale counts: refuse, exactly as before. If the branch
            # only moved for other reasons (a maintainer push mid-run, as in run
            # #7), replay the reservation on top. --autostash keeps the run's
            # uncommitted record updates intact.
            git('fetch', 'origin', branch)
            if git('diff', '--quiet', 'HEAD~1', 'FETCH_HEAD', '--', ledger,
                   check=False).returncode != 0:
                break
            if git(*bot, 'rebase', '--autostash', 'FETCH_HEAD', check=False).returncode != 0:
                git('rebase', '--abort', check=False)
                break
    except subprocess.CalledProcessError:
        pass
    raise AIUnavailable('could not persist AI allowance; no request sent')


def providers_from_env() -> list[Provider]:
    providers = []
    for name in os.environ.get('AI_PROVIDERS', 'gemini').split(','):
        name = name.strip()
        if not name:
            continue
        if name not in ('gemini', 'openrouter'):
            raise ValueError('Unknown AI provider; supported: gemini, openrouter')
        prefix = f'AI_{name.upper()}_'
        default_models = DEFAULT_GEMINI_MODELS if name == 'gemini' else ''
        models = tuple(m.strip() for m in os.environ.get(prefix + 'MODELS', default_models).split(',') if m.strip())
        if any(not re.fullmatch(r'[A-Za-z0-9._:/-]{1,150}', m) for m in models):
            raise ValueError('Invalid AI model identifier')
        providers.append(Provider(name, models, os.environ.get(name.upper() + '_API_KEY', ''),
                                  os.environ.get(prefix + 'FREE_TIER_CONFIRMED') == 'true',
                                  int(os.environ.get(prefix + 'DAILY_CALLS', DEFAULT_LIMITS[name][0])),
                                  float(os.environ.get(prefix + 'MIN_INTERVAL_MS', DEFAULT_LIMITS[name][1])) / 1000))
    return providers


class AIClient:
    def __init__(self, providers=None, ledger=None, transport=None, sleep=time.sleep):
        self.providers = providers if providers is not None else providers_from_env()
        self.daily_usd = float(os.environ.get('AI_DAILY_USD', '0'))
        self.run_cap = int(os.environ.get('AI_MAX_RUN_CALLS', DEFAULT_RUN_CALLS))
        self.max_bytes = int(os.environ.get('AI_MAX_INPUT_BYTES', str(DEFAULT_MAX_INPUT_BYTES)))
        self.max_tokens = int(os.environ.get('AI_MAX_OUTPUT_TOKENS', '4096'))
        self.max_wait = float(os.environ.get('AI_MAX_RETRY_SECONDS', '15'))
        self.timeout = float(os.environ.get('AI_TIMEOUT_SECONDS', '90'))
        if (self.run_cap < 1 or self.max_bytes < 1 or self.max_tokens < 1 or self.max_wait < 0
                or not math.isfinite(self.max_wait) or not math.isfinite(self.timeout)
                or self.timeout <= 0 or not math.isfinite(self.daily_usd) or self.daily_usd < 0):
            raise ValueError('Invalid AI limits')
        if any(p.daily_calls < 1 or not math.isfinite(p.interval) or p.interval < 0 for p in self.providers):
            raise ValueError('Invalid provider limits')
        checkpoint = git_checkpoint if os.environ.get('AI_LEDGER_GIT_SYNC') == 'true' else None
        self.ledger = ledger or Ledger(STATE / 'ai_usage.json', checkpoint)
        self.transport, self.sleep = transport, sleep
        self.disabled, self.last_started, self.remaining = set(), {}, {}
        self.lease_days = {}
        self.calls = 0
        self.successful_calls = 0
        self.budget_exhausted = False
        self.diagnostics = []

    @property
    def available(self):
        return any(p.key and p.models and p.confirmed_free for p in self.providers)

    def _reserve(self, provider):
        if self.calls >= self.run_cap:
            self.budget_exhausted = True
            raise AIUnavailable('run AI allowance exhausted')
        day = utc_day()
        if provider.name not in self.remaining or self.lease_days.get(provider.name) != day:
            # Reserve the maximum before using any part; no refunds after crashes.
            allowance = min(self.run_cap - self.calls, provider.daily_calls)
            granted = self.ledger.reserve(provider, allowance, self.daily_usd)
            self.remaining[provider.name] = granted if isinstance(granted, int) else allowance
            self.lease_days[provider.name] = day
            if utc_day() != day:
                return self._reserve(provider)  # a CI checkpoint crossed midnight
        if self.remaining[provider.name] <= 0:
            self.budget_exhausted = True
            raise AIUnavailable('provider run allowance exhausted')
        self.remaining[provider.name] -= 1
        self.calls += 1

    def generate_structured(self, instruction: str, input: str, schema: dict) -> Result:
        Draft202012Validator.check_schema(schema)  # programming errors never fall back
        request = {'instruction': instruction, 'input': input, 'schema': schema,
                   'maxOutputTokens': self.max_tokens}
        if len(json.dumps(request, ensure_ascii=False).encode('utf-8')) > self.max_bytes:
            raise AIUnavailable('AI request exceeds input limit')
        if self.calls >= self.run_cap:
            self.budget_exhausted = True
            raise AIUnavailable('run AI allowance exhausted')
        for provider in self.providers:
            if not provider.key or not provider.confirmed_free:
                continue
            for model in provider.models:
                identity = (provider.name, model)
                if identity in self.disabled:
                    continue
                if provider.name == 'openrouter' and not model.endswith(':free'):
                    self.diagnostics.append({'provider': provider.name, 'model': model, 'reason': 'priced_model_blocked'})
                    continue
                for attempt in range(2):
                    delay = provider.interval - (time.monotonic() - self.last_started.get(provider.name, -math.inf))
                    if delay > 0:
                        self.sleep(delay)
                    try:
                        self._reserve(provider)
                    except AIUnavailable:
                        self.budget_exhausted = True
                        self.diagnostics.append({'provider': provider.name, 'model': model, 'reason': 'budget_exhausted'})
                        self.disabled.update((provider.name, m) for m in provider.models)
                        break
                    self.last_started[provider.name] = time.monotonic()
                    try:
                        result = self._request(provider, model, instruction, input, schema)
                        validate(result.json, schema)
                        self.successful_calls += 1
                        return result
                    except ValidationError:
                        failure = ProviderFailure('malformed')
                    except ProviderFailure as exc:
                        failure = exc
                    self.diagnostics.append({'provider': provider.name, 'model': model,
                                             'reason': failure.kind, 'status': failure.status,
                                             'message': failure.message})
                    if failure.kind == 'rate_limited' and attempt == 0 and max(failure.retry_after, provider.interval) <= self.max_wait:
                        self.sleep(max(provider.interval, failure.retry_after))
                        continue
                    # A malformed or truncated answer is about this one page, not the
                    # model; disabling it here would end AI for the rest of the run.
                    if failure.kind not in ('malformed', 'incomplete'):
                        self.disabled.add(identity)
                    # Gemini quotas are per model, so a 429 leaves the next model in
                    # the list usable. Auth, network and server failures affect the
                    # whole provider.
                    if failure.kind in ('auth', 'provider_unavailable', 'network'):
                        self.disabled.update((provider.name, m) for m in provider.models)
                    break
        failures = list(dict.fromkeys(
            f"{d['provider']}/{d['model']}: {d['reason']}" +
            (f" (HTTP {d['status']})" if d.get('status') else '') +
            (f" {d['message']}" if d.get('message') else '') for d in self.diagnostics))
        detail = '; '.join(failures[-4:]) or 'no provider with a key, model and free-tier confirmation'
        raise AIUnavailable(f'No valid AI result: {detail}')

    def _request(self, provider, model, instruction, input, schema):
        if provider.name == 'gemini':
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            headers = {'x-goog-api-key': provider.key}
            payload = {'systemInstruction': {'parts': [{'text': instruction}]},
                       'contents': [{'role': 'user', 'parts': [{'text': input}]}],
                       'generationConfig': {'responseMimeType': 'application/json',
                                            'responseJsonSchema': gemini_schema(schema),
                                            'maxOutputTokens': self.max_tokens}}
        else:
            url = 'https://openrouter.ai/api/v1/chat/completions'
            headers = {'Authorization': f'Bearer {provider.key}'}
            payload = {'model': model, 'messages': [{'role': 'system', 'content': instruction},
                       {'role': 'user', 'content': input}], 'max_tokens': self.max_tokens,
                       'response_format': {'type': 'json_schema', 'json_schema': {
                           'name': 'volunteering_response', 'strict': True, 'schema': schema}},
                       'provider': {'require_parameters': True, 'data_collection': 'deny'}}
        if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > self.max_bytes:
            raise ProviderFailure('input_too_large')
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout, follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TransportError:
            raise ProviderFailure('network') from None
        status = response.status_code
        if status != 200:
            kind = ('rate_limited' if status == 429 else 'auth' if status in (401, 403)
                    else 'model_unavailable' if status == 404 else 'provider_unavailable'
                    if status >= 500 else 'rejected')
            try:
                retry = float(response.headers.get('Retry-After', provider.interval))
                retry = retry if math.isfinite(retry) and retry >= 0 else self.max_wait + 1
            except ValueError:
                retry = self.max_wait + 1
            raise ProviderFailure(kind, status, retry, provider_message(response))
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ProviderFailure('malformed')
            if provider.name == 'gemini':
                candidate = body.get('candidates', [])[0]
                if candidate.get('finishReason') != 'STOP':
                    raise ProviderFailure('incomplete')
                raw = ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought'))
                usage = body.get('usageMetadata', {})
                input_tokens, output_tokens = usage.get('promptTokenCount', 0), usage.get('candidatesTokenCount', 0)
            else:
                candidate = body.get('choices', [])[0]
                if candidate.get('finish_reason') != 'stop':
                    raise ProviderFailure('incomplete')
                raw = candidate['message']['content']
                usage = body.get('usage', {})
                input_tokens, output_tokens = usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0)
            return Result(json.loads(raw), provider.name, model, input_tokens, output_tokens)
        except (ValueError, TypeError, KeyError, IndexError):
            raise ProviderFailure('malformed') from None


def _variant(schema, drop=frozenset(), flatten_null=False):
    """A copy of a schema without some keywords, for finding what a provider rejects."""
    if isinstance(schema, list):
        return [_variant(x, drop, flatten_null) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key in drop:
            continue
        if key == 'properties' and isinstance(value, dict):
            out[key] = {k: _variant(v, drop, flatten_null) for k, v in value.items()}
        elif key == 'type' and flatten_null and isinstance(value, list):
            rest = [t for t in value if t != 'null']
            out[key] = rest[0] if len(rest) == 1 else rest
        else:
            out[key] = _variant(value, drop, flatten_null)
    return out


def schema_check(client) -> int:
    """Send the real extraction and verification schemas, then variants, to find a 400's cause.

    Uses one reserved call per variant on the first configured Gemini model only.
    """
    from schema import EXTRACTION_SCHEMA
    provider = next((p for p in client.providers if p.name == 'gemini' and p.key
                     and p.confirmed_free and p.models), None)
    if provider is None:
        print('No Gemini provider with a key, model and free-tier confirmation')
        return 1
    model = provider.models[0]
    full = gemini_schema(EXTRACTION_SCHEMA)
    verify = gemini_schema({'type': 'object', 'additionalProperties': False,
        'required': ['screening.dbs'], 'properties': {'screening.dbs': {
            'type': 'object', 'additionalProperties': False, 'required': ['supported', 'evidence'],
            'properties': {'supported': {'type': 'boolean'},
                           'evidence': {'type': ['string', 'null'], 'minLength': 8,
                                        'maxLength': 600}}}}})
    everything = {'minimum', 'maximum', 'minItems', 'maxItems', 'additionalProperties',
                  'enum', 'description'}
    variants = [
        ('extraction schema as sent', full),
        ('verification schema as sent', verify),
        ('extraction without null unions', _variant(full, flatten_null=True)),
        ('extraction without minimum/maximum', _variant(full, {'minimum', 'maximum'})),
        ('extraction without minItems/maxItems', _variant(full, {'minItems', 'maxItems'})),
        ('extraction without additionalProperties', _variant(full, {'additionalProperties'})),
        ('extraction without enum', _variant(full, {'enum'})),
        ('extraction without all of the above', _variant(full, everything, flatten_null=True)),
    ]
    client.run_cap = len(variants)
    page = ('Charity: Example\nPage: https://example.org\n\n--- page text begins ---\n'
            'Kitchen volunteers help serve breakfast on Saturday mornings, 8am to 11am. '
            'An enhanced DBS check is required.\n--- page text ends ---')
    print(f'Testing {model}; {len(variants)} calls.')
    for label, variant in variants:
        try:
            client._reserve(provider)
        except AIUnavailable as exc:
            print(f'  stopped: {exc}')
            return 1
        try:
            client._request(provider, model, 'Return the roles described. JSON only.', page, variant)
            outcome = 'accepted'
        except ProviderFailure as exc:
            outcome = f'{exc.kind} (HTTP {exc.status}) {exc.message or ""}'.strip()
        print(f'  {label:<44} {outcome}')
        time.sleep(provider.interval)
    return 0


def main():
    parser = argparse.ArgumentParser(description='AI diagnostics; no credentials are printed')
    parser.add_argument('command', choices=['providers', 'models', 'probe', 'schema-check'])
    args = parser.parse_args()
    client = AIClient()
    if args.command == 'schema-check':
        return schema_check(client)
    if args.command == 'providers':
        for p in client.providers:
            print(json.dumps({'provider': p.name, 'key_present': bool(p.key), 'models': p.models,
                              'confirmed_free': p.confirmed_free, 'daily_calls': p.daily_calls}))
        return 0
    if args.command == 'models':
        # Model discovery does not generate content or consume a call reservation.
        for p in client.providers:
            if not p.key:
                continue
            url = ('https://generativelanguage.googleapis.com/v1beta/models' if p.name == 'gemini'
                   else 'https://openrouter.ai/api/v1/models')
            headers = {'x-goog-api-key': p.key} if p.name == 'gemini' else {'Authorization': f'Bearer {p.key}'}
            try:
                response = httpx.get(url, headers=headers, timeout=client.timeout)
                if response.status_code != 200:
                    print(json.dumps({'provider': p.name, 'status': response.status_code}))
                    continue
                rows = response.json().get('models' if p.name == 'gemini' else 'data', [])
                ids = [r.get('name', '').removeprefix('models/') if p.name == 'gemini' else r.get('id', '') for r in rows]
                print(json.dumps({'provider': p.name, 'models': ids, 'configured_missing': [m for m in p.models if m not in ids]}))
            except (httpx.TransportError, ValueError):
                print(json.dumps({'provider': p.name, 'reason': 'discovery_unavailable'}))
        return 0
    client.run_cap = 1  # a probe reserves one call, not a full refresh allowance
    try:
        result = client.generate_structured('Classify the invented example. Return JSON.',
                    'A fictional volunteer can help at weekends.',
                    {'type': 'object', 'additionalProperties': False, 'required': ['weekend'],
                     'properties': {'weekend': {'type': 'boolean'}}})
        print(json.dumps({'provider': result.provider, 'model': result.model, 'ok': True}))
        return 0
    except AIUnavailable as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
