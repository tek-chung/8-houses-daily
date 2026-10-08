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


def test_429_waits_once_per_model_then_moves_on(factory, monkeypatch):
    monkeypatch.setenv('AI_MAX_RUN_CALLS', '10')
    seen, waits = [], []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(429, headers={'Retry-After': '2'}) if 'googleapis' in str(request.url) else httpx.Response(200, json=answer('openrouter'))
    client = factory(handler, [GEMINI, OPENROUTER], sleep=waits.append)
    assert client.generate_structured('I', 'X', SCHEMA).provider == 'openrouter'
    assert [u.split('/models/')[-1].split(':')[0] for u in seen[:4]] == ['first'] * 2 + ['second'] * 2
    assert len(seen) == 5
    assert waits == [2, 2]


def test_429_on_one_model_falls_back_to_the_next_model(factory):
    """Gemini quotas are per model: a rate-limited primary must not end AI for the run."""
    def handler(request):
        if '/models/first:' in str(request.url):
            return httpx.Response(429, headers={'Retry-After': '99999'})
        return httpx.Response(200, json=answer())
    client = factory(handler)
    assert client.generate_structured('I', 'X', SCHEMA).model == 'second'
    assert client.generate_structured('I', 'X', SCHEMA).model == 'second'
    assert ('gemini', 'first') in client.disabled
    assert ('gemini', 'second') not in client.disabled


def test_long_retry_after_does_not_wait(factory):
    def handler(request):
        return httpx.Response(429, headers={'Retry-After': '99999'})
    client = factory(handler, sleep=lambda s: pytest.fail('Unbounded retry wait'))
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 2   # one try per model, no waiting


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


def test_daily_reservations_survive_new_clients(factory, tmp_path):
    handler = lambda r: httpx.Response(200, json=answer())
    for _ in range(3):                      # 3 runs x 3 reserved = 9 of the 10 a day
        factory(handler).generate_structured('I', 'X', SCHEMA)
    last = factory(handler)                 # the 10th call is granted, not refused
    last.generate_structured('I', 'X', SCHEMA)
    with pytest.raises(AIUnavailable):
        last.generate_structured('I', 'X', SCHEMA)
    with pytest.raises(AIUnavailable):
        factory(lambda r: pytest.fail('Daily cap exceeded')).generate_structured('I', 'X', SCHEMA)
    data = json.loads((tmp_path / 'usage.json').read_text(encoding='utf-8'))
    assert next(iter(data.values()))['providers']['gemini'] == 10


def test_second_run_of_the_day_gets_what_is_left(tmp_path):
    """Run #8: 20 already reserved today, asked for 150 of 150, got nothing."""
    path = tmp_path / 'usage.json'
    provider = replace(GEMINI, daily_calls=150)
    assert Ledger(path).reserve(provider, 20, 0) == 20
    assert Ledger(path).reserve(provider, 150, 0) == 130
    with pytest.raises(AIUnavailable):
        Ledger(path).reserve(provider, 150, 0)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert next(iter(data.values()))['providers']['gemini'] == 150


def test_partial_grant_limits_the_run(factory, monkeypatch, tmp_path):
    monkeypatch.setenv('AI_MAX_RUN_CALLS', '10')
    Ledger(tmp_path / 'usage.json').reserve(GEMINI, 8, 0)   # 2 of 10 left today
    client = factory(lambda r: httpx.Response(200, json=answer()))
    client.generate_structured('I', 'X', SCHEMA)
    client.generate_structured('I', 'X', SCHEMA)
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.calls == 2 and client.budget_exhausted


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
        return SimpleNamespace(stdout='pipeline/state/ai_usage.json\n', returncode=0)
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


def test_both_unavailable_models_report_http_cause(factory):
    client = factory(lambda request: httpx.Response(404))
    with pytest.raises(AIUnavailable, match='model_unavailable.*HTTP 404'):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.successful_calls == 0


