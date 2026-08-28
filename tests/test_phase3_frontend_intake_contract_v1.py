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
    assert 'const CLIENT_ENGAGEMENT_FIELDS = ["access_method", "primary_technical_contact", "authorized_scope"]' in form
    assert "setEvidenceField(" in form
    assert '"stakeholder_context"' in form
    assert "field," in form


def test_phase3_workspace_mounts_mobile_client_context_instead_of_hiding_it() -> None:
    workspace = Path("apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
    assert workspace.count("<StrategicEvidenceForm") == 1
    assert "{compactMobile ? <section" not in workspace
    assert "Optional human evidence is added from the desktop workspace" not in workspace
    assert "La evidencia humana opcional se agrega desde la vista de escritorio" not in workspace
