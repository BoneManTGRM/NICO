from pathlib import Path


def test_final_v12_output_verification_criteria_preserve_client_truth() -> None:
    text = Path("docs/FINAL_V12_OUTPUT_SANITIZATION_VERIFICATION.md").read_text(encoding="utf-8")
    assert "must contain no client-visible" in text
    assert "preserve the original maturity score" in text
    assert "historical reliability findings" in text
    assert "report-only no-write boundary" in text
