from pathlib import Path


def test_observed_regression_is_documented() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "EXPRESS_FINAL_TRUTH_REPAIR_V34.md").read_text(encoding="utf-8")

    assert "source-score adjustments now run before evidence-specific presentation" in text
    assert "terminal Express responses cannot show" in text
    assert "human review and client-delivery blocking remain mandatory" in text
