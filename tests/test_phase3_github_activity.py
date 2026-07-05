"""Phase 3 GitHub Activity Direct Tests

Covers github_activity.py behavior directly.
"""

import pytest
from nico.modules.github_activity import analyze_github_activity
from nico.assessment import run_assessment


def test_github_activity_local_path_unavailable():
    result = analyze_github_activity("./nico/test_lab")
    assert result["status"] in ("unavailable", "limited")
    assert result["is_github_target"] is False
    assert "Not a GitHub" in str(result.get("limitations", [])) or result["status"] == "limited"


def test_assessment_express_includes_github_activity():
    result = run_assessment("./nico/test_lab", tier="express")
    assert "github_activity" in result
    gh = result["github_activity"]
    assert gh["status"] in ("unavailable", "limited")
    assert gh["is_github_target"] is False


def test_github_activity_non_crash_on_bad_url():
    result = analyze_github_activity("not-a-real-url-12345")
    assert result["status"] in ("unavailable", "limited", "error")
    assert result["is_github_target"] is False


def test_github_activity_module_has_required_fields():
    result = analyze_github_activity("https://github.com/octocat/Hello-World")
    # Even if limited/unavailable, these keys must exist
    for key in ["status", "lookback_months", "is_github_target", "commit_count", "pr_count", "signals", "velocity_classification", "consistency_classification", "limitations"]:
        assert key in result
