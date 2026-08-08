from __future__ import annotations

from pathlib import Path


ROUTE = Path("apps/web/app/api/nico/diagnostics/comprehensive-runtime/route.ts")


def test_comprehensive_readiness_preflight_is_bounded_and_fail_closed() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'export const maxDuration = 45' in source
    assert 'const HEALTH_WARMUP_BUDGET_MS = 28_000' in source
    assert 'const HEALTH_REQUEST_TIMEOUT_MS = 8_000' in source
    assert 'const HEALTH_RETRY_DELAY_MS = 2_000' in source
    assert 'const DIAGNOSTIC_TIMEOUT_MS = 14_000' in source
    assert 'const DIAGNOSTIC_RETRY_DELAY_MS = 1_000' in source
    assert 'signal: AbortSignal.timeout(timeoutMs)' in source
    assert 'new URL("/health", backend)' in source
    assert 'new URL("/diagnostics/comprehensive-runtime", backend)' in source
    assert '"assessment_backend_unreachable"' in source
    assert 'survives_container_replacement_verified: false' in source
    assert 'human_review_required: true' in source
    assert 'client_delivery_allowed: false' in source


def test_permanent_configuration_blocks_use_successful_transport() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    conflict = source[source.index("if (resolution.conflict)"):source.index("if (!resolution.backend)")]
    missing = source[source.index("if (!resolution.backend)"):source.index("// Railway can return")]

    assert '"assessment_backend_configuration_conflict"' in conflict
    assert '"assessment_backend_not_configured"' in missing
    assert ",\n    );" in conflict
    assert ",\n    );" in missing


def test_health_warmup_retries_immediate_edge_failures_inside_one_budget() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    warm = source[source.index("async function warmBackend"):source.index("function retryableDiagnostic")]

    assert "const deadline = startedAt + HEALTH_WARMUP_BUDGET_MS" in warm
    assert "while (Date.now() < deadline)" in warm
    assert "attempts += 1" in warm
    assert "Math.min(HEALTH_REQUEST_TIMEOUT_MS, remaining)" in warm
    assert "await wait(delay)" in warm
    assert "healthy: true" in warm
    assert "healthy: false" in warm


def test_authoritative_diagnostic_retries_only_transient_or_retryable_results_inside_one_budget() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    diagnostic = source[source.index("function retryableDiagnostic"):source.index("export async function GET")]

    assert 'runtimeStatus === "ready"' in diagnostic
    assert "observation.failureClass" in diagnostic
    assert "observation.httpStatus == null || TRANSIENT_STATUS.has(observation.httpStatus)" in diagnostic
    assert "observation.payload.retryable === true || detail.retryable === true" in diagnostic
    assert "const deadline = startedAt + DIAGNOSTIC_TIMEOUT_MS" in diagnostic
    assert "new URL(\"/diagnostics/comprehensive-runtime\", backend)" in diagnostic
    assert "if (!retryableDiagnostic(latest))" in diagnostic
    assert "Math.min(\n      DIAGNOSTIC_RETRY_DELAY_MS" in diagnostic
    assert "await wait(delay)" in diagnostic


def test_health_warmup_never_substitutes_for_authoritative_readiness() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    warmup_start = source.index("const warmup = await warmBackend")
    diagnostic_start = source.index("const diagnostic = await observeDiagnostic")
    success_start = source.index("if (\n    diagnostic.httpStatus")
    success_end = source.index("const reason = upstreamReason")
    success = source[success_start:success_end]

    assert warmup_start < diagnostic_start < success_start
    assert "diagnostic.payload" in success
    assert "warmup.payload" not in success
    assert "health_used_as_readiness_evidence: false" in source


def test_transient_failure_returns_one_semantic_block_without_browser_retry_multiplication() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    blocked = source[source.index("function blockedReadiness"):source.index("function upstreamReason")]
    terminal = source[source.index("const reason = upstreamReason"):]

    assert "retryable = false" in blocked
    assert "upstreamStatus: number | null = null" in blocked
    assert 'detail: {' in blocked
    assert 'request_id: requestId' in blocked
    assert 'browser_retry_authoritative: false' in blocked
    assert 'retry_requires_explicit_user_action: retryable' in blocked
    assert 'status: 200' in blocked
    assert '"Retry-After"' not in blocked
    assert 'diagnostic.httpStatus == null || TRANSIENT_STATUS.has(diagnostic.httpStatus)' in terminal
    assert "transient,\n    diagnostic.httpStatus" in terminal
    assert "transient ? 503 : 200" not in terminal


def test_successful_upstream_readiness_is_forwarded_without_reinterpretation() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    success = source[source.index("if (\n    diagnostic.httpStatus"):source.index("const reason = upstreamReason")]

    assert "Response.json(diagnostic.payload" in success
    assert "status: 200" in success
    assert "boundedHeaders(requestId, upstreamRequests)" in success
    assert "const upstreamRequests = warmup.attempts + diagnostic.attempts" in source


def test_total_upstream_budget_fits_external_production_probe() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert "28_000" in source
    assert "14_000" in source
    assert 28_000 + 14_000 < 45_000
