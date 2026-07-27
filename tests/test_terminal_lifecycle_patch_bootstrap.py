from pathlib import Path


def test_terminal_lifecycle_patcher_is_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts" / "apply_terminal_lifecycle_patch.py").is_file()
