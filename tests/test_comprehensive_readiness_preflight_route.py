from __future__ import annotations

from pathlib import Path


ROUTE = Path("apps/web/app/api/nico/diagnostics/comprehensive-runtime/route.ts")


def test_comprehensive_readiness_preflight_is_bounded_and_fail_closed() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'export const maxDuration = 20' in source
    assert 'const UPSTREAM_TIMEOUT_MS = 12_000' in source
    assert 'const RETRY_DELAYS_MS = [0]' in source
    assert 'signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)' in source
    assert 'new URL("/diagnostics/comprehensive-runtime", resolution.backend)' in source
    assert '"assessment_backend_unreachable"' in source
    assert 'survives_container_replacement_verified: false' in source
    assert 'human_review_required: true' in source
    assert 'client_delivery_allowed: false' in source


def test_permanent_configuration_blocks_use_successful_transport() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    conflict = source[source.index("if (resolution.conflict)"):source.index("if (!resolution.backend)")]
    missing = source[source.index("if (!resolution.backend)"):source.index('const upstream = new URL')]

    assert '"assessment_backend_configuration_conflict"' in conflict
    assert '"assessment_backend_not_configured"' in missing
    assert ",\n    );" in conflict
    assert ",\n    );" in missing


def test_transient_readiness_failures_delegate_retry_to_browser() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    blocked = source[source.index("function blockedReadiness"):source.index("function upstreamReason")]
    transient = source[source.index("if (TRANSIENT_STATUS.has(response.status))"):source.index("return blockedReadiness(\n        requestId,\n        lastFailure,\n        \"The Comprehensive assessment service is not ready yet.")]
    unreachable = source[source.rindex('return blockedReadiness(\n    requestId,\n    "assessment_backend_unreachable"'):]

    assert 'transportStatus = 200' in blocked
    assert 'const retryable = TRANSIENT_STATUS.has(transportStatus)' in blocked
    assert 'detail: {' in blocked
    assert 'request_id: requestId' in blocked
    assert 'browser_retry_authoritative: retryable' in blocked
    assert '"Retry-After": "2"' in blocked
    assert '"The Comprehensive assessment service is temporarily busy and will be checked again."' in transient
    assert ',\n          503,\n        );' in transient
    assert ',\n    503,\n  );' in unreachable


def test_successful_upstream_readiness_is_forwarded_without_reinterpretation() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    success = source[source.index("if (response.ok && Object.keys(payload).length)"):source.index("lastFailure = Object.keys(payload).length")]

    assert "Response.json(payload" in success
    assert "status: 200" in success
    assert "boundedHeaders(requestId, attempt + 1)" in success
