"""Behavioral regressions for the real middleware and bilingual login components."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_specialist_login_return_behavior() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/specialist-login-return.test.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
