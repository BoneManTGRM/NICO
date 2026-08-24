from pathlib import Path

FORM = Path("apps/web/app/assessment/StrategicEvidenceForm.tsx").read_text(encoding="utf-8")
RUN_CONTROLLER = Path("apps/web/app/assessment/useAssessmentRun.ts").read_text(encoding="utf-8")


def test_mobile_evidence_intake_unmounts_while_assessment_is_active() -> None:
    assert "if (!richEditorEnabled && disabled) return null;" in FORM
    assert "if (!richEditorEnabled)" in FORM
    assert 'data-evidence-editor-mounted="false"' in FORM
    assert 'data-mobile-client-engagement-context="true"' in FORM


def test_compact_mobile_does_not_present_optional_modules_as_zero_of_ten() -> None:
    compact = FORM.split("if (!richEditorEnabled) {", 1)[1].split("const activeDefinition", 1)[0]

    assert "{addedCount}/{STRATEGIC_EVIDENCE_DEFINITIONS.length}" not in compact
    assert "{copy.mobileOptional}" in compact
    assert "{copy.mobileContextLabel}" in compact
    assert 'mobileOptional: "Opcional"' in FORM
    assert 'mobileContextLabel: "Contexto del cliente"' in FORM

    # Desktop/full evidence mode retains the real 10-module progress indicator.
    assert "<strong>{addedCount}/{STRATEGIC_EVIDENCE_DEFINITIONS.length}</strong>" in FORM


def test_workspace_disabled_contract_tracks_active_assessment_phases() -> None:
    assert 'phase === "checking" || phase === "starting" || phase === "running"' in RUN_CONTROLLER
