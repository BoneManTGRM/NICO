from nico.provider_collection_runtime import (
    CollectionMode,
    CollectionState,
    PaginationCursor,
    RateLimitWindow,
    build_collection_request,
    build_collection_result,
    normalize_collection_mode,
    validate_collection_request,
    validate_collection_result,
)
from nico.provider_neutral_contract import Capability, ProviderKind


def test_collection_mode_aliases_normalize() -> None:
    assert normalize_collection_mode("REST") is CollectionMode.API
    assert normalize_collection_mode("scheduled poll") is CollectionMode.POLL
    assert normalize_collection_mode("event") is CollectionMode.WEBHOOK
    assert normalize_collection_mode("ssh") is CollectionMode.GIT
    assert normalize_collection_mode("upload") is CollectionMode.ARCHIVE


def test_collection_requests_fail_closed_for_write_access_and_wrong_mode() -> None:
    request = build_collection_request(
        provider="archive",
        mode="api",
        repository_id="archive-1",
        requested_capabilities=(Capability.REPOSITORY,),
        read_only=False,
    )
    issues = validate_collection_request(request)
    assert "collection_must_be_read_only" in issues
    assert "archive_provider_requires_archive_mode" in issues


def test_ready_collection_requires_complete_exact_snapshot() -> None:
    request = build_collection_request(
        provider=ProviderKind.GITLAB,
        mode=CollectionMode.API,
        repository_id="project-17",
        requested_capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.CI_RUNS),
    )
    result = build_collection_result(
        request=request,
        revision="abc123",
        collected_capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.CI_RUNS),
        cursor=PaginationCursor(complete=True),
    )
    assert result.state is CollectionState.READY
    assert validate_collection_result(request, result) == []


def test_incomplete_pagination_is_partial_and_disclosed() -> None:
    request = build_collection_request(
        provider="bitbucket",
        mode="api",
        repository_id="repo-1",
        requested_capabilities=(Capability.REPOSITORY, Capability.COMMITS),
    )
    result = build_collection_result(
        request=request,
        revision="def456",
        collected_capabilities=(Capability.REPOSITORY, Capability.COMMITS),
        cursor=PaginationCursor(token="next-page", page=2, complete=False),
    )
    assert result.state is CollectionState.PARTIAL
    assert result.limitation_reason
    assert validate_collection_result(request, result) == []


def test_rate_limit_never_appears_ready() -> None:
    request = build_collection_request(
        provider="azure repos",
        mode="api",
        repository_id="repo-2",
        requested_capabilities=(Capability.REPOSITORY, Capability.CI_RUNS),
    )
    result = build_collection_result(
        request=request,
        revision="expected",
        collected_capabilities=(Capability.REPOSITORY,),
        rate_limit=RateLimitWindow(remaining=0, reset_at="2026-07-17T14:00:00Z"),
    )
    assert result.state is CollectionState.RATE_LIMITED
    assert Capability.CI_RUNS in result.missing_capabilities
    assert result.limitation_reason


def test_auth_failure_and_provider_mismatch_are_visible() -> None:
    request = build_collection_request(
        provider="gitlab",
        mode="api",
        repository_id="project-3",
        requested_capabilities=(Capability.REPOSITORY,),
    )
    result = build_collection_result(
        request=request,
        revision="",
        collected_capabilities=(),
        auth_failed=True,
    )
    assert result.state is CollectionState.AUTH_FAILED
    mismatched = type(result)(
        state=result.state,
        provider=ProviderKind.GITHUB,
        repository_id=result.repository_id,
        revision=result.revision,
        collected_capabilities=result.collected_capabilities,
        missing_capabilities=result.missing_capabilities,
        cursor=result.cursor,
        rate_limit=result.rate_limit,
        limitation_reason=result.limitation_reason,
        collected_at=result.collected_at,
    )
    assert "collection_provider_mismatch" in validate_collection_result(request, mismatched)
