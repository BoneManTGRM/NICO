from __future__ import annotations

from nico.express_async_api import ExpressAssessmentRunRequest, _model_payload, _safe_request
from nico.runtime_deployment_commit_resolution import runtime_deployment_resolution


def _railway_environment(sha: str) -> dict[str, str]:
    return {
        "RAILWAY_GIT_COMMIT_SHA": sha,
        "RAILWAY_GIT_REPO_OWNER": "BoneManTGRM",
        "RAILWAY_GIT_REPO_NAME": "NICO",
        "RAILWAY_GIT_BRANCH": "main",
    }


def test_express_authorization_marker_survives_async_request_and_resolves_current_release() -> None:
    sha = "a" * 40
    request = ExpressAssessmentRunRequest(
        repository="BoneManTGRM/NICO",
        authorized=True,
        authorization_confirmed=True,
        customer_id="customer_release",
        project_id="project_release",
        authorized_by=f"public_assessment_requester;expected_commit_sha={sha}",
    )

    payload = _model_payload(request)
    persisted_request = _safe_request(payload)

    assert persisted_request["authorized_by"].endswith(f"expected_commit_sha={sha}")
    result = runtime_deployment_resolution(
        persisted_request,
        environ=_railway_environment(sha),
    )

    assert result is not None
    assert result["status"] == "attached"
    assert result["commit_sha"] == sha
    assert result["commit_capture_method"] == "railway_git_commit_sha"
    assert result["api_commit_lookup_attempts"] == 0
    assert result["public_git_fallback_attempted"] is False
    assert result["authorization_marker_supported"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_marker_commit_must_match_provider_release_exactly() -> None:
    requested = "a" * 40
    deployed = "b" * 40
    context = {
        "repository": "BoneManTGRM/NICO",
        "authorized_by": f"public_assessment_requester;expected_commit_sha={requested}",
    }

    assert runtime_deployment_resolution(
        context,
        environ=_railway_environment(deployed),
    ) is None


def test_invalid_authorization_marker_is_never_used_as_commit_proof() -> None:
    context = {
        "repository": "BoneManTGRM/NICO",
        "authorized_by": "public_assessment_requester;expected_commit_sha=not-a-sha",
    }

    assert runtime_deployment_resolution(
        context,
        environ=_railway_environment("a" * 40),
    ) is None
