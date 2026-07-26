from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "apps" / "web" / "app" / "assessment" / "useAssessmentRun.ts"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
EVIDENCE_FORM = ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
EVIDENCE_STYLE = ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.module.css"


def test_preflight_block_is_one_typed_unavailable_state_without_a_false_run() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "export type AssessmentRunIssue" in controller
    assert 'kind: "configuration_blocked"' in controller
    assert '"comprehensive_sqlite_persistent_volume_required"' in controller
    assert "await verifyRuntimePersistence()" in controller
    assert controller.index("await verifyRuntimePersistence()") < controller.index('"/assessment/comprehensive-intake"')
    assert 'setPhase(normalized.kind === "run_failed" ? "failed" : "unavailable")' in controller
    assert 'data-workspace="assessment"' in workspace
    assert 'data-engagement-type="comprehensive"' in workspace
    assert 'data-assessment-primary-action="true"' in workspace
    assert 'issue.runCreated ? copy.exactRunPreserved : copy.noRunCreated' in workspace
    assert 'role="alert"' in workspace


def test_human_evidence_intake_uses_one_focused_editor_on_mobile() -> None:
    form = EVIDENCE_FORM.read_text(encoding="utf-8")
    style = EVIDENCE_STYLE.read_text(encoding="utf-8")

    assert "Choose an evidence module" in form
    assert "Add evidence" in form
    assert "Remove from intake" in form
    assert "moduleList" in form
    assert "moduleEditor" in form
    assert "mobileChooser" in form
    assert "evidenceLines(event.target.value)" in form
    assert ".evidenceWorkspace" in style
    assert ".moduleList" in style
    assert ".moduleEditor" in style
    assert "@media (max-width: 720px)" in style
    assert ".moduleList {\n    display: none;" in style
