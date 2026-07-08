from __future__ import annotations

from typing import Any, Callable

import nico.hosted_assessment as hosted_assessment
from nico.github_app_auth import build_github_auth_headers

_ORIGINAL_RUN_GITHUB_ASSESSMENT = hosted_assessment.run_github_assessment


class MetadataAuthGitHubAssessmentClient(hosted_assessment.GitHubAssessmentClient):
    """GitHub metadata client that prefers GitHub App installation auth."""

    def __init__(self, *, session: Any | None = None) -> None:
        auth = build_github_auth_headers(session=session) if session is not None else build_github_auth_headers()
        self.headers = dict(auth.headers)
        self.auth_mode = auth.mode
        self.auth_evidence = list(auth.evidence)
        self.auth_unavailable = list(auth.unavailable)


def github_metadata_auth_summary(client: Any) -> dict[str, Any]:
    return {
        "mode": getattr(client, "auth_mode", "unknown"),
        "evidence": list(getattr(client, "auth_evidence", [])),
        "unavailable": list(getattr(client, "auth_unavailable", [])),
    }


def run_github_assessment_with_metadata_auth(
    payload: dict[str, Any],
    *,
    client_factory: Callable[[], Any] | None = None,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run hosted assessment with GitHub App-aware metadata auth.

    The existing hosted assessment function creates its own metadata client. This
    wrapper swaps in an auth-aware compatible client for the duration of one run
    and restores the original class immediately after the call.
    """
    created_clients: list[Any] = []
    factory = client_factory or MetadataAuthGitHubAssessmentClient
    assessment_runner = runner or _ORIGINAL_RUN_GITHUB_ASSESSMENT

    def _client_factory() -> Any:
        client = factory()
        created_clients.append(client)
        return client

    original_client = hosted_assessment.GitHubAssessmentClient
    hosted_assessment.GitHubAssessmentClient = _client_factory  # type: ignore[assignment]
    try:
        result = assessment_runner(payload)
    finally:
        hosted_assessment.GitHubAssessmentClient = original_client

    if isinstance(result, dict) and created_clients:
        auth_summary = github_metadata_auth_summary(created_clients[0])
        result["github_metadata_auth"] = auth_summary
        unavailable = auth_summary.get("unavailable") or []
        if unavailable:
            result.setdefault("unavailable_data_notes", []).extend(unavailable)
    return result


def install_metadata_auth_for_hosted_assessment() -> None:
    """Make hosted_assessment.run_github_assessment use metadata auth by default."""
    hosted_assessment.run_github_assessment = run_github_assessment_with_metadata_auth  # type: ignore[assignment]
