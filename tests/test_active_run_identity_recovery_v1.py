from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = (ROOT / "apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")


def test_recovery_preserves_exact_identity_from_url_or_nested_record() -> None:
    assert "function preserveRunIdentity(value: Result, fallback: RunIdentityFallback): Result" in HOOK
    assert "value.run_id || identity.run_id || fallback.runId" in HOOK
    assert "value.commit_sha" in HOOK
    assert "value.repository_snapshot?.commit_sha" in HOOK
    assert "record: {" in HOOK
    assert "identity: {" in HOOK


def test_every_recovery_path_normalizes_before_react_state() -> None:
    assert "const recovered = preserveRunIdentity(recoveredResponse" in HOOK
    assert "current = preserveRunIdentity(continued" in HOOK
    assert "return preserveRunIdentity(recovered" in HOOK
    assert "let current = preserveRunIdentity(initial" in HOOK


def test_active_reload_uses_persisted_run_id_as_authoritative_fallback() -> None:
    resume = HOOK.split("async function resumePersistedRun", 1)[1].split("async function run()", 1)[0]
    assert "runId: persisted.runId" in resume
    assert "setResult(recovered);" in resume
    assert resume.index("const recovered = preserveRunIdentity") < resume.index("setResult(recovered);")


def test_continuation_never_replaces_exact_identity_with_bounded_projection_gaps() -> None:
    continuation = HOOK.split("async function continueRun", 1)[1].split("function applyIssue", 1)[0]
    assert "runId," in continuation
    assert "repository: current.repository" in continuation
    assert "customerId: current.customer_id || scope.customerId" in continuation
    assert "projectId: current.project_id || scope.projectId" in continuation
