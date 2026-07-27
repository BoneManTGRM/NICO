from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts" / "mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")


def test_terminal_metrics_arrow_function_has_balanced_closure() -> None:
    block = PROOF.split("def _read_terminal_metrics", 1)[1].split("def _validate_terminal_metrics", 1)[0]
    assert '"""() => ({' in block
    assert '})"""' in block
    assert '}))"""' not in block
