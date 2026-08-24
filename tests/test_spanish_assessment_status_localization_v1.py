from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "apps/web/app/assessment/assessmentStatus.ts"
PROOF = ROOT / "scripts/spanish_comprehensive_live_acceptance_v3.py"


def test_spanish_maturity_and_risk_bands_are_explicitly_localized() -> None:
    status = STATUS.read_text(encoding="utf-8")

    for expected in (
        'exceptional: "Excepcional"',
        'strong: "Sólido"',
        'moderate: "Moderado"',
        'weak: "Débil"',
        'critical: "Crítico"',
        'low: "Bajo"',
        'medium: "Medio"',
        'high: "Alto"',
    ):
        assert expected in status
    assert "const band = localizedBand(value, copy);" in status
    assert "if (band)" in status


def test_spanish_live_proof_rejects_english_terminal_maturity() -> None:
    proof = PROOF.read_text(encoding="utf-8")

    assert 'SPANISH_MATURITY_LABELS = {"Excepcional", "Sólido", "Moderado", "Débil", "Crítico"}' in proof
    assert 'FORBIDDEN_ENGLISH_MATURITY_LABELS = {"Exceptional", "Strong", "Moderate", "Weak", "Critical"}' in proof
    assert "assert maturity in SPANISH_MATURITY_LABELS" in proof
    assert "assert not any(label in score for label in FORBIDDEN_ENGLISH_MATURITY_LABELS)" in proof
