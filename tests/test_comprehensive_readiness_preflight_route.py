from __future__ import annotations

from pathlib import Path


ROUTE = Path("apps/web/app/api/nico/diagnostics/comprehensive-runtime/route.ts")


def test_comprehensive_readiness_preflight_is_bounded_and_fail_closed() -> None:
    source = ROUTE.read_text(encoding="utf-8")

    assert 'export const maxDuration = 45' in source
    assert 'const UPSTREAM_TIMEOUT_MS = 15_000' in source
    assert 'const RETRY_DELAYS_MS = [0, 1_500]' in source
    assert 'signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)' in source
    assert 'new URL("/diagnostics/comprehensive-runtime", resolution.backend)' in source
    assert '"assessment_backend_unreachable"' in source
    assert 'survives_container_replacement_verified: false' in source
    assert 'human_review_required: true' in source
    assert 'client_delivery_allowed: false' in source


def test_preflight_returns_blocked_readiness_over_successful_transport() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    blocked = source[source.index("function blockedReadiness"):source.index("function upstreamReason")]

    assert 'status: "blocked"' in blocked
    assert 'status: 200' in blocked
    assert 'retryable: true' in blocked
    assert 'status: "bounded_failure"' in blocked
    assert "avoids multiplying" in blocked
