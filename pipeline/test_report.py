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
    assert 'python pipeline/review.py approve' in summary


def test_provider_message_and_new_counts_are_shown():
    report = {'ai_configured': True, 'ai_successful_calls': 0,
              'human_review_count': 0, 'failed_count': 1, 'refused_count': 2,
              'deferred_count': 3, 'published_count': 0, 'unchanged_count': 0,
              'ai_diagnostics': [{'provider': 'gemini', 'model': 'm', 'reason': 'rejected',
                                  'status': 400, 'message': 'INVALID_ARGUMENT bad | schema'}],
              'results': [{'name': 'Blocked charity', 'outcome': 'source_refused',
                           'reasons': ['HTTP 403']}]}
    summary = render(report)
    assert 'INVALID_ARGUMENT bad \\| schema' in summary
    assert 'Refused by site: **2**' in summary and '**3**' in summary
    assert 'HTTP 400' in summary
    assert 'Blocked charity' in summary
