from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "apps/web/app/assessment/AssessmentIntakeDomSnapshotBridge.tsx"
PAGE = ROOT / "apps/web/app/assessment/AssessmentPage.tsx"
FORM = ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"


def test_comprehensive_intake_dom_snapshot_bridge_is_mounted_and_bounded() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert 'import AssessmentIntakeDomSnapshotBridge from "./AssessmentIntakeDomSnapshotBridge";' in page
    assert "<AssessmentIntakeDomSnapshotBridge />" in page
    assert '"/assessment/comprehensive-intake"' in bridge
    assert '"/api/nico/assessment/comprehensive-intake"' in bridge
    assert 'data-assessment-primary-action="true"' in bridge
    assert 'document.addEventListener("click", captureBeforeReactSubmit, true)' in bridge
    assert "rewriteComprehensiveIntakeBody" in bridge
    assert "console." not in bridge
    assert "client_delivery_allowed" not in bridge
    assert "human_review_completed" not in bridge


def test_submit_snapshot_recovers_all_five_client_context_values() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    form = FORM.read_text(encoding="utf-8")

    for marker in (
        "Client name, optional",
        "Nombre del cliente, opcional",
        "Project name, optional",
        "Nombre del proyecto, opcional",
        "access_method",
        "primary_technical_contact",
        "authorized_scope",
    ):
        assert marker in bridge

    assert 'data-mobile-client-engagement-context="true"' in form
    assert "if (!richEditorEnabled && disabled) return null;" in form
    assert "payload.client_name = snapshot.clientName" in bridge
    assert "payload.project_name = snapshot.projectName" in bridge
    assert "payload.human_evidence = humanEvidence" in bridge
    assert "if (response.ok) pendingSnapshot = null" in bridge


def test_mobile_snapshot_overwrites_stale_state_instead_of_merging_false_values() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")

    # The actual touch-control snapshot is authoritative for these three optional fields.
    # A visibly cleared field must delete stale React-state evidence rather than silently
    # retaining an older value in the submitted intake payload.
    assert "if (values.length) evidence[field] = values" in bridge
    assert "else delete evidence[field]" in bridge

    # Scope identity and authorization are intentionally not rebuilt by this bridge.
    assert "customer_id" not in bridge
    assert "project_id" not in bridge
    assert "authorization_confirmed" not in bridge
