#!/usr/bin/env python3
"""Read-only GitHub status report for the AI Council production baseline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

FAILURE_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure"}
CANCELLED_CONCLUSIONS = {"cancelled"}
DEFAULT_PRODUCTION_BRANCH = "gitops-v0.4-final"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _run_projection(run: dict[str, Any]) -> dict[str, Any]:
    """Return useful non-sensitive workflow metadata only."""
    keys = ("id", "name", "path", "head_branch", "head_sha", "event", "status",
            "conclusion", "created_at", "updated_at", "html_url")
    aliases = {"path": "workflow_path", "head_branch": "branch"}
    return {aliases.get(key, key): run.get(key) for key in keys}


def build_report(
    branch_data: dict[str, Any],
    ci_data: dict[str, Any],
    closure_data: dict[str, Any],
    *,
    production_branch: str = DEFAULT_PRODUCTION_BRANCH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic report from GitHub API payloads."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    commit = branch_data.get("commit") if isinstance(branch_data, dict) else None
    commit = commit if isinstance(commit, dict) else {}
    commit_sha = str(commit.get("sha") or "").strip().lower()
    if len(commit_sha) != 40 or any(ch not in "0123456789abcdef" for ch in commit_sha):
        raise ValueError("GitHub did not return a valid production commit SHA")

    raw_ci_runs = ci_data.get("workflow_runs", []) if isinstance(ci_data, dict) else []
    ci_runs = [r for r in raw_ci_runs if isinstance(r, dict)]
    matching = [r for r in ci_runs if str(r.get("head_sha") or "").lower() == commit_sha]
    matching.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    latest_for_head = _run_projection(matching[0]) if matching else None

    cutoff = now - timedelta(days=30)
    recent = []
    for run in ci_runs:
        created = _parse_time(run.get("created_at"))
        if created is not None and cutoff <= created <= now:
            recent.append(run)
    failures = [_run_projection(r) for r in recent
                if str(r.get("conclusion") or "").lower() in FAILURE_CONCLUSIONS]
    cancelled = [_run_projection(r) for r in recent
                 if str(r.get("conclusion") or "").lower() in CANCELLED_CONCLUSIONS]
    successes = sum(str(r.get("conclusion") or "").lower() == "success" for r in recent)

    if latest_for_head is None:
        current_ci_status = "NOT_FOUND"
    elif latest_for_head.get("status") != "completed":
        current_ci_status = "IN_PROGRESS"
    elif latest_for_head.get("conclusion") == "success":
        current_ci_status = "PASS"
    elif latest_for_head.get("conclusion") in FAILURE_CONCLUSIONS:
        current_ci_status = "FAIL"
    elif latest_for_head.get("conclusion") in CANCELLED_CONCLUSIONS:
        current_ci_status = "CANCELLED"
    else:
        current_ci_status = "UNKNOWN"

    raw_closure = closure_data.get("workflow_runs", []) if isinstance(closure_data, dict) else []
    closure_runs = [r for r in raw_closure if isinstance(r, dict)]
    closure_runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    latest_closure = _run_projection(closure_runs[0]) if closure_runs else None

    return {
        "schema": "ai-council-production-status-report/v1",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "report_status": "PASS" if current_ci_status == "PASS" else "WARN",
        "report_is_read_only": True,
        "production": {
            "branch": production_branch,
            "commit_sha": commit_sha,
            "commit_url": commit.get("html_url"),
        },
        "ci": {
            "current_commit_status": current_ci_status,
            "latest_run_for_current_commit": latest_for_head,
            "last_30_days": {
                "runs_seen": len(recent),
                "successes": successes,
                "failures": len(failures),
                "cancelled": len(cancelled),
                "latest_failures": sorted(
                    failures, key=lambda r: str(r.get("created_at") or ""), reverse=True
                )[:10],
            },
        },
        "deployment_closure": {
            "latest_workflow_run": latest_closure,
            "this_report_proves_current_live_deployment": False,
            "interpretation": (
                "Closure workflow status is reported separately. Green CI or a closure run "
                "on another commit does not prove that the currently served app matches "
                "the production branch."
            ),
        },
    }


def _api_get(
    path: str,
    *,
    api_base_url: str,
    token: str,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-council-production-status-report",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(api_base_url.rstrip("/") + path, headers=headers, method="GET")
    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API GET failed with HTTP {exc.code} for requested path") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"GitHub API GET failed: {exc.__class__.__name__}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"GitHub API returned invalid JSON: {exc.__class__.__name__}") from None
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected payload")
    return payload


def collect_report(
    repository: str,
    token: str,
    *,
    api_base_url: str = "https://api.github.com",
    production_branch: str = DEFAULT_PRODUCTION_BRANCH,
    now: datetime | None = None,
    get_json: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch branch, CI, and closure metadata through read-only GitHub endpoints."""
    if not repository or "/" not in repository:
        raise ValueError("GITHUB_REPOSITORY must be in owner/name format")
    branch = quote(production_branch, safe="")
    repo_path = "/repos/" + repository
    if get_json is None:
        def get_json(path: str) -> dict[str, Any]:
            return _api_get(path, api_base_url=api_base_url, token=token)
    branch_data = get_json(f"{repo_path}/branches/{branch}")
    ci_data = get_json(f"{repo_path}/actions/workflows/ci.yml/runs?branch={branch}&per_page=100")
    closure_data = get_json(
        f"{repo_path}/actions/workflows/hotfix164-30-deployment-commit-closure.yml/runs?per_page=20"
    )
    return build_report(
        branch_data, ci_data, closure_data,
        production_branch=production_branch, now=now,
    )


