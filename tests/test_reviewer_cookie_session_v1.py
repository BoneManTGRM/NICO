"""Execute the shipped reviewer components and proxy with synthetic sessions."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_reviewer_workspace_uses_existing_session_without_admin_secret() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/reviewer-cookie-session.test.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
