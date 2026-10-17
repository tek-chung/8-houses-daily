"""Approving review proposals. Run: python -m pytest pipeline/test_review.py -q"""
import copy
import json

import pytest

import review
from review import ReviewError, approve, describe, reject


@pytest.fixture
def org(tmp_path):
    source = next(p for p in sorted(review.ORGS_DIR.glob('*.json'))
                  if len(json.loads(p.read_text(encoding='utf-8')).get('opportunities', [])) >= 2)
    doc = json.loads(source.read_text(encoding='utf-8'))
    doc['organisation']['check'].update(last_success='2026-09-01T00:00:00+00:00',
                                        content_hash=None)
    path = tmp_path / source.name
    path.write_text(json.dumps(doc), encoding='utf-8')
    return path, doc


def proposal(doc, roles):
    org = doc['organisation']
    return {'org_id': org['id'], 'name': org['name'], 'url': org['volunteer_url'],
            'outcome': 'review_required', 'reasons': ['new role detected'],
            'roles_before': len(doc['opportunities']), 'roles_after': len(roles),
            'fetched_content_hash': 'page-v2', 'checked_at': '2026-10-11T04:00:00+00:00',
            'model': 'gemini/test', 'confidence': 1.0, 'proposed': roles}


def new_role(doc, title='Weekend breakfast helper'):
    role = copy.deepcopy(doc['opportunities'][0])
    role.update(title=title, id=f"{doc['organisation']['id']}-weekend-breakfast-helper")
    role['provenance']['reviewed_by_human'] = False
    return role


def no_site_errors(org_id):
    return []


