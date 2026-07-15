from pathlib import Path


def test_final_v12_sanitization_documentation_preserves_truth_boundary() -> None:
    text = Path("docs/FINAL_V12_OUTPUT_SANITIZATION.md").read_text(encoding="utf-8")
    assert "rendered as `unavailable`" in text
    assert "Historical workflow reliability findings remain visible" in text
    assert "do not alter scores" in text
    assert "no-write boundary" in text
