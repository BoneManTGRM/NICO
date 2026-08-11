from __future__ import annotations

from pathlib import Path

from nico.runtime_deployment_commit_resolution import runtime_deployment_resolution


SOURCE = Path("nico/runtime_deployment_commit_resolution.py").read_text(encoding="utf-8")


def test_railway_provider_exact_sha_resolves_without_external_lookup() -> None:
    sha = "a" * 40
    result = runtime_deployment_resolution(
        {
            "repository": "BoneManTGRM/NICO",
            "expected_commit_sha": sha,
        },
        environ={
            "RAILWAY_GIT_COMMIT_SHA": sha,
            "RAILWAY_GIT_REPO_OWNER": "BoneManTGRM",
            "RAILWAY_GIT_REPO_NAME": "NICO",
            "RAILWAY_GIT_BRANCH": "main",
        },
    )
    assert result is not None
    assert result["status"] == "attached"
    assert result["repository"] == "BoneManTGRM/NICO"
    assert result["commit_sha"] == sha
    assert result["commit_capture_method"] == "railway_git_commit_sha"
    assert result["api_commit_lookup_attempts"] == 0
    assert result["public_git_fallback_attempted"] is False
    assert result["exact_commit_verified"] is True


def test_provider_resolution_refuses_repository_or_sha_mismatch() -> None:
    sha = "b" * 40
    env = {
        "RAILWAY_GIT_COMMIT_SHA": sha,
        "RAILWAY_GIT_REPO_OWNER": "BoneManTGRM",
        "RAILWAY_GIT_REPO_NAME": "NICO",
        "RAILWAY_GIT_BRANCH": "main",
    }
    assert runtime_deployment_resolution(
        {"repository": "Other/Repo", "expected_commit_sha": sha},
        environ=env,
    ) is None
    assert runtime_deployment_resolution(
        {"repository": "BoneManTGRM/NICO", "expected_commit_sha": "c" * 40},
        environ=env,
    ) is None


def test_comprehensive_intake_callsite_gets_provider_preverified_resolution() -> None:
    assert "def _install_comprehensive_intake_capture()" in SOURCE
    assert "from nico import comprehensive_api_routes" in SOURCE
    assert 'enriched["exact_commit_resolution"] = runtime' in SOURCE
    assert "comprehensive_api_routes.capture_repository_snapshot = capture" in SOURCE
    assert '"external_repository_fallback_preserved": True' in SOURCE
    assert '"private_repository_policy_preserved": True' in SOURCE
    assert '"human_review_required": True' in SOURCE
    assert '"client_delivery_allowed": False' in SOURCE
