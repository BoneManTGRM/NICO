from __future__ import annotations

from pathlib import Path

from nico.decision_grade_human_evidence_v1 import MODULE_DEFINITIONS


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.ts"
FORM = ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
CONTROLLER = ROOT / "apps" / "web" / "app" / "assessment" / "useAssessmentRun.ts"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def test_workspace_exposes_exact_canonical_human_evidence_schema() -> None:
    source = MODEL.read_text(encoding="utf-8")

    for definition in MODULE_DEFINITIONS:
        assert f'moduleId: "{definition["module_id"]}"' in source
        exact_fields = ", ".join(f'"{field}"' for field in definition["required_fields"])
        assert f"requiredFields: [{exact_fields}]" in source


def test_intake_is_bilingual_and_fail_closed_for_missing_context() -> None:
    source = FORM.read_text(encoding="utf-8")

    assert "OPTIONAL STRATEGIC EVIDENCE" in source
    assert "EVIDENCIA ESTRATÉGICA OPCIONAL" in source
    assert "Missing modules remain Not assessed" in source
    assert "nunca se infieren del repositorio" in source
    assert "moduleCompleteness" in source
    assert "exclusion_rationale" in source
    assert "evidenceLines(event.target.value)" in source


def test_controller_sends_compacted_evidence_on_same_canonical_run() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "human_evidence: compactStrategicHumanEvidence(humanEvidence)" in controller
    assert 'assessment_depth: "strategic"' in controller
    assert "report_language: locale" in controller
    assert "<StrategicEvidenceForm" in workspace
    assert "onChange={setHumanEvidence}" in workspace
    assert "disabled={running}" in workspace
