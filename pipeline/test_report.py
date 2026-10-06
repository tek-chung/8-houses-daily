from report import render


def test_failed_extractions_are_not_human_review_proposals():
    report = {'ai_configured': True, 'ai_successful_calls': 0,
              'human_review_count': 0, 'failed_count': 1,
              'published_count': 0, 'unchanged_count': 15,
              'ai_diagnostics': [{'provider': 'gemini', 'model': 'old',
                                  'reason': 'model_unavailable', 'status': 404}],
              'results': [{'name': 'Example charity', 'outcome': 'extraction_failed',
                           'reasons': ['No valid AI result']} ]}
    summary = render(report)
    assert 'Proposals requiring human review: **0**' in summary
    assert 'Incomplete checks: **1**' in summary
    assert 'Validated AI responses: **0**' in summary
    assert '404' in summary
    assert '### Proposals to review' not in summary
    assert 'Example charity' not in render(report, pr=True)


def test_pr_only_lists_valid_proposals():
    report = {'ai_configured': True, 'ai_successful_calls': 2,
              'human_review_count': 1, 'failed_count': 1,
              'published_count': 0, 'unchanged_count': 0,
              'results': [
                  {'name': 'Proposal charity', 'outcome': 'review_required',
                   'reasons': ['screening changed']},
                  {'name': 'Failed charity', 'outcome': 'extraction_failed',
                   'reasons': ['HTTP 404']}]}
    summary = render(report, pr=True)
    assert 'Proposal charity' in summary
    assert 'Failed charity' not in summary
    assert 'fetched_content_hash' in summary
