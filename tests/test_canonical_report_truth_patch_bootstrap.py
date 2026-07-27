from pathlib import Path


def test_canonical_report_truth_patcher_is_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts" / "apply_canonical_report_truth_patch.py").is_file()
