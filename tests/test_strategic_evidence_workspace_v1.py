from __future__ import annotations

from pathlib import Path

from nico.decision_grade_human_evidence_v1 import MODULE_DEFINITIONS


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.ts"
FORM = ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.module.css"
CONTROLLER = ROOT / "apps" / "web" / "app" / "assessment" / "useAssessmentRun.ts"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def test_workspace_exposes_exact_canonical_human_evidence_schema() -> None:
    source = MODEL.read_text(encoding="utf-8")

    for definition in MODULE_DEFINITIONS:
        assert f'moduleId: "{definition["module_id"]}"' in source
        exact_fields = ", ".join(f'"{field}"' for field in definition["required_fields"])
        assert f"requiredFields: [{exact_fields}]" in source


def test_intake_is_bilingual_fail_closed_and_uses_one_focused_editor() -> None:
    source = FORM.read_text(encoding="utf-8")

    assert "OPTIONAL HUMAN EVIDENCE" in source
    assert "EVIDENCIA HUMANA OPCIONAL" in source
    assert "Missing modules remain Not assessed and are never inferred from repository code" in source
    assert "Los módulos faltantes permanecen como No evaluados y nunca se infieren del repositorio" in source
    assert "moduleCompleteness" in source
    assert "exclusion_rationale" in source
    assert "evidenceLines(event.target.value)" in source
    assert "moduleList" in source
    assert "moduleEditor" in source
    assert "mobileChooser" in source
    assert "Add evidence" in source
    assert "Remove from intake" in source
    assert "Include this module" not in source
    assert "summary-box" not in source
    assert "<details className={styles.strategicEvidence}>" not in source


def test_intake_updates_each_module_from_latest_parent_state() -> None:
    source = FORM.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")

    assert "onChange((currentValue) =>" in source
    assert "next(currentModule)" in source
    assert "const updated = {...currentValue}" in source
    assert "setModule(moduleId, (current) =>" in source
    assert "{...current, observed_at}" in source
    assert "{...current, source_reference}" in source
    assert "onInput={(event) =>" in source
    assert "const observed_at = event.currentTarget.value" in source
    assert "Dispatch<SetStateAction<StrategicHumanEvidenceInput>>" in source
    assert "Dispatch<SetStateAction<StrategicHumanEvidenceInput>>" in controller


def test_intake_has_compact_mobile_controls() -> None:
    source = STYLES.read_text(encoding="utf-8")

    assert "@media (max-width: 720px)" in source
    assert ".mobileChooser" in source
    assert ".moduleList {\n    display: none;" in source
    assert ".primaryAction" in source
    assert "min-height: 46px" in source
    assert ".metadataGrid" in source
    assert ".requiredEvidence" in source
    assert "grid-template-columns: minmax(0, 1fr)" in source


def test_controller_sends_compacted_evidence_on_same_canonical_run() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "human_evidence: compactStrategicHumanEvidence(humanEvidence)" in controller
    assert 'assessment_depth: "strategic"' in controller
    assert "report_language: reportLanguageForRequest(locale)" in controller
    assert "<StrategicEvidenceForm" in workspace
    assert "onChange={setHumanEvidence}" in workspace
    assert "disabled={running}" in workspace
