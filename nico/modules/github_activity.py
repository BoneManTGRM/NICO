"""GitHub Activity Module (Phase 3)

Safe GitHub activity analysis for public repos. Requires token for reliable/private data.
"""

import os
from datetime import datetime, timedelta, timezone

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


def analyze_github_activity(target: str, months: int = 6, github_token_env: str | None = None) -> dict:
    result = {
        "status": "unavailable",
        "lookback_months": months,
        "is_github_target": False,
        "commit_count": 0,
        "pr_count": 0,
        "active_authors_count": 0,
        "signals": [],
        "velocity_classification": "unknown",
        "consistency_classification": "unknown",
        "limitations": []
    }

    if not _is_github_url(target):
        result["limitations"].append("Not a GitHub repository URL")
        return result

    result["is_github_target"] = True
    owner, repo = _parse_repo(target)
    if not owner or not repo:
        result["limitations"].append("Could not parse owner/repo")
        return result

    if not HAS_REQUESTS:
        result["status"] = "limited"
        result["limitations"].append("requests not installed; install it for GitHub activity analysis")
        return result

    token = os.getenv(github_token_env) if github_token_env else None
    if not token:
        token = os.getenv("GITHUB_TOKEN")

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NICO-Assessment"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    since_dt = datetime.now(timezone.utc) - timedelta(days=30 * months)
    since = since_dt.isoformat()

    try:
        # Commits
        commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits?since={since}&per_page=100"
        resp = requests.get(commits_url, headers=headers, timeout=20)
        if resp.status_code == 200:
            commits = resp.json() or []
            result["commit_count"] = len(commits)
            authors = {c.get("author", {}).get("login") or c.get("commit", {}).get("author", {}).get("name") for c in commits if c.get("author") or c.get("commit")}
            result["active_authors_count"] = len([a for a in authors if a])
        elif resp.status_code in (401, 403, 404):
            result["status"] = "limited"
            result["limitations"].append("Repository may be private or token/rate limit issue")
            return result
        else:
            result["status"] = "limited"
            result["limitations"].append(f"GitHub commits API returned {resp.status_code}")
            return result

        # PRs
        prs_url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100"
        resp = requests.get(prs_url, headers=headers, timeout=20)
        if resp.status_code == 200:
            prs = resp.json() or []
            recent_prs = [p for p in prs if p.get("updated_at", "") >= since]
            result["pr_count"] = len(recent_prs)

        # Classification (conservative)
        if result["commit_count"] == 0 and result["pr_count"] == 0:
            result["signals"].append("No recent activity detected")
            result["velocity_classification"] = "low"
            result["consistency_classification"] = "stale"
        elif result["pr_count"] < 5:
            result["signals"].append("Low PR activity in last 6 months")
            result["velocity_classification"] = "low"
        else:
            result["velocity_classification"] = "moderate"

        if result["active_authors_count"] >= 3:
            result["signals"].append("Multiple active contributors")

        result["status"] = "completed" if token else "limited"

        if not token:
            result["limitations"].append("No GITHUB_TOKEN; data limited to public unauthenticated API (rate limits apply)")

    except Exception:
        result["status"] = "error"
        result["limitations"].append("GitHub activity fetch error: request failed")

    return result
