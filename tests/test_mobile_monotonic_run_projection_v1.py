from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
IDENTITY = (ASSESSMENT / "assessmentRunIdentity.ts").read_text(encoding="utf-8")
HOOK = (ASSESSMENT / "useAssessmentRun.ts").read_text(encoding="utf-8")
EVIDENCE = (ASSESSMENT / "assessmentEvidence.ts").read_text(encoding="utf-8")


def _function_body(source: str, name: str, next_name: str) -> str:
    return source.split(f"function {name}", 1)[1].split(f"function {next_name}", 1)[0]


def test_same_run_sparse_projection_cannot_regress_progress_or_stage() -> None:
    assert "const RUN_SNAPSHOT_CACHE_LIMIT = 4" in IDENTITY
    assert "const runSnapshots = new Map<string, Result>()" in IDENTITY
    assert "sameRunIdentity(incoming, previous)" in IDENTITY
    assert "Math.max(previousProgress, incomingProgress)" in IDENTITY
    assert '"unknown_stage"' in IDENTITY
    assert "currentStageFor(incoming) || currentStageFor(previous)" in IDENTITY
    assert "mergeStageResults(" in IDENTITY
    assert "runSnapshots.get(runIdFor(incoming)) || null" in IDENTITY


def test_cross_run_identity_remains_a_hard_partition() -> None:
    reconciliation = _function_body(
        IDENTITY,
        "reconcileSameRunSnapshot",
        "continuitySnapshot",
    )
    assert "if (!previous || !sameRunIdentity(incoming, previous))" in reconciliation
    assert "return incoming;" in reconciliation


def test_continuity_cache_is_bounded_and_excludes_large_or_authorizing_state() -> None:
    snapshot = _function_body(IDENTITY, "continuitySnapshot", "cacheRunSnapshot")
    assert "stageContinuity(stage)" in snapshot
    assert "reportContinuity(value.reports)" in snapshot
    assert "assessmentContinuity(value.assessment)" in snapshot
    assert "pdf_base64" not in snapshot
    assert "markdown:" not in snapshot
    assert "html:" not in snapshot
    assert "json:" not in snapshot
    assert "human_review_completed" not in snapshot
    assert "client_delivery_allowed" not in snapshot
    assert "review_decision" not in snapshot
    assert "accepted_edition" not in snapshot
    assert "approved_delivery_package" not in snapshot


def test_all_live_and_recovery_responses_pass_through_identity_reconciliation() -> None:
    assert "let current = preserveRunIdentity(initial" in HOOK
    assert "current = preserveRunIdentity(continued" in HOOK
    assert "return preserveRunIdentity(recovered" in HOOK
    assert "const recovered = preserveRunIdentity(recoveredResponse" in HOOK


def test_five_percent_is_only_a_last_resort_without_a_retained_same_run_snapshot() -> None:
    assert "running\n      ? 5" in EVIDENCE
    assert "Preserve exact identity and monotonic presentation state" in IDENTITY
    assert "scanner evidence, report bodies, PDF bytes" in IDENTITY
    assert "human decisions, approval state" in IDENTITY
