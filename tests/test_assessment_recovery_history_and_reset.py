"""Keep browser persistence failures and stale timeouts out of saved run state."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_saved_review_recovery_and_explicit_reset() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/assessment-recovery-history.test.cjs",
         "tests/js/assessment-reset-timeout.test.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
