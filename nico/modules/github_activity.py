"""GitHub Activity Module (Phase 2)

Basic structure for analyzing recent engineering activity.
Real GitHub API usage will be added later when token is provided.
"""

from datetime import datetime, timedelta


def analyze_activity(target: str, token: str | None = None, months: int = 6) -> dict:
    result = {
        "target": target,
        "period_months": months,
        "status": "limited",
        "activity": {},
        "limitations": []
    }

    if not target.startswith("https://github.com"):
        result["limitations"].append("GitHub activity analysis only supports GitHub URLs")
        result["status"] = "not_applicable"
        return result

    if not token:
        result["limitations"].append("No GitHub token provided — activity data is limited to static analysis")
        result["limitations"].append("Recent commits/PRs require --github-token-env or GITHUB_TOKEN")
        result["activity"]["note"] = "Token required for real commit/PR history"
        return result

    # Placeholder for future real implementation
    result["status"] = "not_implemented_yet"
    result["limitations"].append("Real GitHub API call not yet implemented in Phase 2")
    return result
