from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
CONTROLLER = ROOT / "apps" / "web" / "app" / "assessment" / "useAssessmentRun.ts"
COPY = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentCopy.ts"
TYPES = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentTypes.ts"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "engagementWorkspace.module.css"
INLINE_STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "assessment-inline-readiness.css"


def test_workspace_uses_semantic_engagement_identity() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert 'data-workspace="assessment"' in source
    assert 'data-engagement-type="comprehensive"' in source
    assert 'data-canonical-assessment="strategic"' in source
    assert "data-assessment-service-count" not in source
    assert 'data-assessment-primary-action="true"' in source
    assert 'data-assessment-authorization="true"' in source


def test_readiness_failure_is_one_authoritative_safe_notice() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    copy = COPY.read_text(encoding="utf-8")

    assert "const preflightIssue = issue && !issue.runCreated ? issue : null" in workspace
    assert "const runIssue = issue && issue.runCreated ? issue : null" in workspace
    assert 'data-assessment-no-run-issue="true"' in workspace
    assert 'role="alert"' in workspace
    assert "issueRef.current?.focus()" in workspace
    assert 'preflightIssue.kind === "run_failed"' in workspace
    assert "{showStatePanel ? <section" in workspace
    assert 'setPhase(normalized.kind === "run_failed" ? "failed" : "unavailable")' in controller
    assert 'setPhase("checking")' in controller
    assert 'kind: "configuration_blocked"' in controller
    assert "No assessment was created and no repository processing began" in copy
    assert "SQLite" not in copy
    assert "persistent volume" not in copy.lower()


def test_retry_resumes_exact_run_instead_of_creating_duplicate() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")

    assert "async function retry()" in source
    assert 'const runId = String(result?.run_id || "").trim()' in source
    assert '`/assessment/comprehensive-run/${encodeURIComponent(runId)}`' in source
    assert "await continueRun(recovered, currentScope(), token)" in source
    retry_body = source.split("async function retry()", 1)[1]
    retry_body = retry_body.split("return {", 1)[0]
    assert '"/assessment/comprehensive-intake"' not in retry_body


def test_phases_distinguish_readiness_from_run_failure() -> None:
    source = TYPES.read_text(encoding="utf-8")

    assert '"checking"' in source
    assert '"unavailable"' in source
    assert '"failed"' in source


def test_mobile_design_keeps_errors_compact_and_actions_reachable() -> None:
    source = STYLES.read_text(encoding="utf-8")
    inline = INLINE_STYLES.read_text(encoding="utf-8")

    assert "@media (max-width: 430px)" in source
    assert ".issueContent" in source
    assert ".retryButton" in source
    assert "min-height: 44px" in source
    assert ".lifecycle" in source
    assert "grid-template-columns: 1fr" in source
    assert '[data-assessment-no-run-issue="true"]' in inline
    assert "box-shadow: none" in inline