def _markdown_summary(report: dict[str, Any]) -> str:
    prod, ci = report["production"], report["ci"]
    recent = ci["last_30_days"]
    closure = report["deployment_closure"]["latest_workflow_run"]
    lines = [
        "# AI Council production status",
        "",
        f"- Report status: **{report['report_status']}**",
        f"- Production branch: {prod['branch']}",
        f"- Production commit: {prod['commit_sha']}",
        f"- Exact-commit CI status: **{ci['current_commit_status']}**",
        f"- CI runs in last 30 days: {recent['runs_seen']} (success {recent['successes']}, failures {recent['failures']}, cancelled {recent['cancelled']})",
    ]
    if prod.get("commit_url"):
        lines.append(f"- Commit link: {prod['commit_url']}")
    exact_run = ci.get("latest_run_for_current_commit")
    if exact_run and exact_run.get("html_url"):
        lines.append(f"- Exact-commit CI run: {exact_run['html_url']}")
    if recent["latest_failures"]:
        lines += ["", "## Recent CI failures"]
        for run in recent["latest_failures"]:
            lines.append(f"- {run.get('created_at')}: {run.get('name')} — {run.get('conclusion')} — {run.get('html_url')}")
    lines += ["", "## Deployment closure"]
    if closure:
        lines.append(
            f"- Latest closure run: {closure.get('conclusion') or closure.get('status')} "
            f"on branch {closure.get('branch')} at {closure.get('head_sha')} "
            f"({closure.get('html_url')})"
        )
    else:
        lines.append("- No closure workflow run was returned by GitHub.")
    lines += [
        "",
        "**Important:** this read-only report does not call providers, change refs, or prove the currently served app matches the production commit. Deployment proof remains the separate fresh-evidence closure gate.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com").strip()
    branch = os.environ.get("PRODUCTION_BRANCH", DEFAULT_PRODUCTION_BRANCH).strip()
    output = Path(os.environ.get("REPORT_OUTPUT", "dist/AI_COUNCIL_PRODUCTION_STATUS_REPORT.json"))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    try:
        report = collect_report(repository, token, api_base_url=api_base, production_branch=branch)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = _markdown_summary(report)
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(summary + "\n")
        print(json.dumps({
            "report_file": str(output),
            "report_status": report["report_status"],
            "production_commit_sha": report["production"]["commit_sha"],
            "current_commit_ci_status": report["ci"]["current_commit_status"],
            "ci_failure_count_last_30_days": report["ci"]["last_30_days"]["failures"],
            "provider_api_calls": 0,
            "repository_mutations": 0,
        }, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"STATUS_REPORT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
