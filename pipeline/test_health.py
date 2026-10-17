"""The status issue: silence must mean nothing needs you, and noise must mean
something does. Offline: GitHub is a recording fake."""
import json

import pytest

import health
from health import assess_deploy, assess_refresh, render, sync

RUN, REPO = "https://github.com/o/r/actions/runs/1", "https://github.com/o/r"


def review(**kw):
    base = {"ai_configured": True, "ai_broken": False, "ai_diagnostics": [],
            "median_days_since_check": 3, "site_banner": False, "results": [],
            "confirmed_count": 20, "unchanged_count": 3, "published_count": 0}
    base.update(kw)
    return base


def result(org_id, outcome, reasons=("x",)):
    return {"org_id": org_id, "name": org_id.title(), "outcome": outcome,
            "reasons": list(reasons), "roles_before": 2, "roles_after": 3}


# ------------------------------------------------------------------ assessing

def test_a_quiet_week_needs_nobody():
    a = assess_refresh(review(results=[result("akt", "source_refused"),
                                       result("crisis", "confirmed"),
                                       result("spear", "ai_deferred")]), "success")
    assert a.level == "ok"


def test_failing_before_any_page_is_broken_and_says_where_to_look():
    a = assess_refresh(None, "failure")
    assert a.level == "broken"
    assert "pytest pipeline/ site/" in render(a, RUN, REPO)


@pytest.mark.parametrize("diag,advice", [
    ({"reason": "auth", "status": 403}, "GEMINI_API_KEY"),
    ({"reason": "rejected", "status": 400}, "invalid or deleted key"),
    ({"reason": "model_unavailable", "status": 404}, "AI_GEMINI_MODELS"),
    ({"reason": "rate_limited", "status": 429}, "clears by itself")])
def test_broken_ai_names_the_fix_for_the_failure_seen(diag, advice):
    a = assess_refresh(review(ai_broken=True, ai_diagnostics=[diag]), "failure")
    assert a.level == "broken" and advice in render(a, RUN, REPO)


def test_no_provider_configured_says_which_setting():
    a = assess_refresh(review(ai_broken=True, ai_configured=False), "failure")
    assert "AI_GEMINI_FREE_TIER_CONFIRMED" in render(a, RUN, REPO)


def test_waiting_decisions_are_listed_with_their_ids():
    a = assess_refresh(review(results=[result("crisis", "review_required"),
                                       result("shelter", "review_required")]), "success")
    body = render(a, RUN, REPO)
    assert a.level == "attention" and a.waiting == ["crisis", "shelter"]
    assert "(`crisis`)" in body and "Review a proposal" in body


def test_one_bad_page_is_information_not_an_alarm():
    a = assess_refresh(review(results=[result("st-mungos", "extraction_failed")]), "success")
    assert a.level == "ok"


def test_roles_on_a_platform_we_cannot_read_are_never_silent():
    """Crisis held 4 of 80 offers for weeks because nothing said its board was unread."""
    gap = {**result("shelter", "confirmed"), "unread_platforms": ["app.betterimpact.com"]}
    a = assess_refresh(review(results=[gap, result("akt", "confirmed")]), "success")
    body = render(a, RUN, REPO)
    assert a.level == "attention" and "Roles we cannot see" in body
    section = body.split("Roles we cannot see")[1].split("###")[0]
    assert "Shelter" in section and "app.betterimpact.com" in section
    assert "platforms_acknowledged" in section and "Akt" not in section


def test_an_unreadable_board_is_reported_and_leaves_roles_alone():
    a = assess_refresh(review(results=[result("crisis", "board_failed",
                                              ["board not read: board feed answered HTTP 503"])]),
                       "success")
    body = render(a, RUN, REPO)
    assert a.level == "attention" and "could not be read" in body and "HTTP 503" in body


def test_failing_links_need_a_person():
    a = assess_refresh(review(results=[result("ace-of-clubs", "source_failed",
                                              ["certificate has expired"])]), "success")
    assert a.level == "attention" and "volunteer_url" in render(a, RUN, REPO)


@pytest.mark.parametrize("median,banner,level", [(44, False, "ok"), (45, False, "attention"),
                                                 (61, True, "attention")])
def test_freshness_warns_before_the_paper_suspends_itself(median, banner, level):
    a = assess_refresh(review(median_days_since_check=median, site_banner=banner), "success")
    assert a.level == level


def test_deploy_states():
    assert assess_deploy("failure", True).level == "broken"
    unconfigured = assess_deploy("success", False)
    assert unconfigured.level == "attention"
    assert "CLOUDFLARE_API_TOKEN" in render(unconfigured, RUN, REPO)
    assert assess_deploy("success", True).level == "ok"


