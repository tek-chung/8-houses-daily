"""Confirmation: re-establishing a published listing without changing it.

Added 17 October 2026. The first live run (8 Oct) checked 23 readable pages and
published nothing on its own, because every hand-researched listing differed in
wording from a fresh extraction. Without a way to confirm a listing that is still
right, the paper would have suspended itself on about 1 November.

What these tests hold:
  - confirmation never changes a published record, and never consults the gate;
  - it needs a verbatim quotation for every role and every assertive claim;
  - anything short of that falls through to the ordinary extract → gate → review;
  - new roles found beside a confirmed listing always go to a person.
"""
import copy
import json
import sys
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, validate

import review
import run as runner
from ai import AIUnavailable
from extract import Confirmation, confirm, extract
from fetchpage import FetchResult

PAGE = ("Kitchen volunteers cook breakfast for our guests every Saturday. "
        "Shifts run Saturdays 8am to 11am. You must be 18 or over to apply. "
        "We are recruiting kitchen volunteers now.")

ROLE = {'id': 'x-kitchen', 'title': 'Kitchen volunteer',
        'what_youd_do': 'Cook and serve Saturday breakfast for guests.',
        'status': 'open', 'next_intake': None, 'specific_times': 'Saturdays 8am to 11am',
        'screening': {'dbs': 'unknown', 'references': None, 'interview': None,
                      'min_age': 18, 'induction': None}}

GOOD = {'listed': 'Kitchen volunteers cook breakfast for our guests every Saturday',
        'status': 'We are recruiting kitchen volunteers now',
        'screening.min_age': 'You must be 18 or over',
        'specific_times': 'Shifts run Saturdays 8am to 11am'}


class FakeClient:
    """Checks every schema it is sent is valid, and every reply fits that schema."""
    def __init__(self, reply, exhausted=False):
        self.reply, self.sent, self.budget_exhausted = reply, [], exhausted

    def generate_structured(self, instruction, input, schema):
        Draft202012Validator.check_schema(schema)
        self.sent.append(SimpleNamespace(instruction=instruction, input=input, schema=schema))
        if isinstance(self.reply, Exception):
            raise self.reply
        data = self.reply(schema) if callable(self.reply) else self.reply
        validate(data, schema)
        return SimpleNamespace(json=data, provider='gemini', model='test')


def verdicts(evidence, others=(), places=()):
    return {'roles': {'x-kitchen': {**{k: {'supported': v is not None, 'evidence': v}
                                       for k, v in evidence.items()},
                                    'places': list(places)}},
            'other_roles': list(others)}


# ------------------------------------------------------------- extract.confirm

def test_every_quotation_found_confirms_the_listing():
    client = FakeClient(verdicts(GOOD))
    result = confirm(client, 'Example', 'https://example.org', PAGE, [ROLE])
    assert result.confirmed and not result.unsupported and result.other_roles == []
    asked = client.sent[0].schema['properties']['roles']['properties']['x-kitchen']['required']
    # unknown and null assert nothing, so they are not asked about
    assert sorted(asked) == ['listed', 'places', 'screening.min_age', 'specific_times', 'status']


# ------------------------------------------------------------- where a role happens
# St Mungo's Outreach Volunteer was published as a London role while the page offered
# it in Bournemouth and Reading only. A confirmation must compare places both ways.

LISTING = ("Outreach Volunteer. Location: Bournemouth, Reading. Join outreach shifts. "
           "Gardening Group Volunteer. Location: Camden. Garden with clients.")


def test_a_place_the_page_names_but_the_listing_lacks_is_not_confirmed():
    role = {**ROLE, 'id': 'x-kitchen', 'title': 'Outreach Volunteer', 'status': 'unknown',
            'specific_times': None, 'screening': {**ROLE['screening'], 'min_age': None}}
    verdict = {'roles': {'x-kitchen': {'listed': {'supported': True,
                                                  'evidence': 'Outreach Volunteer. Location'},
                                       'places': ['Bournemouth', 'Reading']}},
               'other_roles': []}
    result = confirm(FakeClient(verdict), 'St Mungo', 'https://e.org', LISTING, [role])
    assert not result.confirmed and result.unsupported == ['x-kitchen::stated_places']


