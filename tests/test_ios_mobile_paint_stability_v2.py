from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "apps/web/app/layout.tsx"
MOBILE_CSS = ROOT / "apps/web/styles/assessment-mobile-stability.css"
EVIDENCE_FORM = ROOT / "apps/web/app/assessment/StrategicEvidenceForm.tsx"
WEBKIT_PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v2.py"
SCORE_PROJECTION = ROOT / "nico/comprehensive_mobile_score_projection_v2.py"
PACKAGE = ROOT / "nico/__init__.py"


def test_mobile_stability_styles_load_after_existing_assessment_styles() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    terminal = source.index('import "../styles/assessment-terminal-mobile.css"')
    stability = source.index('import "../styles/assessment-mobile-stability.css"')
    assert terminal < stability


def test_phone_workspace_removes_known_ios_paint_pressure() -> None:
    source = MOBILE_CSS.read_text(encoding="utf-8")

    assert "@media (max-width: 760px)" in source
    assert 'main[data-workspace="assessment"] section#assessment' in source
    assert "overflow: visible !important" in source
    assert "max-height: none !important" in source
    assert "contain: none !important" in source
    assert "backdrop-filter: none !important" in source
    assert "box-shadow: none !important" in source
    assert ':not([data-mobile-evidence-boundary="true"])' in source
    assert 'section[data-mobile-evidence-boundary="true"]::after' in source
    assert 'details[class*="stageHistory"]' in source
    assert '[data-assessment-report-ready="true"] .results-grid' in source
    assert "content-visibility: auto" not in source


def test_touch_devices_do_not_mount_the_optional_evidence_editor() -> None:
    source = EVIDENCE_FORM.read_text(encoding="utf-8")

    assert "function useRichEvidenceEditor" in source
    assert '(min-width: 1025px) and (pointer: fine)' in source
    assert "const [enabled, setEnabled] = useState(false)" in source
    assert 'data-mobile-evidence-boundary="true"' in source
    assert 'data-evidence-editor-mounted="false"' in source
    assert 'data-mobile-evidence-note="true"' in source
    assert source.index("if (!richEditorEnabled)") < source.index("const activeDefinition")


def test_webkit_gate_requires_zero_allocated_evidence_controls() -> None:
    source = WEBKIT_PROOF.read_text(encoding="utf-8")

    assert 'VERSION = "nico.mobile_restart_live_acceptance.webkit.v3"' in source
    assert "playwright.webkit.launch" in source
    assert 'device_scale_factor", 3' in source
    assert 'is_mobile", True' in source
    assert 'has_touch", True' in source
    assert "_prove_intake_paint(browser, args)" in source
    assert "optional_evidence_editor_unmounted" in source
    assert "optional_evidence_controls_allocated" in source
    assert "interactive_control_count" in source
    assert "rich_editor_node_count" in source
    assert "authorization_reachable" in source
    assert "assessment_action_reachable" in source
    assert "ancestor_clipping_absent" in source
    assert "page_crash_absent" in source
    assert "recovery.run_proof(browser, args)" in source


def test_bounded_terminal_response_recovers_canonical_score_from_report_json() -> None:
    source = SCORE_PROJECTION.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")

    assert 'VERSION = "nico.comprehensive_mobile_score_projection.v3"' in source
    assert 'json_value.get("assessment")' in source
    assert "controller_module._report_outputs = _report_outputs" in source
    assert '"full_report_embedded": False' in source
    assert "install_scorecard_extraction_validation" in source
    assert '"wrapped_control_labels_supported": True' in source
    assert '"all_canonical_rows_and_scores_required": True' in source
    assert "from nico.comprehensive_mobile_score_projection_v2 import" in package
    assert package.rindex("install_comprehensive_mobile_score_projection_v2()") > package.index(
        "install_comprehensive_canonical_truth()"
    )
