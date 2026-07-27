from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")
HYDRATION = (ROOT / "apps/web/app/assessment/AssessmentHydrationContract.tsx").read_text(encoding="utf-8")


def test_mobile_proof_waits_for_the_canonical_hydration_marker() -> None:
    assert "workspace.dataset.assessmentHydrated" in HYDRATION
    assert "dataset.assessmentHydrated === 'true'" in PROOF
    assert "def _wait_for_hydration" in PROOF
    assert "self._wait_for_hydration(timeout_ms)" in PROOF


def test_dispatch_diagnostics_expose_lost_form_state() -> None:
    assert "authorization_checked" in PROOF
    assert "repository_value" in PROOF
    assert "hydrated" in PROOF
    assert 'result["client_hydration_wait_verified"] = True' in PROOF