def test_matching_places_confirm_and_bare_london_is_ignored():
    role = {**ROLE, 'title': 'Outreach Volunteer', 'status': 'unknown', 'specific_times': None,
            'stated_places': ['Bournemouth', 'Reading'],
            'screening': {**ROLE['screening'], 'min_age': None}}
    verdict = {'roles': {'x-kitchen': {'listed': {'supported': True,
                                                  'evidence': 'Outreach Volunteer. Location'},
                                       'places': ['reading', 'Bournemouth', 'London']}},
               'other_roles': []}
    # "London" is not on this page, so it is dropped before comparing; the rest match
    assert confirm(FakeClient(verdict), 'St Mungo', 'https://e.org', LISTING, [role]).confirmed


def test_a_listed_place_the_page_no_longer_names_is_not_confirmed():
    role = {**ROLE, 'title': 'Outreach Volunteer', 'status': 'unknown', 'specific_times': None,
            'stated_places': ['Ealing'],
            'screening': {**ROLE['screening'], 'min_age': None}}
    verdict = {'roles': {'x-kitchen': {'listed': {'supported': True,
                                                  'evidence': 'Outreach Volunteer. Location'},
                                       'places': []}},
               'other_roles': []}
    assert not confirm(FakeClient(verdict), 'St Mungo', 'https://e.org', LISTING, [role]).confirmed


def test_a_place_that_belongs_to_another_role_does_not_count():
    from extract import places_found
    long_gap = "Outreach Volunteer. " + "word " * 200 + "Gardening Group Volunteer. Location: Camden."
    assert not places_found('Camden', 'Outreach Volunteer', long_gap)
    assert places_found('Camden', 'Gardening Group Volunteer', long_gap)
    assert places_found('Camden', 'Role not on the page', long_gap)   # page-wide fallback


def test_extraction_drops_places_it_cannot_find_and_says_so():
    from extract import check_places
    role = {'title': 'Gardening Group Volunteer', 'stated_places': ['Camden', 'Bristol']}
    assert not check_places(role, LISTING) and role['stated_places'] == []
    role = {'title': 'Gardening Group Volunteer', 'stated_places': ['camden']}
    assert check_places(role, LISTING) and role['stated_places'] == ['camden']


@pytest.mark.parametrize('field', list(GOOD))
def test_one_unsupported_item_is_not_a_confirmation(field):
    result = confirm(FakeClient(verdicts({**GOOD, field: None})), 'Example',
                     'https://example.org', PAGE, [ROLE])
    assert not result.confirmed and result.unsupported == [f'x-kitchen::{field}']


def test_a_quotation_not_on_the_page_does_not_count():
    invented = {**GOOD, 'status': 'Applications are open all year round'}
    result = confirm(FakeClient(verdicts(invented)), 'Example', 'https://example.org',
                     PAGE, [ROLE])
    assert not result.confirmed and result.unsupported == ['x-kitchen::status']


def test_quotations_match_across_line_breaks():
    page = PAGE.replace('every Saturday. Shifts', 'every Saturday.\n\n  Shifts')
    assert confirm(FakeClient(verdicts(GOOD)), 'E', 'https://e.org', page, [ROLE]).confirmed


def test_an_empty_listing_on_a_page_with_no_roles_is_confirmed():
    client = FakeClient({'other_roles': []})
    result = confirm(client, 'Example', 'https://example.org', 'We have no roles today.', [])
    assert result.confirmed
    assert 'roles' not in client.sent[0].schema['properties']   # Gemini rejects empty objects


