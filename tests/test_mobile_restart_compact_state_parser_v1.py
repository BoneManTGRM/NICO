from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_mobile_proof_reads_compact_identity_rows() -> None:
    assert "querySelectorAll('article, details p')" in PROOF
    assert "const headerRunId" in PROOF
    assert "|| headerRunId" in PROOF


def test_mobile_proof_accepts_current_internal_review_vocabulary() -> None:
    assert '"Internal review required"' in PROOF
    assert '"Revisión interna requerida"' in PROOF
    assert "'Internal review'" in PROOF
    assert "'Revisión interna'" in PROOF


def test_mobile_proof_keeps_legacy_terminal_compatibility() -> None:
    assert '"Expert review required"' in PROOF
    assert '"Se requiere revisión experta"' in PROOF
