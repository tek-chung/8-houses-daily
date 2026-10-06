"""Freshness must work without a pipeline run or a recent saved report."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_build_recomputes_freshness_from_the_source_dates(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('freshness_builder', Path(__file__).with_name('build.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, 'DATA', tmp_path)
    (tmp_path / 'orgs').mkdir()
    source = {'organisation': {'id': 'sample', 'check': {
        'last_success': (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()}},
        'opportunities': [{'id': 'sample-role'}]}
    (tmp_path / 'orgs' / 'sample.json').write_text(json.dumps(source), encoding='utf-8')
    _, _, report, _ = builder.load()
    assert report['orgs']['sample']['suppress_assertive'] is True
    (tmp_path / 'freshness.json').write_text(json.dumps({'orgs': {
        'sample': {'suppress_assertive': False}}}), encoding='utf-8')
    _, _, report, _ = builder.load()
    assert report['orgs']['sample']['suppress_assertive'] is True
