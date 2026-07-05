"""GitHub Token Health Module (Phase 3)

Safe pre-check for GitHub token permissions before Activity / CI runs.
Never exposes the token.
"""

import os
from urllib.parse import urlparse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def _is_github_url(target: str) -> bool:
    try:
        p = urlparse(target if target.startswith(('http://', 'https://')) else 'https://' + target)
        return 'github.com' in p.netloc
    except Exception:
        return False


def _parse_repo(target: str):
    try:
        p = urlparse(target if target.startswith(('http://', 'https://')) else 'https://' + target)
        parts = [x for x in p.path.strip('/').split('/') if x]
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None, None


def check_github_token_health(target: str, github_token_env: str | None = None) -> dict:
    result = {
        "status": "unavailable",
        "is_github_target": False,
        "token_present": False,
        "repo_access": False,
        "contents_access": False,
        "pull_requests_access": False,
        "actions_access": False,
        "rate_limit_remaining": None,
        "limitations": []
    }

    if not _is_github_url(target):
        result["limitations"].append("Not a GitHub repository URL")
        return result

    result["is_github_target"] = True

    owner, repo = _parse_repo(target)
    if not owner or not repo:
        result["limitations"].append("Could not parse owner/repo from URL")
        return result

    if not HAS_REQUESTS:
        result["status"] = "limited"
        result["limitations"].append("requests library not available")
        return result

    token = None
    if github_token_env:
        token = os.getenv(github_token_env)
    if not token:
        token = os.getenv("GITHUB_TOKEN")

    result["token_present"] = bool(token)

    if not token:
        result["status"] = "limited"
        result["limitations"].append("No GitHub token configured (GITHUB_TOKEN or github_token_env)")
        return result

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "NICO-TokenHealth"
    }

    try:
        base = f"https://api.github.com/repos/{owner}/{repo}"

        # 1. Repo metadata
        resp = requests.get(base, headers=headers, timeout=10)
        if resp.status_code == 200:
            result["repo_access"] = True
        elif resp.status_code in (401, 403, 404):
            result["limitations"].append("Token cannot access repository metadata (private or insufficient permissions)")
            result["status"] = "limited"
            return result
        else:
            result["limitations"].append(f"Unexpected status checking repo: {resp.status_code}")

        # 2. Contents access
        resp = requests.get(f"{base}/contents?per_page=1", headers=headers, timeout=10)
        if resp.status_code == 200:
            result["contents_access"] = True

        # 3. Pull requests access
        resp = requests.get(f"{base}/pulls?per_page=1&state=all", headers=headers, timeout=10)
        if resp.status_code == 200:
            result["pull_requests_access"] = True

        # 4. Actions access
        resp = requests.get(f"{base}/actions/runs?per_page=1", headers=headers, timeout=10)
        if resp.status_code == 200:
            result["actions_access"] = True

        # 5. Rate limit
        if "X-RateLimit-Remaining" in resp.headers:
            try:
                result["rate_limit_remaining"] = int(resp.headers["X-RateLimit-Remaining"])
            except Exception:
                pass

        if result["repo_access"]:
            result["status"] = "completed"

    except Exception as e:
        result["status"] = "error"
        result["limitations"].append(f"Token health check error: {str(e)[:180]}")

    return result
