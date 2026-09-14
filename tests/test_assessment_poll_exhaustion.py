"""Exercise real frontend polling and same-run recovery with deterministic I/O."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_assessment_poll_exhaustion_preserves_terminal_truth_and_recovery() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/assessment-poll-exhaustion.test.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
