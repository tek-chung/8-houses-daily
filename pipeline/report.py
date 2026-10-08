"""Separate valid proposals from incomplete checks in GitHub summaries."""
import argparse
import json
from pathlib import Path


def text(value):
    return str(value).replace('\n', ' ').replace('|', '\\|').replace('`', "'")


def render(report, pr=False):
    human = report['human_review_count']
    failed = report['failed_count']
    lines = ['## Refresh summary', '',
        f"AI configured: **{report['ai_configured']}**",
        f"Validated AI responses: **{report['ai_successful_calls']}**",
        f"Published updates: **{report['published_count']}** · "
        f"Unchanged sources: **{report['unchanged_count']}**",
        f"Proposals requiring human review: **{human}** · Incomplete checks: **{failed}**",
        f"Refused by site: **{report.get('refused_count', 0)}** · "
        f"Deferred to next run (AI allowance used up): **{report.get('deferred_count', 0)}**", '']
    if failed:
        lines += ['Incomplete checks retain existing listings and their last successful '
                  'verification dates. They are not proposals to approve.', '']
    diagnostics = report.get('ai_diagnostics', [])
    if diagnostics:
        lines += ['### Provider diagnostics', '',
                  '| Provider/model | Reason | HTTP | Provider message |',
                  '| --- | --- | --- | --- |']
        seen = set()
        for d in diagnostics:
            row = (d['provider'], d['model'], d['reason'], d.get('status'), d.get('message'))
            if row in seen:
                continue
            seen.add(row)
            lines.append(f"| {text(row[0])}/{text(row[1])} | {text(row[2])} | "
                         f"{row[3] or '—'} | {text(row[4]) if row[4] else '—'} |")
        lines.append('')
        if any(d.get('status') == 404 for d in diagnostics):
            lines += ['The configured models were unavailable. Check `AI_GEMINI_MODELS` '
                      'against the account’s accessible models (`python pipeline/ai.py models`). '
                      'See `docs/ai-setup.md`.', '']
        if any(d.get('status') == 400 for d in diagnostics):
            lines += ['The provider rejected the request itself (HTTP 400). The provider '
                      'message above says which part; an invalid API key also returns 400 '
                      'on Gemini.', '']
    if human:
        lines += ['### Proposals to review', '',
                  'Review only entries with `outcome: review_required` and `proposed` '
                  'records in `pipeline/state/review.json`. Screening, recruitment status '
                  'and intake changes require human approval. After checking the facts, '
                  'copy accepted records, their `fetched_content_hash` and `checked_at` '
                  'into the organisation record. Set `provenance.reviewed_by_human` '
                  'only after a human has reviewed them.', '']
    results = report.get('results', [])
    selected = [r for r in results if r.get('outcome') == 'review_required' or
                (not pr and r.get('outcome') in ('source_failed', 'source_refused',
                                               'ai_unavailable', 'extraction_failed',
                                               'invalid_extraction'))]
    if selected:
        lines += ['| Charity | Outcome | Reason |', '| --- | --- | --- |']
        for r in selected:
            lines.append(f"| {text(r['name'])} | {text(r['outcome'])} | "
                         f"{text('; '.join(r['reasons']))} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('format', choices=['summary', 'pr', 'outputs'])
    parser.add_argument('--path', type=Path, default=Path('pipeline/state/review.json'))
    args = parser.parse_args()
    report = json.loads(args.path.read_text(encoding='utf-8'))
    assert report['needs_review'] == len(report['items'])
    if args.format == 'outputs':
        print(f"review_count={report['human_review_count']}")
        print(f"failed_count={report['failed_count']}")
        print(f"ai_failed_count={report.get('ai_failed_count', report['failed_count'])}")
        print(f"source_failed_count={report.get('source_failed_count', 0)}")
    else:
        print(render(report, args.format == 'pr'), end='')


if __name__ == '__main__':
    main()
