"""Separate valid proposals from incomplete checks in GitHub summaries."""
import argparse
import json
from pathlib import Path

MAX_PR_BODY = 60_000   # GitHub refuses bodies over 65,536 characters


def text(value):
    return str(value).replace('\n', ' ').replace('|', '\\|').replace('`', "'")


def render(report, pr=False):
    human = report['human_review_count']
    failed = report['failed_count']
    lines = ['## Refresh summary', '',
        f"AI configured: **{report['ai_configured']}**",
        f"Validated AI responses: **{report['ai_successful_calls']}**",
        f"Confirmed against the page: **{report.get('confirmed_count', 0)}** · "
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
                  'Screening, recruitment status, intake and new or missing roles need a '
                  'person. Nothing is published until you decide, and the paper stays '
                  'honest meanwhile: unchecked notices stop asserting screening and '
                  'status after 21 days.', '',
                  '**From the browser:** read the changes below and the charity’s own '
                  'page, then **Actions → Review a proposal → Run workflow**, with the '
                  'charity id and approve or reject. It commits the decision and redeploys.', '',
                  '**Or locally**, on `main` after `git fetch`:', '',
                  '```',
                  'python pipeline/review.py list',
                  'python pipeline/review.py show <org-id>      # then read their page',
                  'python pipeline/review.py approve <org-id>   # or: reject <org-id>',
                  '```', '',
                  'Then commit `data/` and push. Do not merge this PR: it only carries the '
                  'proposals. Approving marks the records as reviewed by a human.', '']
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


def proposal_details(report, orgs_dir):
    """Each proposal field by field, as `review.py show` prints it, so it can be
    reviewed in the browser without a checkout."""
    from review import describe
    fence = '`' * 3
    out = []
    for r in report.get('results', []):
        if r.get('outcome') != 'review_required':
            continue
        path = Path(orgs_dir) / f"{r['org_id']}.json"
        try:
            shown = describe(r, json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError) as exc:
            shown = f'(could not show the changes: {type(exc).__name__})'
        out += [f"<details><summary><b>{text(r['name'])}</b> · id <code>{r['org_id']}</code>"
                f" · {r.get('roles_before')} → {r.get('roles_after')} roles</summary>", '',
                fence + 'diff', shown.replace(fence, "'''"), fence, '', '</details>', '']
    return out


def pr_body(report, orgs_dir):
    body = render(report, pr=True)
    details = proposal_details(report, orgs_dir)
    if details:
        body += '\n### The changes, charity by charity\n\n' + '\n'.join(details)
    if len(body) > MAX_PR_BODY:
        body = (body[:MAX_PR_BODY] + '\n\n…cut short to fit GitHub. `python pipeline/review.py '
                'show <org-id>`, or the freshness-run artifact, has the rest.\n')
    return body


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
        print(f"ai_broken={str(bool(report.get('ai_broken'))).lower()}")
    elif args.format == 'pr':
        from config import ORGS_DIR
        print(pr_body(report, ORGS_DIR), end='')
    else:
        print(render(report), end='')


if __name__ == '__main__':
    main()
