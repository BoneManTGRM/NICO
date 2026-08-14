from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps/web/app/assessment"
HOOK = (ASSESSMENT / "useAssessmentRun.ts").read_text(encoding="utf-8")
IDENTITY = (ASSESSMENT / "assessmentRunIdentity.ts").read_text(encoding="utf-8")
PERSISTENCE = (ASSESSMENT / "assessmentRunPersistence.ts").read_text(encoding="utf-8")


def test_recovery_preserves_exact_identity_from_url_or_nested_record() -> None:
    assert "export function preserveRunIdentity" in IDENTITY
    assert "value.run_id || identity.run_id || fallback.runId" in IDENTITY
    assert "value.commit_sha" in IDENTITY
    assert "value.repository_snapshot?.commit_sha" in IDENTITY
    assert "record: {" in IDENTITY
    assert "identity: {" in IDENTITY


def test_every_recovery_path_normalizes_before_react_state() -> None:
    assert "const recovered = preserveRunIdentity(recoveredResponse" in HOOK
    assert "current = preserveRunIdentity(continued" in HOOK
    assert "return preserveRunIdentity(recovered" in HOOK
    assert "let current = preserveRunIdentity(initial" in HOOK
    assert "publishResult(recovered);" in HOOK


def test_active_reload_uses_persisted_run_id_as_authoritative_fallback() -> None:
    resume = HOOK.split("async function resumePersistedRun", 1)[1].split("async function run()", 1)[0]
    assert "runId: persisted.runId" in resume
    assert "publishResult(recovered);" in resume
    assert resume.index("const recovered = preserveRunIdentity") < resume.index("publishResult(recovered);")


def test_continuation_never_replaces_exact_identity_with_bounded_projection_gaps() -> None:
    continuation = HOOK.split("async function continueRun", 1)[1].split("function applyIssue", 1)[0]
    assert "runId," in continuation
    assert "repository: current.repository" in continuation
    assert "customerId: current.customer_id || scope.customerId" in continuation
    assert "projectId: current.project_id || scope.projectId" in continuation


def test_resume_does_not_publish_a_synthetic_five_percent_unknown_stage() -> None:
    resume = HOOK.split("async function resumePersistedRun", 1)[1].split("async function run()", 1)[0]
    assert 'status: "running"' not in resume
    assert "setResult({" not in resume
    assert "publishResult(recovered);" in resume
    assert "preferMonotonicVisibleResult" in HOOK
    assert "incomingProgress < previousProgress" in HOOK
    assert "previousStage" in HOOK and "!incomingStage" in HOOK


def test_page_resume_cannot_cancel_the_existing_exact_run_loop() -> None:
    restore = HOOK.split("const restoreAfterPageResume", 1)[1].split(
        'window.addEventListener("pageshow"', 1
    )[0]
    resume = HOOK.split("async function resumePersistedRun", 1)[1].split("async function run()", 1)[0]
    continuation = HOOK.split("async function continueRun", 1)[1].split("function applyIssue", 1)[0]

    assert 'window.addEventListener("pageshow", restoreAfterPageResume)' in HOOK
    assert 'window.addEventListener("online", restoreAfterPageResume)' in HOOK
    assert "const persisted = readPersistedRun();" in restore
    assert "activeContinuationRunId.current === persisted.runId" in restore
    assert "visibleRunId && visibleRunId !== persisted.runId" in restore
    assert "activeContinuationRunId.current === persisted.runId" in resume
    assert "activeContinuationRunId.current = continuationRunId" in continuation
    assert 'activeContinuationRunId.current = ""' in continuation


def test_exact_url_run_uses_per_run_storage_without_cross_run_metadata() -> None:
    assert 'EXACT_RUN_STORAGE_PREFIX = "nico.comprehensive.exact-run.v1."' in PERSISTENCE
    assert "readExactStoredRun(urlRunId)" in PERSISTENCE
    assert "active?.runId === runId ? active : null" in PERSISTENCE
    assert "Never borrow repository, client" in PERSISTENCE
    assert 'repository: ""' in PERSISTENCE
    assert 'customerId: "default_customer"' in PERSISTENCE
    assert "window.localStorage.setItem(exactRunStorageKey(value.runId), encoded)" in PERSISTENCE
