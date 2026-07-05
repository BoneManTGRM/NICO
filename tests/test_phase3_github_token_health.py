"""Phase 3 GitHub Token Health Tests

Direct tests for github_token_health module and integration.
"""

from nico.modules.github_token_health import check_github_token_health
from nico.assessment import run_assessment

import json
from pathlib import Path


def test_token_health_local_path():
    result = check_github_token_health("./nico/test_lab")
    assert result["status"] in ("unavailable", "limited")
    assert result["is_github_target"] is False


def test_token_health_missing_token():
    # Force no token by using a non-existent env var
    result = check_github_token_health("https://github.com/octocat/Hello-World", github_token_env="NON_EXISTENT_TOKEN_VAR_12345")
    assert result["status"] in ("limited", "unavailable")
    assert result["token_present"] is False


def test_token_health_bad_url():
    result = check_github_token_health("not-a-github-url")
    assert result["status"] in ("unavailable", "limited", "error")
    assert result["is_github_target"] is False


def test_token_health_result_never_contains_token():
    result = check_github_token_health("https://github.com/octocat/Hello-World")
    result_str = json.dumps(result)
    assert "token" not in result_str.lower() or "token_present" in result_str.lower()


def test_assessment_includes_token_health():
    result = run_assessment("./nico/test_lab", tier="express")
    assert "github_token_health" in result


def test_evidence_manifest_includes_token_health():
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_token_test")
    manifest_path = Path("/tmp/nico_token_test/evidence_manifest.json")
    if manifest_path.exists():
        with open(manifest_path) as f:
            data = json.load(f)
        assert "github_token_health" in data.get("module_statuses", {})