def test_default_byte_limit_accepts_full_unicode_page_and_schema(factory):
    from extract import PROMPT
    from schema import EXTRACTION_SCHEMA
    def handler(request):
        assert len(request.content) < ai.DEFAULT_MAX_INPUT_BYTES
        return httpx.Response(200, json=answer(raw='{"roles":[],"page_notes":null}'))
    client = factory(handler)
    assert client.generate_structured(PROMPT, '\U0001f600' * 60000, EXTRACTION_SCHEMA).json['roles'] == []
    assert client.successful_calls == 1


def test_default_models_follow_requested_order(monkeypatch):
    monkeypatch.setenv('AI_PROVIDERS', 'gemini')
    monkeypatch.delenv('AI_GEMINI_MODELS', raising=False)
    assert ai.providers_from_env()[0].models == ('gemini-3.5-flash-lite', 'gemini-3.1-flash-lite')


def test_default_limits_cover_a_full_pass_within_free_tier(monkeypatch):
    for name in ('AI_GEMINI_DAILY_CALLS', 'AI_GEMINI_MIN_INTERVAL_MS', 'AI_MAX_RUN_CALLS',
                 'AI_OPENROUTER_DAILY_CALLS', 'AI_OPENROUTER_MIN_INTERVAL_MS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('AI_PROVIDERS', 'gemini,openrouter')
    gemini, openrouter = ai.providers_from_env()
    assert (gemini.daily_calls, gemini.interval) == (150, 6.0)
    assert (openrouter.daily_calls, openrouter.interval) == (20, 5.0)
    assert AIClient([gemini]).run_cap == 150
    assert 60 / gemini.interval < 15          # under the 15 requests/minute limit


def _fake_git(monkeypatch, pushes, ledger_changed_upstream=False):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REF_NAME', 'main')
    commands, pushes = [], iter(pushes)
    def run(command, **kwargs):
        commands.append(command)
        if command[:2] == ['git', 'push']:
            code = next(pushes)
        elif command[:2] == ['git', 'diff'] and '--quiet' in command:
            code = 1 if ledger_changed_upstream else 0
        else:
            code = 0
        return SimpleNamespace(stdout='pipeline/state/ai_usage.json\n', returncode=code)
    monkeypatch.setattr(ai.subprocess, 'run', run)
    return commands


def test_git_checkpoint_rebases_when_branch_moved_during_run(monkeypatch):
    """Run #7 raced a maintainer push; an unrelated push must not disable AI."""
    commands = _fake_git(monkeypatch, [1, 0])
    git_checkpoint()
    rebases = [c for c in commands if 'rebase' in c]
    assert len(rebases) == 1 and '--autostash' in rebases[0]
    assert commands[-1] == ['git', 'push', 'origin', 'HEAD:main']


def test_git_checkpoint_refuses_when_ledger_changed_upstream(monkeypatch):
    """A newer reservation elsewhere means ours was computed from stale counts."""
    commands = _fake_git(monkeypatch, [1, 0], ledger_changed_upstream=True)
    with pytest.raises(AIUnavailable):
        git_checkpoint()
    assert not [c for c in commands if 'rebase' in c]


def test_git_checkpoint_gives_up_after_repeated_rejection(monkeypatch):
    _fake_git(monkeypatch, [1, 1, 1])
    with pytest.raises(AIUnavailable):
        git_checkpoint()


def _keywords(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            if key != 'properties':
                found.add(key)
            _keywords(value, found)
    elif isinstance(node, list):
        for item in node:
            _keywords(item, found)
    return found


def test_gemini_receives_only_supported_schema_keywords(factory):
    """Gemini 400s on minLength/maxLength/pattern; the full schema stays local."""
    from schema import EXTRACTION_SCHEMA
    sent = []
    def handler(request):
        sent.append(json.loads(request.content)['generationConfig']['responseJsonSchema'])
        return httpx.Response(200, json=answer(raw='{"roles": []}'))
    factory(handler).generate_structured('I', 'X', EXTRACTION_SCHEMA)
    used = _keywords(sent[0])
    # schema-check, 8 Oct 2026: these made gemini-3.5-flash-lite return HTTP 400
    assert not used & {'minLength', 'maxLength', 'pattern', 'uniqueItems', 'minItems', 'maxItems'}
    assert {'enum', 'required', 'additionalProperties', 'minimum'} <= used
    assert {'pattern', 'maxItems'} <= _keywords(EXTRACTION_SCHEMA)  # the original is untouched
    item = sent[0]['properties']['roles']['items']['properties']
    assert sent[0]['properties']['roles']['description'] == 'At most 15 items.'
    assert item['when']['description'] == '1 to 3 items.'
    assert 'At most 220 characters.' in item['what_youd_do']['description']


def test_limits_note_is_not_duplicated_on_reprojection():
    once = ai.gemini_schema({'type': 'string', 'maxLength': 5, 'description': 'Code.'})
    assert once == {'type': 'string', 'description': 'Code. At most 5 characters.'}
    assert ai.gemini_schema(once) == once


def test_property_named_like_a_keyword_survives_projection():
    projected = ai.gemini_schema({'type': 'object', 'properties': {
        'pattern': {'type': 'string', 'pattern': '^x$'}}})
    assert projected == {'type': 'object', 'properties': {'pattern': {'type': 'string'}}}


def test_local_validation_still_enforces_dropped_keywords(factory):
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['code'],
              'properties': {'code': {'type': 'string', 'pattern': '^[A-Z]{2}$'}}}
    client = factory(lambda r: httpx.Response(200, json=answer(raw='{"code": "not valid"}')))
    with pytest.raises(AIUnavailable, match='malformed'):
        client.generate_structured('I', 'X', schema)


def test_one_malformed_answer_does_not_disable_the_model_for_the_run(factory):
    replies = iter(['{"ok": "nope"}', '{"ok": true}'])
    client = factory(lambda r: httpx.Response(200, json=answer(raw=next(replies))),
                     providers=[replace(GEMINI, models=('only',))])
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.generate_structured('I', 'X', SCHEMA).json == {'ok': True}


def test_rejection_reports_redacted_provider_reason(factory):
    secret = 'AIzaSy' + 'x' * 33
    body = {'error': {'code': 400, 'status': 'INVALID_ARGUMENT',
                      'message': f'Invalid JSON payload; key {secret} rejected'}}
    client = factory(lambda r: httpx.Response(400, json=body),
                     providers=[replace(GEMINI, models=('only',))])
    with pytest.raises(AIUnavailable) as exc:
        client.generate_structured('I', 'X', SCHEMA)
    assert 'INVALID_ARGUMENT' in str(exc.value)
    assert secret not in str(exc.value)
    assert secret not in json.dumps(client.diagnostics)


def test_budget_exhaustion_is_flagged_for_deferral(factory, monkeypatch):
    monkeypatch.setenv('AI_MAX_RUN_CALLS', '1')
    client = factory(lambda r: httpx.Response(200, json=answer()))
    client.generate_structured('I', 'X', SCHEMA)
    assert client.budget_exhausted is False
    with pytest.raises(AIUnavailable):
        client.generate_structured('I', 'X', SCHEMA)
    assert client.budget_exhausted is True


def test_verification_cut_short_by_allowance_is_deferred_not_proposed():
    from extract import extract
    class Client:
        budget_exhausted = False
        def generate_structured(self, instruction, input, schema):
            if 'roles' in schema['properties']:
                role = {'title': 'Kitchen helper', 'what_youd_do': 'Help cook meals for guests.',
                        'screening': {'dbs': 'enhanced'}, 'status': 'open'}
                return SimpleNamespace(json={'roles': [role]}, provider='p', model='m')
            self.budget_exhausted = True
            raise AIUnavailable('run AI allowance exhausted')
    result = extract(Client(), 'Charity', 'https://example.org', 'An enhanced DBS check is required.')
    assert result.deferred is True and result.error and result.roles == []


def test_git_checkpoint_against_real_repositories(tmp_path, monkeypatch):
    """End to end with real git: unrelated upstream push is replayed, ledger edits are not."""
    import shutil
    import subprocess
    if not shutil.which('git'):
        pytest.skip('git not installed')
    def sh(cwd, *args):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@e', *args],
                              cwd=cwd, check=True, capture_output=True, text=True).stdout
    origin, work, other = tmp_path / 'origin.git', tmp_path / 'work', tmp_path / 'other'
    sh(tmp_path, 'init', '--bare', '-b', 'main', str(origin))
    sh(tmp_path, 'clone', str(origin), str(work))
    (work / 'pipeline' / 'state').mkdir(parents=True)
    ledger = work / 'pipeline' / 'state' / 'ai_usage.json'
    ledger.write_text('{}\n', encoding='utf-8')
    (work / 'record.json').write_text('old\n', encoding='utf-8')
    sh(work, 'add', '.'); sh(work, 'commit', '-m', 'base'); sh(work, 'push', 'origin', 'HEAD:main')
    sh(tmp_path, 'clone', str(origin), str(other))
    (other / 'code.py').write_text('x = 1\n', encoding='utf-8')
    sh(other, 'add', '.'); sh(other, 'commit', '-m', 'maintainer'); sh(other, 'push')

    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_REF_NAME', 'main')
    monkeypatch.setattr(ai, 'ROOT', work)
    (work / 'record.json').write_text('updated by the run, uncommitted\n', encoding='utf-8')
    ledger.write_text('{"day": 20}\n', encoding='utf-8')
    git_checkpoint()
    log = sh(origin, 'log', '--format=%s', 'main')
    assert log.splitlines()[:2] == ['Reserve refresh AI allowance', 'maintainer']
    assert (work / 'record.json').read_text(encoding='utf-8') == 'updated by the run, uncommitted\n'

    sh(other, 'pull')
    (other / 'pipeline' / 'state' / 'ai_usage.json').write_text('{"day": 40}\n', encoding='utf-8')
    sh(other, 'commit', '-am', 'another reservation'); sh(other, 'push')
    ledger.write_text('{"day": 40, "stale": true}\n', encoding='utf-8')
    with pytest.raises(AIUnavailable):
        git_checkpoint()
    assert 'stale' not in sh(origin, 'show', 'main:pipeline/state/ai_usage.json')


