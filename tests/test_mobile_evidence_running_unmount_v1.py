from pathlib import Path

FORM = Path("apps/web/app/assessment/StrategicEvidenceForm.tsx").read_text(encoding="utf-8")
RUN_CONTROLLER = Path("apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")


def test_mobile_evidence_intake_unmounts_while_assessment_is_active() -> None:
    assert "if (!richEditorEnabled && disabled) return null;" in FORM
    assert "if (!richEditorEnabled)" in FORM
    assert 'data-evidence-editor-mounted="false"' in FORM
    assert 'data-mobile-client-engagement-context="true"' in FORM


def test_workspace_disabled_contract_tracks_active_assessment_phases() -> None:
    assert 'phase === "checking" || phase === "starting" || phase === "running"' in RUN_CONTROLLER