def test_render_carries_a_machine_readable_marker():
    a = assess_refresh(review(results=[result("crisis", "review_required")]), "success")
    assert "<!-- health level=attention waiting=crisis -->" in render(a, RUN, REPO)


# ------------------------------------------------------------------ syncing

class FakeGitHub:
    def __init__(self, open_issue=None):
        self.open_issue, self.calls = open_issue, []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([self.open_issue] if self.open_issue else [])
        return ""

    def did(self, *verb):
        return [c for c in self.calls if c[:len(verb)] == list(verb)]


def existing(level="attention", waiting=""):
    return {"number": 7, "body": f"old\n<!-- health level={level} waiting={waiting} -->"}


def attention(*waiting):
    return assess_refresh(review(results=[result(w, "review_required") for w in waiting]),
                          "success")


def test_a_new_problem_opens_an_issue():
    gh = FakeGitHub()
    assert sync(attention("crisis"), RUN, REPO, gh) == "opened"
    create = gh.did("issue", "create")[0]
    assert "status: refresh" in create and health.TITLES[("refresh", "attention")] in create


def test_the_same_problem_next_week_edits_without_emailing():
    gh = FakeGitHub(existing(waiting="crisis"))
    assert sync(attention("crisis"), RUN, REPO, gh) == "updated"
    assert gh.did("issue", "edit") and not gh.did("issue", "comment")


def test_new_decisions_comment_so_you_hear_about_them():
    gh = FakeGitHub(existing(waiting="crisis"))
    sync(attention("crisis", "shelter"), RUN, REPO, gh)
    comment = gh.did("issue", "comment")
    assert comment and "`shelter`" in comment[0][-1] and "`crisis`" not in comment[0][-1]


def test_getting_worse_comments():
    gh = FakeGitHub(existing("attention"))
    sync(assess_refresh(None, "failure"), RUN, REPO, gh)
    assert "Worse since last time" in gh.did("issue", "comment")[0][-1]


def test_a_broken_refresh_reminds_every_week():
    gh = FakeGitHub(existing("broken"))
    sync(assess_refresh(None, "failure"), RUN, REPO, gh)
    assert "Still broken" in gh.did("issue", "comment")[0][-1]


def test_a_broken_deploy_does_not_comment_every_day():
    gh = FakeGitHub({"number": 3, "body": "<!-- health level=broken waiting= -->"})
    sync(assess_deploy("failure", True), RUN, REPO, gh)
    assert gh.did("issue", "edit") and not gh.did("issue", "comment")


def test_all_clear_closes_the_issue():
    gh = FakeGitHub(existing())
    assert sync(assess_refresh(review(), "success"), RUN, REPO, gh) == "closed"
    assert gh.did("issue", "close")


def test_all_clear_with_no_issue_does_nothing():
    gh = FakeGitHub()
    assert sync(assess_refresh(review(), "success"), RUN, REPO, gh) == "nothing"
    assert len(gh.calls) == 1


def test_dry_runs_never_touch_the_issue(tmp_path, monkeypatch):
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review(dry_run=True)), encoding="utf-8")
    monkeypatch.setattr(health, "sync", lambda *a: pytest.fail("dry run"))
    assert health.main(["refresh", "--job-status", "success", "--run-url", RUN,
                        "--repo-url", REPO, "--review", str(path)]) == 0


def test_github_trouble_warns_instead_of_failing_the_job(tmp_path, monkeypatch, capsys):
    def broken(*a):
        raise OSError("gh not found")
    monkeypatch.setattr(health, "_gh", broken)
    monkeypatch.setattr(health, "sync", lambda a, r, u, **k: health.__dict__["_gh"]([]))
    assert health.main(["deploy", "--job-status", "failure", "--run-url", RUN,
                        "--repo-url", REPO]) == 0
    assert "::warning::" in capsys.readouterr().out


def test_a_review_decision_never_clears_a_broken_refresh():
    gh = FakeGitHub(existing("broken"))
    assert sync(assess_refresh(review(), "success"), RUN, REPO, gh, keep_broken=True) == "left broken"
    assert len(gh.calls) == 1


def test_a_blocked_allowance_checkpoint_is_explained():
    diags = [{"reason": "budget_exhausted",
              "message": "could not persist AI allowance; no request sent"}]
    a = assess_refresh(review(ai_broken=True, ai_diagnostics=diags), "failure")
    assert "could not record its AI allowance" in render(a, RUN, REPO)


def test_unread_additions_are_noted():
    r = dict(result("crisis", "confirmed"), additions_unread="malformed",
             other_roles=["Night shelter"])
    a = assess_refresh(review(results=[r]), "success")
    assert a.level == "ok" and "Night shelter" in render(a, RUN, REPO)
