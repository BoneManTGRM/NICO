from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = (
    ROOT / "apps" / "web" / "app" / "ComprehensiveStuckRunRecovery.tsx"
).read_text(encoding="utf-8")
REQUESTS = (
    ROOT / "apps" / "web" / "app" / "assessment" / "assessmentRunRequests.ts"
).read_text(encoding="utf-8")


def _milliseconds(source: str, name: str) -> int:
    match = re.search(rf"const {re.escape(name)} = ([0-9_]+);", source)
    assert match is not None, f"missing timeout constant: {name}"
    return int(match.group(1).replace("_", ""))


def test_global_recovery_timeout_never_preempts_canonical_request_owner() -> None:
    assert _milliseconds(RECOVERY, "DIAGNOSTIC_REQUEST_TIMEOUT_MS") > _milliseconds(
        REQUESTS,
        "READINESS_CLIENT_TIMEOUT_MS",
    )
    assert _milliseconds(RECOVERY, "RUN_STATUS_REQUEST_TIMEOUT_MS") > _milliseconds(
        REQUESTS,
        "RUN_STATUS_CLIENT_TIMEOUT_MS",
    )
    assert _milliseconds(RECOVERY, "LONG_REQUEST_TIMEOUT_MS") > _milliseconds(
        REQUESTS,
        "RUN_CONTINUE_CLIENT_TIMEOUT_MS",
    )


def test_exact_run_get_uses_its_own_outer_fallback_instead_of_generic_get_timeout() -> None:
    assert 'const RUN_STATUS_PATH = /^\\/api\\/nico\\/assessment\\/comprehensive-run\\/[^/?#]+$/;' in RECOVERY
    assert 'if (method === "GET" && RUN_STATUS_PATH.test(path))' in RECOVERY
    assert "return RUN_STATUS_REQUEST_TIMEOUT_MS;" in RECOVERY
    assert "SHORT_REQUEST_TIMEOUT_MS" not in RECOVERY


def test_canonical_run_issue_suppresses_duplicate_fixed_recovery_panel() -> None:
    assert "const CANONICAL_RUN_ISSUE_SELECTOR =" in RECOVERY
    assert '[data-assessment-run-state="true"] [role="alert"]' in RECOVERY
    assert "new MutationObserver(suppressWhenCanonicalIssueVisible)" in RECOVERY
    assert "if (canonicalRunIssueVisible()) hideFallback();" in RECOVERY
    assert "if (!visible || canonicalRunIssueVisible()) return null;" in RECOVERY
    assert "issueObserver.disconnect();" in RECOVERY


def test_exact_run_identity_and_fail_closed_approval_boundaries_are_unchanged() -> None:
    assert 'const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1"' in RECOVERY
    assert 'url.searchParams.set(ACTIVE_RUN_QUERY_KEY, exactRunId)' in RECOVERY
    assert 'data-clear-stuck-comprehensive-run="true"' in RECOVERY
    assert "human_review" not in RECOVERY
    assert "client_delivery" not in RECOVERY
    assert "approved_delivery" not in RECOVERY
