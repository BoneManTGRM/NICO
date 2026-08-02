from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps/web/app/ComprehensiveStuckRunRecovery.tsx"
LAYOUT = ROOT / "apps/web/app/layout.tsx"


def test_guard_bounds_comprehensive_lifecycle_requests() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const SHORT_REQUEST_TIMEOUT_MS = 45_000" in source
    assert "const LONG_REQUEST_TIMEOUT_MS = 300_000" in source
    assert "const controller = new AbortController()" in source
    assert "controller.abort" in source
    assert "nico:comprehensive-request-timeout" in source
    assert "/diagnostics/comprehensive-runtime" in source
    assert "comprehensive-intake" in source
    assert "comprehensive-run" in source


def test_guard_expires_stale_browser_run_identity() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "const ACTIVE_RUN_MAX_AGE_MS = 2 * 60 * 60_000" in source
    assert "Date.now() - stored.startedAt > ACTIVE_RUN_MAX_AGE_MS" in source
    assert 'window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY)' in source
    assert 'url.searchParams.delete(ACTIVE_RUN_QUERY_KEY)' in source


def test_guard_exposes_mobile_safe_recovery_controls() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'data-comprehensive-stuck-run-recovery="true"' in source
    assert 'data-clear-stuck-comprehensive-run="true"' in source
    assert "Retry saved run" in source
    assert "Clear stuck run and start new" in source
    assert "Keep waiting" in source
    assert "env(safe-area-inset-bottom)" in source


def test_guard_is_mounted_before_assessment_transport_bridges() -> None:
    source = LAYOUT.read_text(encoding="utf-8")
    assert 'import ComprehensiveStuckRunRecovery from "./ComprehensiveStuckRunRecovery"' in source
    assert "<ComprehensiveStuckRunRecovery />" in source
    assert source.index("<ComprehensiveStuckRunRecovery />") < source.index("<AssessmentApiTransportBridge />")
