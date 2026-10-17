"""Refresh regressions: unavailable extraction must never refresh unverified facts."""
import copy
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

import fetchpage
import run as runner
from extract import Confirmation, finalise
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
    # These tests cover the extraction path. Confirmation has its own tests in
    # test_confirm.py; here it declines, exactly as when a page has changed.
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(error='not under test'))
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
        assert report['human_review_count'] == 0
        assert report['failed_count'] == 1
        assert report['ai_successful_calls'] == 0


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


# ---------------------------------------------------------- run #7 regressions

@pytest.mark.parametrize('status,refused', [(403, True), (429, True), (404, False), (500, False)])
def test_refusals_are_flagged_but_missing_pages_are_not(mocked_http, monkeypatch, status, refused):
    monkeypatch.setattr(fetchpage, '_get', lambda url, headers: httpx.Response(
        status, request=httpx.Request('GET', url)))
    result = fetchpage.fetch('https://example.org', cache_write=False)
    assert result.status == 'failed' and result.refused is refused


@pytest.mark.parametrize('detail,refused', [
    ('unable to get local issuer certificate', True),   # browsers repair the chain
    ('certificate has expired', False),                  # browsers warn visitors too
    ("Hostname mismatch, certificate is not valid for 'www.example.org'", False)])
def test_only_repairable_tls_failures_are_refusals(mocked_http, monkeypatch, detail, refused):
    def get(url, headers):
        raise httpx.ConnectError(f'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: {detail}')
    monkeypatch.setattr(fetchpage, '_get', get)
    assert fetchpage.fetch('https://example.org', cache_write=False).refused is refused


def test_refused_source_never_marks_a_working_link_dead(record, monkeypatch):
    path, doc = record
    doc['organisation']['check'].update(link_status='ok', consecutive_failures=5)
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult(
        'failed', error='HTTP 403', refused=True))
    report = runner.process(path, doc, None, False)
    check = json.loads(path.read_text(encoding='utf-8'))['organisation']['check']
    assert report['outcome'] == 'source_refused' and report['route'] == 'auto'
    assert check['link_status'] == 'ok'
    assert check['consecutive_failures'] == 5   # refusals do not count towards dead


def test_robots_server_error_is_a_retry_not_link_only(monkeypatch):
    fetchpage._robots_cache.clear()
    fetchpage._robots_unavailable.clear()
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return SimpleNamespace(status_code=503, text='')
    monkeypatch.setattr(fetchpage.httpx, 'Client', Client)
    monkeypatch.setattr(fetchpage, '_throttle', lambda: None)
    result = fetchpage.fetch('https://robots-down.example/volunteer', cache_write=False)
    assert result.status == 'failed' and 'robots.txt unavailable' in result.error
    fetchpage._robots_cache.clear()
    fetchpage._robots_unavailable.clear()


def test_exhausted_allowance_defers_instead_of_failing(record, monkeypatch):
    path, doc = record
    before = copy.deepcopy(doc)
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult('changed', text='source', content_hash='new'))
    monkeypatch.setattr(runner, 'extract', lambda *a: pytest.fail('no call once the allowance is gone'))
    client = SimpleNamespace(budget_exhausted=True)
    report = runner.process(path, doc, client, False)
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert report['outcome'] == 'ai_deferred' and report['route'] == 'auto'
    assert stored['opportunities'] == before['opportunities']
    assert stored['organisation']['check'].get('last_extraction') == \
        before['organisation']['check'].get('last_extraction')   # keeps its queue position


def test_allowance_running_out_mid_page_defers_and_keeps_queue_position(record, monkeypatch):
    path, doc = record
    doc['organisation']['check']['last_extraction'] = '2026-09-01T00:00:00+00:00'
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult('changed', text='source', content_hash='new'))
    monkeypatch.setattr(runner, 'extract', lambda *a: SimpleNamespace(
        error='AI allowance ran out', deferred=True))
    report = runner.process(path, doc, SimpleNamespace(budget_exhausted=False), False)
    check = json.loads(path.read_text(encoding='utf-8'))['organisation']['check']
    assert report['outcome'] == 'ai_deferred'
    assert check['last_extraction'] == '2026-09-01T00:00:00+00:00'


def test_completed_extraction_moves_org_to_back_of_queue(record, monkeypatch):
    path, doc = record
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult('changed', text='source'))
    monkeypatch.setattr(runner, 'extract', lambda *a: SimpleNamespace(error='rejected', deferred=False))
    runner.process(path, doc, SimpleNamespace(budget_exhausted=False), False)
    check = json.loads(path.read_text(encoding='utf-8'))['organisation']['check']
    assert check['last_extraction'] == runner.NOW()


