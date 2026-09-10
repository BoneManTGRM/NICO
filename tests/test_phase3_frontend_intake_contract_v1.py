from __future__ import annotations

from pathlib import Path


def test_phase3_frontend_reuses_existing_comprehensive_evidence_modules() -> None:
    source = Path("apps/web/app/assessment/strategicEvidence.ts").read_text(encoding="utf-8")
    assert source.count('moduleId: "') == 10
    assert 'moduleId: "stakeholder_context"' in source
    assert 'requiredFields: ["objectives", "constraints"]' in source
    assert 'fields: ["objectives", "constraints", "access_method", "primary_technical_contact", "authorized_scope"]' in source
    assert 'moduleId: "compliance_requirements"' in source
    assert 'requiredFields: ["requirements"]' in source
    assert 'fields: ["requirements", "authority_status"]' in source


def test_phase3_frontend_keeps_existing_functional_qa_and_platform_parity_sections() -> None:
    source = Path("apps/web/app/assessment/strategicEvidence.ts").read_text(encoding="utf-8")
    form = Path("apps/web/app/assessment/StrategicEvidenceForm.tsx").read_text(encoding="utf-8")
    assert 'moduleId: "functional_qa"' in source
    assert 'requiredFields: ["test_cases", "observed_results"]' in source
    assert 'moduleId: "platform_parity"' in source
    assert 'requiredFields: ["matrix"]' in source
    assert "evidenceFields(activeDefinition).map" in form


def test_phase3_mobile_intake_keeps_mandatory_client_context_available_without_full_editor() -> None:
    form = Path("apps/web/app/assessment/StrategicEvidenceForm.tsx").read_text(encoding="utf-8")
    assert 'data-mobile-client-engagement-context="true"' in form
    assert 'const MOBILE_CLIENT_ENGAGEMENT_FIELDS = ["access_method", "primary_technical_contact", "authorized_scope"]' in form
    assert "setEvidenceField(" in form
    assert '"stakeholder_context"' in form
    assert "field," in form


def test_phase3_workspace_mounts_mobile_client_context_instead_of_hiding_it() -> None:
    workspace = Path("apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
    assert workspace.count("<StrategicEvidenceForm") == 1
    assert "{compactMobile ? <section" not in workspace
    assert "Optional human evidence is added from the desktop workspace" not in workspace
    assert "La evidencia humana opcional se agrega desde la vista de escritorio" not in workspace


def test_no_run_retry_refreshes_the_exact_dom_snapshot_without_breaking_automatic_retries() -> None:
    bridge = Path(
        "apps/web/app/assessment/AssessmentIntakeDomSnapshotBridge.tsx"
    ).read_text(encoding="utf-8")
    workspace = Path(
        "apps/web/app/assessment/AssessmentWorkspace.tsx"
    ).read_text(encoding="utf-8")

    # Both user gestures that can create an intake bind a fresh native-control
    # snapshot before React disables/unmounts the compact evidence editor.
    assert workspace.count('data-assessment-intake-submit="true"') == 2
    primary_action = workspace.split('data-assessment-primary-action="true"', 1)[1].split(
        "</button>", 1
    )[0]
    no_run_retry = workspace.split("{preflightIssue ?", 1)[1].split(
        ': phase === "checking"', 1
    )[0]
    exact_run_retry = workspace.split("{runIssue ?", 1)[1].split(
        "{!runIssue && message", 1
    )[0]
    assert 'data-assessment-intake-submit="true"' in primary_action
    assert 'data-assessment-intake-submit="true"' in no_run_retry
    assert 'data-assessment-intake-submit="true"' not in exact_run_retry
    assert "function isIntakeSubmitAction" in bridge
    assert "[data-assessment-intake-submit='true']" in bridge
    assert "pendingSnapshot = captureIntakeDomSnapshot();" in bridge

    # The snapshot remains available to requestWithRetry's internal 5xx replays and
    # is consumed only when the intake is accepted.
    assert "const snapshot = pendingSnapshot || captureIntakeDomSnapshot();" in bridge
    assert "if (response.ok) pendingSnapshot = null;" in bridge
