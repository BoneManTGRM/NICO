"""CI/CD Audit Module (Phase 3)

Static file detection + optional GitHub Actions run history when token available.
"""

import os
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from nico.modules.github_url_safety import is_github_repo_url, parse_github_repo


def _is_github_url(target: str) -> bool:
    return is_github_repo_url(target)


def _parse_repo(target: str):
    return parse_github_repo(target)


def audit_cicd(target: str, github_token_env: str | None = None) -> dict:
    result = {
        "target": target,
        "status": "limited",
        "workflows": [],
        "has_ci": False,
        "workflow_runs_count": 0,
        "failed_runs_recent": 0,
        "success_rate": None,
        "last_run_status": None,
        "limitations": []
    }

    # Static file detection (always run)
    path = Path(target)
    if path.exists():
        ci_files = []
        for pattern in [".github/workflows/*.yml", ".github/workflows/*.yaml", "Dockerfile", "docker-compose*.yml", ".gitlab-ci.yml", "Jenkinsfile"]:
            matches = list(path.glob(pattern)) if "*" in pattern else list(path.rglob(pattern))
            ci_files.extend([str(m) for m in matches])

        if ci_files:
            result["has_ci"] = True
            result["workflows"] = ci_files
            result["status"] = "completed"
        else:
            result["limitations"].append("No common CI/CD configuration files found")
    else:
        result["limitations"].append("Target path does not exist for static scan")

    # Dynamic GitHub Actions history (only if GitHub URL + token available)
    if _is_github_url(target) and HAS_REQUESTS:
        token = os.getenv(github_token_env) if github_token_env else os.getenv("GITHUB_TOKEN")
        if token:
            owner, repo = _parse_repo(target)
            if owner and repo:
                headers = {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "NICO-Assessment"
                }
                try:
                    # Get recent workflow runs
                    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=50"
                    resp = requests.get(runs_url, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        runs = resp.json().get("workflow_runs", [])
                        result["workflow_runs_count"] = len(runs)

                        failed = [r for r in runs if r.get("conclusion") == "failure"]
                        result["failed_runs_recent"] = len(failed)

                        if runs:
                            result["last_run_status"] = runs[0].get("conclusion") or runs[0].get("status")

                        if result["workflow_runs_count"] > 0:
                            success = result["workflow_runs_count"] - result["failed_runs_recent"]
                            result["success_rate"] = round(success / result["workflow_runs_count"] * 100, 1)

                        result["status"] = "completed"
                        result["limitations"].append("Includes recent GitHub Actions run history")
                    else:
                        result["limitations"].append(f"GitHub Actions API returned {resp.status_code}")
                except Exception:
                    result["limitations"].append("GitHub Actions history fetch error: request failed")
        else:
            result["limitations"].append("No GITHUB_TOKEN provided; workflow run history not fetched")
    elif _is_github_url(target):
        result["limitations"].append("requests not available or no token for workflow history")

    # Final status logic
    if result["has_ci"] or result["workflow_runs_count"] > 0:
        result["status"] = "completed"

    return result
