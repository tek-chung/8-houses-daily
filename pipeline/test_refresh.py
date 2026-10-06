"""Refresh regressions: unavailable extraction must never refresh unverified facts."""
import copy
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

import fetchpage
import run as runner
from extract import finalise
from fetchpage import FetchResult


@pytest.fixture
def record(tmp_path, monkeypatch):
    source = next(p for p in runner.ORGS_DIR.glob('*.json')
                  if json.loads(p.read_text(encoding='utf-8')).get('opportunities'))
    doc = json.loads(source.read_text(encoding='utf-8'))
    doc['organisation']['check']['last_success'] = '2026-01-01T00:00:00+00:00'
    path = tmp_path / 'orgs' / source.name
    path.parent.mkdir()
    path.write_text(json.dumps(doc), encoding='utf-8')
    monkeypatch.setattr(runner, 'NOW', lambda: '2026-10-05T00:00:00+00:00')
    return path, doc


@pytest.mark.parametrize('status', ['changed', 'unchanged'])
def test_missing_key_preserves_facts_and_only_verifies_unchanged(record, monkeypatch, status):
    path, doc = record
    before = copy.deepcopy(doc)
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult(status, text='source', content_hash='new'))
    monkeypatch.setattr(runner, 'extract', lambda *a: pytest.fail('No model calls without a key'))
    report = runner.process(path, doc, None, False)
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert stored['opportunities'] == before['opportunities']
    assert stored['organisation']['check']['last_attempt'] == runner.NOW()
    assert stored['organisation']['check']['last_success'] == (
        runner.NOW() if status == 'unchanged' else before['organisation']['check']['last_success'])
    if status == 'changed':
        assert report['route'] == 'review'
        assert stored['organisation']['check'].get('content_hash') == before['organisation']['check'].get('content_hash')


@pytest.mark.parametrize('dry', [True, False])
def test_main_without_key_checks_sources_and_dry_run_writes_nothing(record, monkeypatch, tmp_path, dry):
    path, doc = record
    before = path.read_bytes()
    state = tmp_path / 'state'
    monkeypatch.setenv('AI_PROVIDERS', 'gemini')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setattr(runner, 'ORGS_DIR', path.parent)
    monkeypatch.setattr(runner, 'STATE', state)
    monkeypatch.setattr(runner, 'REVIEW_OUT', state / 'review.json')
    monkeypatch.setattr(sys, 'argv', ['run.py'] + (['--dry-run'] if dry else []))
    calls = []
    def fetch(*a, **kwargs):
        calls.append(kwargs)
        return FetchResult('changed', text='source', content_hash='new')
    monkeypatch.setattr(runner, 'fetch', fetch)
    fresh = {'median_days_since_check': 1, 'site_banner': False}
    monkeypatch.setattr(runner.decay, 'compute', lambda orgs: fresh)
    monkeypatch.setattr(runner.decay, 'write', lambda orgs: fresh)
    assert runner.main() == 1
    assert calls[0]['cache_write'] is not dry
    if dry:
        assert path.read_bytes() == before
        assert not state.exists()
    else:
        report = json.loads((state / 'review.json').read_text(encoding='utf-8'))
        assert report['extraction_available'] is False
        assert report['needs_review'] == len(report['items']) == 1


def test_extraction_failure_records_attempt_without_verifying(record, monkeypatch):
    path, doc = record
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult('changed', text='source'))
    monkeypatch.setattr(runner, 'extract', lambda *a: SimpleNamespace(error='provider unavailable'))
    assert runner.process(path, doc, object(), False)['route'] == 'review'
    check = json.loads(path.read_text(encoding='utf-8'))['organisation']['check']
    assert check['last_attempt'] == runner.NOW()
    assert check['last_success'] == '2026-01-01T00:00:00+00:00'


def test_internal_error_stops_run_instead_of_provider_fallback(record, monkeypatch, tmp_path):
    path, doc = record
    monkeypatch.setenv('AI_PROVIDERS', 'gemini')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setattr(runner, 'ORGS_DIR', path.parent)
    monkeypatch.setattr(sys, 'argv', ['run.py'])
    def fetch(*a, **kwargs):
        raise RuntimeError('Internal error')
    monkeypatch.setattr(runner, 'fetch', fetch)
    assert runner.main() == 2


def test_published_role_links_survive_title_rewording(record, monkeypatch):
    path, doc = record
    doc['opportunities'] = doc['opportunities'][:1]
    old = doc['opportunities'][0]
    candidate = copy.deepcopy(old)
    candidate['title'] += ' role'
    candidate['id'] = 'new-generated-id'
    candidate['coords'] = None
    old['coords'] = [51.5, -0.1]
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult('changed', text='source'))
    monkeypatch.setattr(runner, 'extract', lambda *a: SimpleNamespace(
        error=None, roles=[candidate], confidence=1.0, verified=[], unsupported=[],
        model_used='test', page_notes=[]))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    monkeypatch.setattr(runner, 'route_org', lambda *a: ('auto', []))
    runner.process(path, doc, object(), False)
    stored = json.loads(path.read_text(encoding='utf-8'))['opportunities'][0]
    assert stored['id'] == old['id']
    assert stored['coords'] == old['coords']


def test_verified_fields_are_scoped_to_their_role():
    result = finalise({'title': 'Kitchen'}, 'charity', 'https://example.org', 1,
                      ['Kitchen::screening.dbs', 'Host::status'], ['Host::screening.dbs'])
    assert result['provenance']['verified_fields'] == ['screening.dbs']
    assert result['provenance']['unsupported_fields'] == []


@pytest.fixture
def mocked_http(monkeypatch):
    monkeypatch.setattr(fetchpage, 'robots_allows', lambda url: True)
    monkeypatch.setattr(fetchpage, 'main_content', lambda html: html)
    monkeypatch.setattr(fetchpage, 'MIN_MAIN_CONTENT_CHARS', 1)
    monkeypatch.setattr(fetchpage, '_load_cache', lambda: {
        'https://example.org': {'etag': 'cached', 'hash': 'approved'}})
    monkeypatch.setattr(fetchpage, '_save_cache', lambda cache: pytest.fail('Dry fetch wrote cache'))


def test_linked_page_changes_are_checked_despite_cached_landing(mocked_http, monkeypatch):
    calls = []
    body = ['original role requirements']
    monkeypatch.setattr(fetchpage, 'find_role_links', lambda *a: ['https://example.org/role'])
    def get(url, headers):
        calls.append((url, headers.copy()))
        return httpx.Response(200, text=body[0] if url.endswith('/role') else 'landing',
                              request=httpx.Request('GET', url))
    monkeypatch.setattr(fetchpage, '_get', get)
    first = fetchpage.fetch('https://example.org', cache_write=False)
    body[0] = 'changed role requirements'
    second = fetchpage.fetch('https://example.org', known_hash=first.content_hash, cache_write=False)
    assert second.status == 'changed'
    assert len(calls) == 4
    assert all('If-None-Match' not in headers for _, headers in calls)


@pytest.mark.parametrize('known_hash,status', [('approved', 'unchanged'), ('unapproved', 'failed')])
def test_304_requires_approved_single_page_baseline(mocked_http, monkeypatch, known_hash, status):
    headers_seen = []
    def get(url, headers):
        headers_seen.append(headers)
        return httpx.Response(304, request=httpx.Request('GET', url))
    monkeypatch.setattr(fetchpage, '_get', get)
    result = fetchpage.fetch('https://example.org', known_hash=known_hash,
                             follow_roles=False, cache_write=False)
    assert result.status == status
    assert ('If-None-Match' in headers_seen[0]) == (status == 'unchanged')
