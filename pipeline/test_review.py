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
    assert json.loads(file.read_text(encoding='utf-8'))['results'][0]['outcome'] == 'approved'
    assert review.main(['--path', str(file), 'list']) == 0
    assert 'Nothing waiting' in capsys.readouterr().out
    assert review.main(['--path', str(file), 'reject', org_id]) == 1


def test_real_site_check_accepts_current_data():
    org_id = json.loads(next(review.ORGS_DIR.glob('*.json')).read_text(encoding='utf-8'))['organisation']['id']
    assert review._site_errors(org_id) == []
