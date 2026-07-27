from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")
HYDRATION = (ROOT / "apps/web/app/assessment/AssessmentHydrationContract.tsx").read_text(encoding="utf-8")


def test_mobile_proof_waits_for_the_canonical_hydration_marker() -> None:
    assert "workspace.dataset.assessmentHydrated" in HYDRATION
    assert "HYDRATED_WORKSPACE_SELECTOR" in PROOF
    assert "[data-assessment-hydrated=\"true\"]" in PROOF
    assert "[data-assessment-client-mode=\"compact-mobile\"]" in PROOF
    assert "def _wait_for_hydration" in PROOF
    assert "self._wait_for_hydration(kwargs.get(\"timeout\"))" in PROOF
    assert 'result["hydration_wait_verified"] = True' in PROOF


def test_dispatch_diagnostics_expose_actionability_and_compact_dom_state() -> None:
    for field in ("connected", "disabled", "width", "height", "label"):
        assert field in PROOF
    assert "Assessment start action never became dispatchable" in PROOF
    assert "compact_terminal_count" in PROOF
    assert "heavy_report_mounted_count" in PROOF
    assert "stage_history_count" in PROOF
    assert "scorecard_grid_count" in PROOF
    assert 'result["compact_mobile_dom_verified"] = True' in PROOF