def test_running_out_of_allowance_defers():
    result = confirm(FakeClient(AIUnavailable('run AI allowance exhausted'), exhausted=True),
                     'Example', 'https://example.org', PAGE, [ROLE])
    assert result.deferred and not result.confirmed


def test_a_provider_failure_is_not_a_confirmation():
    result = confirm(FakeClient(AIUnavailable('No valid AI result: gemini/x: auth')),
                     'Example', 'https://example.org', PAGE, [ROLE])
    assert not result.confirmed and not result.deferred and 'auth' in result.error


def test_page_text_is_framed_as_untrusted():
    client = FakeClient(verdicts(GOOD))
    confirm(client, 'Example', 'https://example.org', PAGE, [ROLE])
    assert 'untrusted' in client.sent[0].instruction
    assert '--- page text begins ---' in client.sent[0].input


# ------------------------------------------------------------- run.process

@pytest.fixture
def record(tmp_path, monkeypatch):
    source = next(p for p in sorted(runner.ORGS_DIR.glob('*.json'))
                  if len(json.loads(p.read_text(encoding='utf-8')).get('opportunities', [])) >= 2)
    doc = json.loads(source.read_text(encoding='utf-8'))
    doc['organisation']['check'].update(last_success='2026-09-02T00:00:00+00:00',
                                        content_hash=None, last_extraction=None)
    path = tmp_path / source.name
    path.write_text(json.dumps(doc), encoding='utf-8')
    monkeypatch.setattr(runner, 'NOW', lambda: '2026-10-18T04:00:00+00:00')
    monkeypatch.setattr(runner, 'fetch', lambda *a, **k: FetchResult(
        'changed', text='page text', content_hash='page-v2'))
    return path, doc


def stored(path):
    return json.loads(path.read_text(encoding='utf-8'))


def client():
    return SimpleNamespace(budget_exhausted=False)


def test_confirmed_listing_succeeds_without_changing_a_record(record, monkeypatch):
    path, doc = record
    before = copy.deepcopy(doc['opportunities'])
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(confirmed=True, model_used='g/t'))
    monkeypatch.setattr(runner, 'extract', lambda *a: pytest.fail('no extraction once confirmed'))
    monkeypatch.setattr(runner, 'route_org', lambda *a: pytest.fail('the gate is not consulted'))
    report = runner.process(path, doc, client(), False)
    saved = stored(path)
    assert report['outcome'] == 'confirmed' and report['route'] == 'auto'
    assert saved['opportunities'] == before
    check = saved['organisation']['check']
    assert check['last_success'] == check['last_attempt'] == '2026-10-18T04:00:00+00:00'
    assert check['content_hash'] == 'page-v2'      # next week: unchanged, no AI at all


def test_unconfirmed_listing_takes_the_ordinary_path(record, monkeypatch):
    path, doc = record
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        unsupported=[f"{doc['opportunities'][0]['id']}::status"]))
    called = []
    def fake_extract(*a):
        called.append(True)
        return SimpleNamespace(error='provider unavailable', deferred=False)
    monkeypatch.setattr(runner, 'extract', fake_extract)
    report = runner.process(path, doc, client(), False)
    assert called and report['outcome'] == 'extraction_failed'
    assert 'not confirmed' in report['confirmation']
    check = stored(path)['organisation']['check']
    assert check['last_success'] == '2026-09-02T00:00:00+00:00' and check['content_hash'] is None


def new_role(doc, title='Weekend breakfast helper'):
    role = copy.deepcopy(doc['opportunities'][0])
    role.update(title=title, id=f"{doc['organisation']['id']}-weekend-breakfast-helper")
    role['provenance']['reviewed_by_human'] = False
    return role


def extraction(roles):
    return lambda *a: SimpleNamespace(error=None, deferred=False, roles=roles, confidence=1.0,
                                      verified=[], unsupported=[], model_used='g/t',
                                      page_notes=None)