def test_schema_check_pinpoints_the_rejected_keyword(factory, monkeypatch, capsys):
    def handler(request):
        sent = json.dumps(json.loads(request.content)['generationConfig']['responseJsonSchema'])
        if '"enum"' in sent:
            return httpx.Response(400, json={'error': {'status': 'INVALID_ARGUMENT',
                                                       'message': 'Request contains an invalid argument.'}})
        return httpx.Response(200, json=answer(raw='{"roles": []}'))
    monkeypatch.setattr(ai.time, 'sleep', lambda s: None)
    client = factory(handler, [replace(GEMINI, daily_calls=20)])
    assert ai.schema_check(client) == 0
    lines = {l.split('  ')[1].strip(): l for l in capsys.readouterr().out.splitlines()[1:]}
    assert 'rejected' in lines['extraction schema as sent']
    assert 'accepted' in lines['extraction without enum']
    assert 'rejected' in lines['extraction without null unions']
    assert 'accepted' in lines['verification schema as sent']


def test_variant_removes_keywords_but_not_property_names():
    s = {'type': 'object', 'properties': {'enum': {'type': ['string', 'null'], 'enum': ['a']}}}
    assert ai._variant(s, {'enum'}, flatten_null=True) == {
        'type': 'object', 'properties': {'enum': {'type': 'string'}}}
