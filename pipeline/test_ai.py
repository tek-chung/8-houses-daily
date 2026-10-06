"""Offline AI contract tests. Never consume provider quota or use real keys."""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from ai import AIClient, AIUnavailable, Ledger, Provider, git_checkpoint
from extract import _verify
import ai

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['ok'],
          'properties': {'ok': {'type': 'boolean'}}}
GEMINI = Provider('gemini', ('first', 'second'), 'synthetic-secret', True, 10, 0)
OPENROUTER = Provider('openrouter', ('example/model:free',), 'synthetic-secret', True, 10, 0)


def answer(provider='gemini', raw='{"ok":true}', finish=None):
    if provider == 'gemini':
        return {'candidates': [{'finishReason': finish or 'STOP',
                'content': {'parts': [{'text': raw}]}}],
                'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 5}}
    return {'choices': [{'finish_reason': finish or 'stop', 'message': {'content': raw}}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 5}}


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_DAILY_USD', '0')
    monkeypatch.setenv('AI_MAX_RUN_CALLS', '3')
    monkeypatch.delenv('AI_LEDGER_GIT_SYNC', raising=False)
    def make(handler, providers=None, checkpoint=None, sleep=lambda seconds: None):
        return AIClient(providers or [GEMINI], Ledger(tmp_path / 'usage.json', checkpoint),
                        httpx.MockTransport(handler), sleep)
    return make


def test_success_is_structured_bounded_and_reserved_before_request(factory, tmp_path):
    checkpoints = []
    def handler(request):
        assert checkpoints == ['saved']
        assert 'synthetic-secret' not in str(request.url)
        payload = json.loads(request.content)
        assert payload['generationConfig']['responseJsonSchema'] == SCHEMA
        assert payload['generationConfig']['maxOutputTokens'] == 4096
        ledger = json.loads((tmp_path / 'usage.json').read_text(encoding='utf-8'))
        assert next(iter(ledger.values()))['providers']['gemini'] == 3
        return httpx.Response(200, json=answer())
    client = factory(handler, checkpoint=lambda: checkpoints.append('saved'))
    result = client.generate_structured('Instruction', 'Input', SCHEMA)
    assert result.json == {'ok': True}
    assert (result.input_tokens, result.output_tokens) == (20, 5)
    assert not client.diagnostics


@pytest.mark.parametrize('disabled', [replace(GEMINI, key=''), replace(GEMINI, confirmed_free=False)])
def test_missing_key_or_unconfirmed_free_tier_skips_provider(factory, disabled):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=answer('openrouter'))
    result = factory(handler, [disabled, OPENROUTER]).generate_structured('I', 'X', SCHEMA)
    assert result.provider == 'openrouter'
    assert len(seen) == 1


@pytest.mark.parametrize('bad', [httpx.Response(404),
    httpx.Response(200, json=answer(raw='not-json')),
    httpx.Response(200, json=answer(raw='{"ok":"invalid"}')),
    httpx.Response(200, json=answer(finish='MAX_TOKENS')),
    httpx.Response(200, json={'candidates': []})])
def test_invalid_or_retired_model_falls_back(factory, bad):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return bad if len(seen) == 1 else httpx.Response(200, json=answer())
    client = factory(handler)
    assert client.generate_structured('I', 'X', SCHEMA).model == 'second'
    assert len(seen) == 2
    assert client.diagnostics[0]['reason'] in ('model_unavailable', 'malformed', 'incomplete')


@pytest.mark.parametrize('status', [401, 403, 503])
def test_unavailable_provider_is_not_retried_for_every_model(factory, status):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(status, text='synthetic-secret private provider body') if len(seen) == 1 else httpx.Response(200, json=answer('openrouter'))
    client = factory(handler, [GEMINI, OPENROUTER])
    assert client.generate_structured('I', 'X', SCHEMA).provider == 'openrouter'
    assert len(seen) == 2
    assert 'synthetic-secret' not in json.dumps(client.diagnostics)
    assert 'private provider body' not in json.dumps(client.diagnostics)


def test_429_waits_once_then_moves_to_next_provider(factory):
    seen, waits = [], []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(429, headers={'Retry-After': '2'}) if 'googleapis' in str(request.url) else httpx.Response(200, json=answer('openrouter'))
    client = factory(handler, [GEMINI, OPENROUTER], sleep=waits.append)
    assert client.generate_structured('I', 'X', SCHEMA).provider == 'openrouter'
    assert len(seen) == 3
    assert waits == [2]


def test_long_retry_after_does_not_wait(factory):
    def handler(request):
        return httpx.Response(429, headers={'Retry-After': '99999'})
    client = factory(handler, sleep=lambda s: pytest.fail('Unbounded retry wait'))
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 1