def test_new_roles_beside_a_confirmed_listing_are_proposed_without_touching_it(record, monkeypatch):
    path, doc = record
    before = copy.deepcopy(doc['opportunities'])
    reworded = copy.deepcopy(before[0])
    reworded['what_youd_do'] = 'Entirely re-worded by the model, as always happens.'
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=['Weekend breakfast helper']))
    monkeypatch.setattr(runner, 'extract', extraction([reworded, new_role(doc)]))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    report = runner.process(path, doc, client(), False)
    assert report['outcome'] == 'review_required' and report['route'] == 'review'
    assert 'new role detected' in report['reasons']
    assert report['proposed'][:len(before)] == before          # current records verbatim
    assert [r['title'] for r in report['proposed'][len(before):]] == ['Weekend breakfast helper']
    saved = stored(path)
    assert saved['opportunities'] == before                     # held, not written
    check = saved['organisation']['check']
    assert check['last_success'] == '2026-10-18T04:00:00+00:00'  # the listing was confirmed
    assert check['content_hash'] is None                        # the additions are undecided
    # ...and a person can approve it from the same run without "out of date".
    review.approve(report, path, site_check=lambda org_id: [])
    titles = [r['title'] for r in stored(path)['opportunities']]
    assert titles == [r['title'] for r in before] + ['Weekend breakfast helper']


def test_new_role_never_takes_an_existing_roles_id(record, monkeypatch):
    path, doc = record
    clash = new_role(doc, 'Something else entirely')
    clash['id'] = doc['opportunities'][0]['id']
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=['Something else entirely']))
    monkeypatch.setattr(runner, 'extract', extraction([clash]))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    report = runner.process(path, doc, client(), False)
    ids = [r['id'] for r in report['proposed']]
    assert len(ids) == len(set(ids)) and ids[-1] == f"{doc['opportunities'][0]['id']}-2"


def test_other_roles_that_turn_out_to_be_listed_ones_still_confirm(record, monkeypatch):
    path, doc = record
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=[doc['opportunities'][0]['title'] + ' role']))
    monkeypatch.setattr(runner, 'extract', extraction(copy.deepcopy(doc['opportunities'])))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    report = runner.process(path, doc, client(), False)
    assert report['outcome'] == 'confirmed'
    assert stored(path)['organisation']['check']['content_hash'] == 'page-v2'


@pytest.mark.parametrize('ex', [SimpleNamespace(error='No valid AI result', deferred=False),
                                SimpleNamespace(error='allowance ran out', deferred=True)])
def test_unreadable_additions_leave_the_listing_confirmed_and_retried(record, monkeypatch, ex):
    path, doc = record
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=['Weekend breakfast helper']))
    monkeypatch.setattr(runner, 'extract', lambda *a: ex)
    doc['organisation']['check']['last_extraction'] = '2026-09-01T00:00:00+00:00'
    report = runner.process(path, doc, client(), False)
    check = stored(path)['organisation']['check']
    assert report['outcome'] == 'confirmed' and report['additions_unread']
    assert check['last_success'] == '2026-10-18T04:00:00+00:00'
    assert check['content_hash'] is None
    assert check['last_extraction'] == '2026-09-01T00:00:00+00:00'   # read first next run


def test_deferred_confirmation_keeps_its_place_in_the_queue(record, monkeypatch):
    path, doc = record
    doc['organisation']['check']['last_extraction'] = '2026-09-01T00:00:00+00:00'
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(error='allowance', deferred=True))
    report = runner.process(path, doc, client(), False)
    check = stored(path)['organisation']['check']
    assert report['outcome'] == 'ai_deferred'
    assert check['last_extraction'] == '2026-09-01T00:00:00+00:00'
    assert check['last_success'] == '2026-09-02T00:00:00+00:00'


