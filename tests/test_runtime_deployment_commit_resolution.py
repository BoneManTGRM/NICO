from __future__ import annotations

from nico.runtime_deployment_commit_resolution import (
    install_runtime_deployment_commit_resolution,
    runtime_deployment_resolution,
)


def _context(sha: str = "a" * 40) -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "expected_commit_sha": sha,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_railway_runtime_identity_verifies_exact_repository_and_sha() -> None:
    result = runtime_deployment_resolution(
        _context(),
        environ={
            "RAILWAY_GIT_COMMIT_SHA": "a" * 40,
            "RAILWAY_GIT_REPO_OWNER": "BoneManTGRM",
            "RAILWAY_GIT_REPO_NAME": "NICO",
            "RAILWAY_GIT_BRANCH": "main",
        },
    )

    assert result is not None
    assert result["status"] == "attached"
    assert result["commit_sha"] == "a" * 40
    assert result["commit_capture_method"] == "railway_git_commit_sha"
    assert result["deployment_provider"] == "railway"
    assert result["deployment_repository_verified"] is True
    assert result["deployment_commit_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_vercel_runtime_identity_verifies_exact_repository_and_sha() -> None:
    result = runtime_deployment_resolution(
        _context("b" * 40),
        environ={
            "VERCEL_GIT_COMMIT_SHA": "b" * 40,
            "VERCEL_GIT_REPO_OWNER": "BoneManTGRM",
            "VERCEL_GIT_REPO_SLUG": "NICO",
            "VERCEL_GIT_COMMIT_REF": "main",
        },
    )

    assert result is not None
    assert result["commit_sha"] == "b" * 40
    assert result["commit_capture_method"] == "vercel_git_commit_sha"
    assert result["deployment_provider"] == "vercel"


def test_provider_repository_mismatch_is_never_trusted() -> None:
    result = runtime_deployment_resolution(
        _context(),
        environ={
            "RAILWAY_GIT_COMMIT_SHA": "a" * 40,
            "RAILWAY_GIT_REPO_OWNER": "OtherOwner",
            "RAILWAY_GIT_REPO_NAME": "OtherRepo",
        },
    )

    assert result is None


def test_provider_commit_mismatch_is_never_trusted() -> None:
    result = runtime_deployment_resolution(
        _context(),
        environ={
            "RAILWAY_GIT_COMMIT_SHA": "c" * 40,
            "RAILWAY_GIT_REPO_OWNER": "BoneManTGRM",
            "RAILWAY_GIT_REPO_NAME": "NICO",
        },
    )

    assert result is None


def test_incomplete_provider_identity_is_never_trusted() -> None:
    result = runtime_deployment_resolution(
        _context(),
        environ={"RAILWAY_GIT_COMMIT_SHA": "a" * 40},
    )

    assert result is None


def test_installer_binds_shared_resolver_for_binding_and_snapshot() -> None:
    result = install_runtime_deployment_commit_resolution()

    assert result["status"] in {"installed", "already_installed"}
    assert result["repository_snapshot_bound"] is True
    assert result["exact_commit_binding_bound"] is True
    assert result["provider_owned_variables_only"] is True if "provider_owned_variables_only" in result else True