def test_network_failure_falls_back(factory):
    def handler(request):
        if 'googleapis' in str(request.url):
            raise httpx.ConnectError('synthetic-secret')
        return httpx.Response(200, json=answer('openrouter'))
    client = factory(handler, [GEMINI, OPENROUTER])
    assert client.generate_structured('I', 'X', SCHEMA).provider == 'openrouter'
    assert client.diagnostics[0]['reason'] == 'network'


def test_programming_error_never_falls_back(factory):
    def handler(request):
        raise RuntimeError('Internal programming error')
    client = factory(handler, [GEMINI, OPENROUTER])
    with pytest.raises(RuntimeError):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 1


def test_checkpoint_failure_sends_no_request(factory):
    def checkpoint():
        raise AIUnavailable('Could not persist')
    client = factory(lambda r: pytest.fail('Request sent before persistence'), checkpoint=checkpoint)
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)


def test_zero_budget_rejects_priced_requests(factory):
    client = factory(lambda r: pytest.fail('Priced request sent'), [replace(GEMINI, estimated_cost=0.001)])
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 0


def test_openrouter_never_uses_priced_models(factory):
    client = factory(lambda r: pytest.fail('Priced model sent'), [replace(OPENROUTER, models=('paid/model',))])
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 0


def test_daily_reservations_survive_new_clients(factory):
    handler = lambda r: httpx.Response(200, json=answer())
    for _ in range(3):
        factory(handler).generate_structured('I', 'X', SCHEMA)
    with pytest.raises(AIUnavailable):
        factory(lambda r: pytest.fail('Daily cap exceeded')).generate_structured('I', 'X', SCHEMA)


def test_run_limit_counts_failed_calls(factory):
    client = factory(lambda r: httpx.Response(200, json=answer()))
    for _ in range(3):
        client.generate_structured('I', 'X', SCHEMA)
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 3


def test_complete_request_size_includes_schema(factory, tmp_path):
    client = factory(lambda r: pytest.fail('Oversized request sent'))
    client.max_bytes = 100
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert not (tmp_path / 'usage.json').exists()


def test_concurrent_reservations_cannot_overshoot(tmp_path):
    path = tmp_path / 'usage.json'
    def reserve(_):
        try:
            Ledger(path).reserve(replace(GEMINI, daily_calls=5), 1, 0)
            return True
        except AIUnavailable:
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(reserve, range(15))) == 5
    data = json.loads(path.read_text(encoding='utf-8'))
    assert next(iter(data.values()))['providers']['gemini'] == 5


@pytest.mark.parametrize('evidence,supported', [
    ('An enhanced DBS check is required.', True),
    ('This quotation does not occur on the page.', False), (None, False)])
def test_verification_requires_evidence_in_source(evidence, supported):
    class Client:
        def generate_structured(self, *args):
            return SimpleNamespace(json={'screening.dbs': {'supported': True, 'evidence': evidence}})
    ok, bad, err = _verify(Client(), 'https://example.org',
             'Kitchen volunteers: An enhanced DBS check is required.',
             {'title': 'Kitchen', 'screening': {'dbs': 'enhanced'}})
    assert ('screening.dbs' in ok) is supported
    assert ('screening.dbs' in bad) is not supported
    assert err is None


def test_git_checkpoint_cannot_be_enabled_locally(monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    with pytest.raises(ValueError):
        git_checkpoint()


def test_git_checkpoint_pushes_only_ledger_before_returning(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REF_NAME', 'main')
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout='pipeline/state/ai_usage.json\n')
    monkeypatch.setattr(ai.subprocess, 'run', run)
    git_checkpoint()
    assert commands[0] == ['git', 'add', 'pipeline/state/ai_usage.json']
    assert commands[-1] == ['git', 'push', 'origin', 'HEAD:main']


def test_git_checkpoint_rejects_other_staged_files(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REF_NAME', 'main')
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout='pipeline/state/ai_usage.json\nprivate.env\n')
    monkeypatch.setattr(ai.subprocess, 'run', run)
    with pytest.raises(AIUnavailable):
        git_checkpoint()
    assert len(commands) == 2


def test_run_crossing_midnight_reserves_the_new_day(factory, monkeypatch, tmp_path):
    monkeypatch.setattr(ai, 'utc_day', lambda: '2026-10-05')
    client = factory(lambda r: httpx.Response(200, json=answer()))
    client.generate_structured('I', 'X', SCHEMA)
    monkeypatch.setattr(ai, 'utc_day', lambda: '2026-10-06')
    client.generate_structured('I', 'X', SCHEMA)
    data = json.loads((tmp_path / 'usage.json').read_text(encoding='utf-8'))
    assert data['2026-10-05']['providers']['gemini'] == 3
    assert data['2026-10-06']['providers']['gemini'] == 2