def test_confirmation_can_be_switched_off(record, monkeypatch):
    path, doc = record
    monkeypatch.setattr(runner, 'CONFIRM_EXISTING_LISTINGS', False)
    monkeypatch.setattr(runner, 'confirm', lambda *a: pytest.fail('switched off'))
    monkeypatch.setattr(runner, 'extract', lambda *a: SimpleNamespace(error='x', deferred=False))
    assert runner.process(path, doc, client(), False)['outcome'] == 'extraction_failed'


# ------------------------------------------------- never auto-publish a build break

def test_auto_publish_the_build_would_refuse_goes_to_review(record, monkeypatch):
    """A record the build refuses stops the deploy and, through the tests, the next
    refresh. So the pipeline checks the build's invariants before publishing."""
    path, doc = record
    before = copy.deepcopy(doc['opportunities'])
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(unsupported=['x::status']))
    monkeypatch.setattr(runner, 'extract', extraction(copy.deepcopy(before)))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    monkeypatch.setattr(runner, 'route_org', lambda *a: ('auto', []))
    report = runner.process(path, doc, client(), False,
                            site_check=lambda org, roles: [f"{roles[0]['id']}: apply_url is off-domain"])
    assert report['route'] == 'review' and report['outcome'] == 'review_required'
    assert any('site build would refuse' in r for r in report['reasons'])
    assert stored(path)['opportunities'] == before


def test_real_site_check_passes_current_records_and_catches_a_break(record):
    from sitecheck import record_errors
    path, doc = record
    org, roles = doc['organisation'], copy.deepcopy(doc['opportunities'])
    assert record_errors(org, roles) == []
    roles[0]['status'] = 'open'
    roles[0]['provenance']['unsupported_fields'] = ['status']
    assert any('status' in e for e in record_errors(org, roles))


# ------------------------------------------------- copyright guard: one rewrite

def _role(what):
    return {'title': 'Kitchen', 'what_youd_do': what, 'status': 'unknown', 'next_intake': None,
            'screening': {'dbs': 'unknown', 'references': None, 'interview': None,
                          'min_age': None, 'induction': None}}


class Replies:
    def __init__(self, *answers):
        self.answers, self.instructions = list(answers), []
        self.budget_exhausted = False

    def generate_structured(self, instruction, input, schema):
        self.instructions.append(instruction)
        return SimpleNamespace(json=self.answers.pop(0), provider='gemini', model='test')


COPIED = 'cook breakfast for our guests every Saturday morning in the hall'
PAGE2 = f'Volunteers {COPIED}. It is friendly.'


def test_copied_wording_is_rewritten_once_then_accepted():
    client = Replies({'roles': [_role(f'You {COPIED}.')]},
                     {'roles': [_role('Make and serve the weekend morning meal.')]})
    result = extract(client, 'Example', 'https://example.org', PAGE2)
    assert result.error is None and len(result.roles) == 1
    assert 'own words' in client.instructions[1] and 'Kitchen' in client.instructions[1]


def test_copied_wording_twice_still_fails_the_page():
    client = Replies({'roles': [_role(f'You {COPIED}.')]}, {'roles': [_role(f'Help {COPIED}.')]})
    result = extract(client, 'Example', 'https://example.org', PAGE2)
    assert result.error and 'verbatim' in result.error and not result.roles


# ------------------------------------------------- what counts as "AI broken"

AUTH = [{'reason': 'auth', 'status': 403}]
MALFORMED = [{'reason': 'malformed', 'message': 'roles/0/when failed maxItems'}]
CHECKPOINT = [{'reason': 'budget_exhausted', 'message': 'could not persist AI allowance; no request sent'}]
USED_UP = [{'reason': 'budget_exhausted', 'message': 'daily AI allowance exhausted; no request sent'}]


