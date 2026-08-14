from pathlib import Path


def test_phase3_final_acceptance_note_requires_exact_main_proof() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "phase3-final-acceptance-note.md").read_text(encoding="utf-8")
    assert "Unified Production Acceptance" in text
    assert "fresh Comprehensive report" in text
    assert "does not itself claim completion" in text
