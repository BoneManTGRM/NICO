from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_mobile_proof_reads_the_actual_compact_identity_dom() -> None:
    assert "querySelectorAll('article, details p')" in PROOF
    assert "const identityRows" in PROOF
    assert "const row = identityRows.find" in PROOF
    assert "row?.querySelector('code')" in PROOF


def test_mobile_proof_accepts_current_internal_review_vocabulary() -> None:
    assert '"Internal review required"' in PROOF
    assert '"Revisión interna requerida"' in PROOF
    assert "'Internal review', 'Expert review'" in PROOF
    assert "'Revisión interna', 'Revisión experta'" in PROOF


def test_proof_does_not_fall_back_to_url_identity_as_ui_evidence() -> None:
    wait_body = PROOF.split("def _wait_for_same_run_ui", 1)[1].split("def _wait_for_terminal", 1)[0]
    assert 'last.get("run_id") == run_id' in wait_body
    assert 'page_url' not in wait_body