@pytest.mark.parametrize('calls,ok,diags,outcome,broken', [
    (5, 0, AUTH, 'extraction_failed', True),        # every request refused: broken
    (5, 1, AUTH, 'extraction_failed', False),       # some worked
    (4, 0, MALFORMED, 'extraction_failed', False),  # one awkward page, not the integration
    (0, 0, CHECKPOINT, 'ai_deferred', True),        # nothing could be sent at all
    (0, 0, USED_UP, 'ai_deferred', False),          # a second run the same day
    (0, 0, [], 'unchanged', False)])
def test_ai_broken_means_the_integration_not_one_page(tmp_path, monkeypatch, calls, ok, diags,
                                                      outcome, broken):
    orgs = tmp_path / 'orgs'
    orgs.mkdir()
    (orgs / 'a.json').write_text(next(runner.ORGS_DIR.glob('*.json')).read_text(encoding='utf-8'),
                                 encoding='utf-8')
    fake = SimpleNamespace(available=True, calls=calls, successful_calls=ok, diagnostics=diags,
                           budget_exhausted=False)
    monkeypatch.setattr(runner, 'AIClient', lambda: fake)
    monkeypatch.setattr(runner, 'ORGS_DIR', orgs)
    monkeypatch.setattr(runner, 'STATE', tmp_path / 'state')
    monkeypatch.setattr(runner, 'REVIEW_OUT', tmp_path / 'state' / 'review.json')
    monkeypatch.setattr(runner, 'process', lambda *a: {'route': 'auto', 'reasons': [],
                                                       'outcome': outcome})
    monkeypatch.setattr(runner.decay, 'write', lambda orgs: {'median_days_since_check': 0,
                                                            'site_banner': False})
    monkeypatch.setattr(sys, 'argv', ['run.py'])
    runner.main()
    saved = json.loads((tmp_path / 'state' / 'review.json').read_text(encoding='utf-8'))
    assert saved['ai_broken'] is broken


# ------------------------------------------- 17 Oct review: the second opinion

def _contradicting(doc, field='status', value='closed'):
    role = copy.deepcopy(doc['opportunities'][0])
    if field == 'status':
        role['status'] = value if role['status'] != value else 'oversubscribed'
    else:
        role['screening'][field] = value
    return role


@pytest.mark.parametrize('with_new_role', [False, True])
def test_a_fresh_reading_that_contradicts_a_confirmed_listing_goes_to_a_person(
        record, monkeypatch, with_new_role):
    """Found in review: when the page also listed other roles, the follow-up
    extraction's view of the listed ones was discarded, so a status change could be
    absorbed as "confirmed" and the baseline advanced with nobody told."""
    path, doc = record
    before = copy.deepcopy(doc['opportunities'])
    roles = [_contradicting(doc)] + ([new_role(doc)] if with_new_role else [])
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=['Weekend breakfast helper']))
    monkeypatch.setattr(runner, 'extract', extraction(roles))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    report = runner.process(path, doc, client(), False)
    assert report['outcome'] == 'review_required' and report['route'] == 'review'
    assert 'disagrees' in report['confirmation']
    assert any('critical field changed: status' in r for r in report['reasons'])
    assert report['proposed'][0]['status'] == roles[0]['status']       # the reviewer sees it
    check = stored(path)['organisation']['check']
    assert check['last_success'] == '2026-09-02T00:00:00+00:00'        # nothing confirmed
    assert check['content_hash'] is None
    assert stored(path)['opportunities'] == before


def test_a_fresh_reading_that_merely_says_unknown_does_not_undo_a_confirmation(record, monkeypatch):
    path, doc = record
    silent = copy.deepcopy(doc['opportunities'][0])
    silent['status'] = 'unknown'
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(
        confirmed=True, other_roles=['Something']))
    monkeypatch.setattr(runner, 'extract', extraction([silent]))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    assert runner.process(path, doc, client(), False)['outcome'] == 'confirmed'