def test_approve_publishes_proposal_as_reviewed_and_sets_baseline(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities']) + [new_role(doc)]
    for r in roles:
        r['provenance']['reviewed_by_human'] = False
    approve(proposal(doc, roles), path, site_check=no_site_errors)
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert [r['title'] for r in stored['opportunities']] == [r['title'] for r in roles]
    assert all(r['provenance']['reviewed_by_human'] for r in stored['opportunities'])
    check = stored['organisation']['check']
    assert check['content_hash'] == 'page-v2'
    assert check['last_success'] == '2026-10-11T04:00:00+00:00'


def test_drop_leaves_out_one_proposed_role(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities']) + [new_role(doc)]
    approve(proposal(doc, roles), path, drop=['weekend BREAKFAST helper'], site_check=no_site_errors)
    titles = [r['title'] for r in json.loads(path.read_text(encoding='utf-8'))['opportunities']]
    assert 'Weekend breakfast helper' not in titles and len(titles) == len(doc['opportunities'])


def test_drop_of_unknown_title_changes_nothing(org):
    path, doc = org
    before = path.read_bytes()
    with pytest.raises(ReviewError, match='no proposed role'):
        approve(proposal(doc, copy.deepcopy(doc['opportunities'])), path,
                drop=['Nope'], site_check=no_site_errors)
    assert path.read_bytes() == before


def test_missing_roles_are_removed_unless_kept_with_unknown_status(org):
    path, doc = org
    keep = copy.deepcopy(doc['opportunities'][:1])
    missing = doc['opportunities'][1]['title']
    approve(proposal(doc, keep), path, site_check=no_site_errors)
    assert missing not in [r['title'] for r in json.loads(path.read_text(encoding='utf-8'))['opportunities']]

    path.write_text(json.dumps(doc), encoding='utf-8')
    approve(proposal(doc, keep), path, keep_missing=True, site_check=no_site_errors)
    stored = {r['title']: r for r in json.loads(path.read_text(encoding='utf-8'))['opportunities']}
    assert stored[missing]['status'] == 'unknown'


def test_site_build_rejection_rolls_back(org):
    path, doc = org
    before = path.read_bytes()
    with pytest.raises(ReviewError, match='site build would reject'):
        approve(proposal(doc, copy.deepcopy(doc['opportunities'])), path,
                site_check=lambda org_id: [f'{org_id}: bad apply_url'])
    assert path.read_bytes() == before


def test_schema_invalid_proposal_is_refused(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities'])
    roles[0]['status'] = 'maybe'
    with pytest.raises(ReviewError):
        approve(proposal(doc, roles), path, site_check=no_site_errors)


def test_duplicate_ids_are_refused(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities'])
    roles[1]['id'] = roles[0]['id']
    with pytest.raises(ReviewError, match='share an id'):
        approve(proposal(doc, roles), path, site_check=no_site_errors)


@pytest.mark.parametrize('decide', [
    lambda p, path: approve(p, path, site_check=no_site_errors),
    lambda p, path: reject(p, path)])
def test_stale_or_repeated_decisions_are_refused(org, decide):
    path, doc = org
    p = proposal(doc, copy.deepcopy(doc['opportunities']))
    decide(p, path)
    with pytest.raises(ReviewError, match='Already decided'):
        decide(p, path)
    stale = json.loads(path.read_text(encoding='utf-8'))
    stale['organisation']['check'].update(content_hash='later', last_success='2026-10-12T00:00:00+00:00')
    path.write_text(json.dumps(stale), encoding='utf-8')
    with pytest.raises(ReviewError, match='Out of date'):
        decide(p, path)


def test_reject_keeps_listing_and_records_baseline(org):
    path, doc = org
    reject(proposal(doc, [new_role(doc)]), path)
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert stored['opportunities'] == doc['opportunities']
    assert stored['organisation']['check']['content_hash'] == 'page-v2'
    assert stored['organisation']['check']['last_success'] == '2026-09-01T00:00:00+00:00'


def test_show_names_changes_new_and_missing_roles(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities'][:1]) + [new_role(doc)]
    roles[0]['status'] = 'closed' if roles[0]['status'] != 'closed' else 'open'
    text = describe(proposal(doc, roles), doc)
    assert '~ ' in text and 'status:' in text
    assert '+ NEW Weekend breakfast helper' in text
    assert f"- MISSING {doc['opportunities'][1]['title']}" in text


def test_cli_list_approve_and_note(org, tmp_path, monkeypatch, capsys):
    path, doc = org
    monkeypatch.setattr(review, 'ORGS_DIR', path.parent)
    monkeypatch.setattr(review, 'org_path', lambda org_id: path)
    monkeypatch.setattr(review, '_site_errors', no_site_errors)
    file = tmp_path / 'review.json'
    file.write_text(json.dumps({'results': [proposal(doc, copy.deepcopy(doc['opportunities']))]}),
                    encoding='utf-8')
    org_id = doc['organisation']['id']
    assert review.main(['--path', str(file), 'list']) == 0
    assert org_id in capsys.readouterr().out
    assert review.main(['--path', str(file), 'approve', org_id]) == 0
    saved = json.loads(file.read_text(encoding='utf-8'))
    assert saved['results'][0]['outcome'] == 'approved'
    assert saved['items'] == []
    assert saved['needs_review'] == saved['human_review_count'] == saved['failed_count'] == 0
    assert review.main(['--path', str(file), 'list']) == 0
    assert 'Nothing waiting' in capsys.readouterr().out
    assert review.main(['--path', str(file), 'reject', org_id]) == 1


def test_real_site_check_accepts_current_data():
    org_id = json.loads(next(review.ORGS_DIR.glob('*.json')).read_text(encoding='utf-8'))['organisation']['id']
    assert review._site_errors(org_id) == []


def test_same_keeps_the_published_id_of_a_renamed_role(org):
    path, doc = org
    old = doc['opportunities'][0]
    renamed = copy.deepcopy(old)
    renamed.update(title='Completely different wording', id='org-completely-different-wording')
    roles = [renamed] + copy.deepcopy(doc['opportunities'][1:])
    text = describe(proposal(doc, roles), doc)
    assert f'--same "Completely different wording={old["title"]}"' in text
    approve(proposal(doc, roles), path, keep_missing=True, site_check=no_site_errors,
            same=[f'Completely different wording={old["title"]}'])
    stored = json.loads(path.read_text(encoding='utf-8'))['opportunities']
    assert [r['id'] for r in stored].count(old['id']) == 1          # not also kept as missing
    assert next(r for r in stored if r['id'] == old['id'])['title'] == 'Completely different wording'


def test_same_with_unknown_titles_changes_nothing(org):
    path, doc = org
    before = path.read_bytes()
    with pytest.raises(ReviewError, match='--same'):
        approve(proposal(doc, copy.deepcopy(doc['opportunities'])), path,
                site_check=no_site_errors, same=['Nope=Also nope'])
    assert path.read_bytes() == before


def test_blank_descriptive_fields_keep_current_values_but_critical_ones_do_not(org):
    """8 Oct 2026: approving Simon Community erased hand-researched NW5 postcodes."""
    path, doc = org
    roles = copy.deepcopy(doc['opportunities'])
    old = doc['opportunities'][0]
    roles[0].update(postcode_district=None, commitment='unknown', eligibility=[],
                    status='unknown')
    old_known = dict(postcode_district='NW5', commitment='weekly',
                     eligibility=['Women only'], status='open')
    doc['opportunities'][0].update(old_known)
    path.write_text(json.dumps(doc), encoding='utf-8')
    carried = []
    approve(proposal(doc, roles), path, site_check=no_site_errors, carried=carried)
    stored = json.loads(path.read_text(encoding='utf-8'))['opportunities'][0]
    assert stored['postcode_district'] == 'NW5' and stored['commitment'] == 'weekly'
    assert stored['eligibility'] == ['Women only']
    assert stored['status'] == 'unknown'          # critical: unknown wins
    assert carried and set(carried[0][1]) >= {'postcode_district', 'commitment', 'eligibility'}


def test_take_blanks_accepts_the_new_reading(org):
    path, doc = org
    roles = copy.deepcopy(doc['opportunities'])
    roles[0]['specific_times'] = None
    doc['opportunities'][0]['specific_times'] = 'Saturdays 9am'
    path.write_text(json.dumps(doc), encoding='utf-8')
    approve(proposal(doc, roles), path, site_check=no_site_errors, take_blanks=True)
    assert json.loads(path.read_text(encoding='utf-8'))['opportunities'][0]['specific_times'] is None

# ------------------------------------------------------- 17 Oct 2026 regressions

def test_site_check_sees_roles_whose_ids_do_not_start_with_the_charity_id():
    """20 roles (watw-kitchen, nhyc-esol-tutor, sct-charity-shops...) have short ids.
    Matching errors on the charity-id prefix let their build errors through, so an
    approval could write a record the build then refused."""
    from sitecheck import errors_for
    roles = [{'id': 'watw-kitchen', 'org_id': 'women-at-the-well'},
             {'id': 'women-at-the-well-host', 'org_id': 'women-at-the-well'},
             {'id': 'crisis-welcome', 'org_id': 'crisis'}]
    errors = ['watw-kitchen: status open but unsupported', 'women-at-the-well-host: bad',
              'women-at-the-well: org invalid', 'crisis-welcome: not ours']
    assert errors_for('women-at-the-well', errors, roles) == errors[:3]


def test_reviewers_platform_note_survives_approval(org):
    """Shelter recruits on app.betterimpact.com. The build accepts that only when a
    reviewer named the domain; a fresh extraction cannot, so approval always failed."""
    path, doc = org
    old = doc['opportunities'][0]
    old['apply_url'] = 'https://app.betterimpact.com/PublicOrganization/example'
    note = 'the opportunity list is on app.betterimpact.com, their volunteering platform'
    old['provenance']['unsupported_fields'] = ['screening.references', note]
    path.write_text(json.dumps(doc), encoding='utf-8')
    roles = copy.deepcopy(doc['opportunities'])
    roles[0]['provenance']['unsupported_fields'] = ['status']
    roles[0]['provenance']['reviewed_by_human'] = False
    approve(proposal(doc, roles), path, site_check=no_site_errors)
    stored = json.loads(path.read_text(encoding='utf-8'))['opportunities'][0]
    assert note in stored['provenance']['unsupported_fields']
    assert 'screening.references' not in stored['provenance']['unsupported_fields']


def test_platform_note_is_not_carried_to_a_different_domain(org):
    path, doc = org
    old = doc['opportunities'][0]
    old['apply_url'] = 'https://app.betterimpact.com/x'
    old['provenance']['unsupported_fields'] = ['listed on app.betterimpact.com']
    path.write_text(json.dumps(doc), encoding='utf-8')
    roles = copy.deepcopy(doc['opportunities'])
    roles[0]['apply_url'] = 'https://elsewhere.example/apply'
    roles[0]['provenance']['unsupported_fields'] = []
    approve(proposal(doc, roles), path, site_check=no_site_errors)
    stored = json.loads(path.read_text(encoding='utf-8'))['opportunities'][0]
    assert stored['provenance']['unsupported_fields'] == []


def _review(generated_at, outcome='review_required'):
    return {'generated_at': generated_at, 'results': [{'org_id': 'x', 'outcome': outcome}]}


@pytest.mark.parametrize('local_at,remote_at,expected', [
    ('2026-10-08T10:00:00+00:00', '2026-10-18T04:30:00+00:00', 'remote'),
    ('2026-10-18T04:30:00+00:00', '2026-10-08T10:00:00+00:00', 'local'),
    ('2026-10-18T04:30:00+00:00', '2026-10-18T04:30:00+00:00', 'local'),   # keeps decisions
    (None, '2026-10-18T04:30:00+00:00', 'remote')])
def test_the_newer_set_of_proposals_wins(tmp_path, monkeypatch, local_at, remote_at, expected):
    """A local review.json used to win unconditionally, so after a week away the
    previous run's proposals were offered as if they were current."""
    path = tmp_path / 'review.json'
    if local_at:
        path.write_text(json.dumps(_review(local_at, 'local')), encoding='utf-8')
    monkeypatch.setattr(review, '_latest_review_branch', lambda: review.ROLLING_BRANCH)
    monkeypatch.setattr(review, '_read_branch', lambda ref: _review(remote_at, 'remote'))
    loaded = review.load_review(path)
    assert loaded['results'][0]['outcome'] == expected
    assert json.loads(path.read_text(encoding='utf-8'))['results'][0]['outcome'] == expected


def test_an_explicit_path_is_used_as_given(tmp_path, monkeypatch):
    path = tmp_path / 'review.json'
    path.write_text(json.dumps(_review('2026-01-01T00:00:00+00:00', 'local')), encoding='utf-8')
    monkeypatch.setattr(review, '_latest_review_branch', lambda: pytest.fail('not consulted'))
    assert review.load_review(path, prefer_newer=False)['results'][0]['outcome'] == 'local'


def test_rolling_branch_is_preferred_to_dated_ones(monkeypatch):
    refs = '\n'.join(['refs/remotes/origin/freshness/review-2026-10-08',
                      'refs/remotes/origin/freshness/review',
                      'refs/remotes/origin/freshness/review-2026-10-06'])
    monkeypatch.setattr(review.subprocess, 'run', lambda *a, **k: type('R', (), {'stdout': refs})())
    assert review._latest_review_branch() == review.ROLLING_BRANCH
    monkeypatch.setattr(review.subprocess, 'run', lambda *a, **k: type('R', (), {
        'stdout': refs.replace('refs/remotes/origin/freshness/review\n', '')})())
    assert review._latest_review_branch().endswith('review-2026-10-08')