def test_least_recently_extracted_orgs_use_the_allowance_first(tmp_path, monkeypatch):
    orgs_dir = tmp_path / 'orgs'
    orgs_dir.mkdir()
    template = json.loads(next(runner.ORGS_DIR.glob('*.json')).read_text(encoding='utf-8'))
    for org_id, stamp in [('aaa', '2026-10-01T00:00:00+00:00'), ('mmm', None),
                          ('zzz', '2026-09-01T00:00:00+00:00')]:
        doc = copy.deepcopy(template)
        doc['organisation']['id'] = org_id
        doc['organisation']['check']['last_extraction'] = stamp
        (orgs_dir / f'{org_id}.json').write_text(json.dumps(doc), encoding='utf-8')
    seen = []
    def process(path, doc, client, dry):
        seen.append(doc['organisation']['id'])
        return {'route': 'auto', 'reasons': [], 'outcome': 'unchanged'}
    monkeypatch.setattr(runner, 'ORGS_DIR', orgs_dir)
    monkeypatch.setattr(runner, 'process', process)
    monkeypatch.setattr(runner.decay, 'compute', lambda orgs: {'median_days_since_check': 0, 'site_banner': False})
    monkeypatch.setattr(sys, 'argv', ['run.py', '--dry-run'])
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert runner.main() == 0
    assert seen == ['mmm', 'zzz', 'aaa']


# ------------------------------------------------------------- reading role pages

ROLE_TEXT = ("Kitchen volunteers prepare breakfast every Saturday from 8am to 11am. "
             "An enhanced DBS check is required and we ask for two references. ") * 4


def _site(pages, monkeypatch, robots=True):
    """A fake website: url -> html. Records the order pages were requested."""
    seen = []
    monkeypatch.setattr(fetchpage, 'robots_allows', lambda url: robots)
    monkeypatch.setattr(fetchpage, '_load_cache', lambda: {})
    def get(url, headers):
        seen.append(url)
        if url not in pages:
            return httpx.Response(404, request=httpx.Request('GET', url))
        return httpx.Response(200, text=pages[url], request=httpx.Request('GET', url))
    monkeypatch.setattr(fetchpage, '_get', get)
    return seen


def page_html(body):
    return f"<html><body><main>{body}</main></body></html>"


def test_listing_pages_are_followed_to_the_roles(monkeypatch):
    base = 'https://example.org/volunteer'
    pages = {
        base: page_html(f"<p>{ROLE_TEXT}</p><a href='/volunteer/opportunities'>Current volunteer opportunities</a>"),
        'https://example.org/volunteer/opportunities': page_html(
            "<a href='/volunteer/kitchen'>Kitchen volunteer</a>"
            "<a href='/volunteer/reception'>Reception volunteer</a>"),
        'https://example.org/volunteer/kitchen': page_html(f"<h1>Kitchen</h1><p>{ROLE_TEXT}</p>"),
        'https://example.org/volunteer/reception': page_html(f"<h1>Reception</h1><p>{ROLE_TEXT}</p>"),
    }
    _site(pages, monkeypatch)
    res = fetchpage.fetch(base, cache_write=False)
    assert 'https://example.org/volunteer/kitchen' in res.pages_read
    assert 'https://example.org/volunteer/reception' in res.pages_read
    assert '## Page: https://example.org/volunteer/kitchen' in res.text


def test_published_role_pages_are_reread_even_when_unlinked(monkeypatch):
    base = 'https://example.org/volunteer'
    role = 'https://example.org/somewhere/kitchen-helper'
    pages = {base: page_html(f"<p>{ROLE_TEXT}</p>"), role: page_html(f"<p>{ROLE_TEXT}</p>")}
    seen = _site(pages, monkeypatch)
    res = fetchpage.fetch(base, cache_write=False, known_pages=[role])
    assert role in res.pages_read and role in seen


def test_one_long_page_cannot_crowd_out_the_others(monkeypatch):
    from config import MAX_SUBPAGE_CHARS
    base = 'https://example.org/volunteer'
    long_page = 'https://example.org/volunteer/long'
    short_page = 'https://example.org/volunteer/short'
    pages = {base: page_html(f"<p>{ROLE_TEXT}</p><a href='/volunteer/long'>Long role</a>"
                             "<a href='/volunteer/short'>Short role</a>"),
             long_page: page_html("<p>" + "word " * 50000 + "</p>"),
             short_page: page_html(f"<p>Short role. {ROLE_TEXT}</p>")}
    _site(pages, monkeypatch)
    res = fetchpage.fetch(base, cache_write=False)
    assert '## Page: ' + short_page in res.text
    section = res.text.split('## Page: ' + long_page)[1].split('## Page: ')[0]
    assert len(section) <= MAX_SUBPAGE_CHARS + 10


def test_known_role_pages_come_from_the_listing(record):
    path, doc = record
    # The fixture takes the first charity file that has any roles. This test needs
    # two, so do not depend on how many that charity happens to list.
    if len(doc['opportunities']) < 2:
        doc['opportunities'].append(copy.deepcopy(doc['opportunities'][0]))
    landing = doc['organisation']['volunteer_url']
    doc['opportunities'][0]['apply_url'] = 'https://example.org/roles/kitchen/'
    doc['opportunities'][0]['provenance']['source_url'] = landing
    doc['opportunities'][1]['apply_url'] = 'https://example.org/pack.pdf'
    pages = runner.known_role_pages(doc)
    assert 'https://example.org/roles/kitchen' in pages
    assert landing.rstrip('/') not in pages
    assert not any(p.endswith('.pdf') for p in pages)