def test_team_only_on_a_fresh_reading_is_a_disagreement():
    old = {'title': 'Breakfast', 'who_can_apply': 'individual', 'status': 'open'}
    assert runner.disagreements([(old, dict(old, who_can_apply='team_only'))])
    assert not runner.disagreements([(old, dict(old, who_can_apply='unknown'))])


def test_an_empty_listing_needs_two_readings_to_agree(record, monkeypatch):
    path, doc = record
    doc['opportunities'] = []
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(confirmed=True))
    monkeypatch.setattr(runner, 'finalise', lambda role, *a: role)
    monkeypatch.setattr(runner, 'extract', extraction([]))
    report = runner.process(path, doc, client(), False)
    assert report['outcome'] == 'confirmed'
    assert stored(path)['organisation']['check']['content_hash'] == 'page-v2'


def test_an_empty_listing_whose_page_now_has_a_role_proposes_it(record, monkeypatch):
    path, doc = record
    role = new_role(doc)
    doc['opportunities'] = []
    monkeypatch.setattr(runner, 'confirm', lambda *a: Confirmation(confirmed=True))
    monkeypatch.setattr(runner, 'finalise', lambda r, *a: r)
    monkeypatch.setattr(runner, 'extract', extraction([role]))
    report = runner.process(path, doc, client(), False)
    assert report['outcome'] == 'review_required'
    assert [r['title'] for r in report['proposed']] == [role['title']]
    check = stored(path)['organisation']['check']
    assert check['content_hash'] is None and check['last_success'] == '2026-09-02T00:00:00+00:00'


@pytest.mark.parametrize('field,quote', [
    ('screening.min_age', 'You must be over the minimum age'),     # no 18 in it
    ('listed', 'You must be 18 or over to apply'),                 # nothing of the role
    ('status', '## Page: https://example.org'),                    # the fetcher's header
])
def test_a_quotation_must_contain_what_it_supports(field, quote):
    page = PAGE + ' You must be over the minimum age. ## Page: https://example.org'
    result = confirm(FakeClient(verdicts({**GOOD, field: quote})), 'E', 'https://e.org',
                     page, [ROLE])
    assert not result.confirmed and result.unsupported == [f'x-kitchen::{field}']


def test_season_eligibility_and_commitment_are_confirmed_too():
    role = dict(ROLE, seasonal_window={'start_month': 11, 'end_month': 4},
                eligibility=['Women only'], commitment='weekly', who_can_apply='team_only')
    asked = confirm_schema_fields(role)
    assert {'seasonal_window', 'eligibility', 'commitment', 'who_can_apply'} <= set(asked)
    page = PAGE + ' The shelter runs from November to April. Women only. Teams of six, weekly.'
    ev = {**GOOD, 'seasonal_window': 'runs from November to April', 'eligibility': 'Women only',
          'commitment': 'Teams of six, weekly', 'who_can_apply': 'Teams of six'}
    client = FakeClient({'roles': {'x-kitchen': {**{k: {'supported': True, 'evidence': v}
                                                    for k, v in ev.items()}, 'places': []}},
                         'other_roles': []})
    assert confirm(client, 'E', 'https://e.org', page, [role]).confirmed
    ev['seasonal_window'] = 'The shelter runs from November'          # April missing
    client = FakeClient({'roles': {'x-kitchen': {**{k: {'supported': True, 'evidence': v}
                                                    for k, v in ev.items()}, 'places': []}},
                         'other_roles': []})
    assert confirm(client, 'E', 'https://e.org', page, [role]).unsupported == ['x-kitchen::seasonal_window']


def confirm_schema_fields(role):
    from extract import confirm_schema
    return confirm_schema([role])['properties']['roles']['properties'][role['id']]['required']


def test_individual_is_not_asked_about_but_team_only_is():
    assert 'who_can_apply' not in confirm_schema_fields(dict(ROLE, who_can_apply='individual'))
    assert 'who_can_apply' in confirm_schema_fields(dict(ROLE, who_can_apply='team_only'))
