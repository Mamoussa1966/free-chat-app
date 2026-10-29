from datetime import datetime, timezone

import pytest

from scripts import production_status_report as report


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
PRODUCTION_SHA = "a" * 40


def _branch(sha=PRODUCTION_SHA):
    return {
        "name": "gitops-v0.4-final",
        "commit": {
            "sha": sha,
            "html_url": f"https://github.com/example/repo/commit/{sha}",
        },
    }


def _run(run_id, sha, *, conclusion, created_at="2026-10-29T11:00:00Z",
         branch="gitops-v0.4-final", path=".github/workflows/ci.yml"):
    return {
        "id": run_id,
        "name": "AI Council CI",
        "path": path,
        "head_branch": branch,
        "head_sha": sha,
        "event": "push",
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created_at,
        "updated_at": created_at,
        "html_url": f"https://github.com/example/repo/actions/runs/{run_id}",
    }


def test_exact_production_commit_ci_success_is_pass_and_closure_is_separate():
    ci_run = _run(101, PRODUCTION_SHA, conclusion="success")
    closure_run = _run(
        202, "b" * 40, conclusion="success",
        branch="evidence/closure", path=".github/workflows/hotfix164-30-deployment-commit-closure.yml",
    )
    result = report.build_report(
        _branch(),
        {"workflow_runs": [ci_run]},
        {"workflow_runs": [closure_run]},
        now=NOW,
    )

    assert result["report_status"] == "PASS"
    assert result["production"]["commit_sha"] == PRODUCTION_SHA
    assert result["ci"]["current_commit_status"] == "PASS"
    assert result["ci"]["latest_run_for_current_commit"]["id"] == 101
    assert result["deployment_closure"]["latest_workflow_run"]["id"] == 202
    assert result["deployment_closure"]["this_report_proves_current_live_deployment"] is False
    assert result["report_is_read_only"] is True


def test_failure_counts_and_recent_failure_link_are_reported_without_claiming_pass():
    failed = _run(103, PRODUCTION_SHA, conclusion="failure", created_at="2026-10-28T11:00:00Z")
    cancelled = _run(104, "c" * 40, conclusion="cancelled")
    old_failure = _run(105, "d" * 40, conclusion="failure", created_at="2026-09-01T00:00:00Z")
    result = report.build_report(
        _branch(),
        {"workflow_runs": [failed, cancelled, old_failure]},
        {"workflow_runs": []},
        now=NOW,
    )

    assert result["report_status"] == "WARN"
    assert result["ci"]["current_commit_status"] == "FAIL"
    assert result["ci"]["last_30_days"]["failures"] == 1
    assert result["ci"]["last_30_days"]["cancelled"] == 1
    assert [r["id"] for r in result["ci"]["last_30_days"]["latest_failures"]] == [103]


def test_no_exact_commit_ci_run_is_not_misreported_as_success():
    other_commit_run = _run(106, "e" * 40, conclusion="success")
    result = report.build_report(
        _branch(),
        {"workflow_runs": [other_commit_run]},
        {"workflow_runs": []},
        now=NOW,
    )
    assert result["ci"]["current_commit_status"] == "NOT_FOUND"
    assert result["ci"]["latest_run_for_current_commit"] is None
    assert result["report_status"] == "WARN"


def test_invalid_production_sha_fails_closed():
    with pytest.raises(ValueError, match="valid production commit SHA"):
        report.build_report(
            _branch("not-a-sha"),
            {"workflow_runs": []},
            {"workflow_runs": []},
            now=NOW,
        )


def test_collect_report_uses_only_read_only_metadata_endpoints():
    calls = []
    payloads = {
        "/repos/example/repo/branches/gitops-v0.4-final": _branch(),
        "/repos/example/repo/actions/workflows/ci.yml/runs?branch=gitops-v0.4-final&per_page=100": {
            "workflow_runs": [_run(107, PRODUCTION_SHA, conclusion="success")]
        },
        "/repos/example/repo/actions/workflows/hotfix164-30-deployment-commit-closure.yml/runs?per_page=20": {
            "workflow_runs": []
        },
    }

    def fake_get(path):
        calls.append(path)
        return payloads[path]

    result = report.collect_report(
        "example/repo", "not-logged",
        get_json=fake_get, now=NOW,
    )

    assert result["report_status"] == "PASS"
    assert len(calls) == 3
    assert all("/branches/" in p or "/actions/workflows/" in p for p in calls)
    assert all("/dispatches" not in p for p in calls)
