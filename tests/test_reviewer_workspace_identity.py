"""Exercise the real reviewer page with synthetic browser and HTTP boundaries."""
from pathlib import Path
import subprocess


def test_reviewer_workspace_identity_and_response_boundaries():
    result = subprocess.run(
        ["node", "--test", "tests/js/reviewer-workspace.test.cjs"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        timeout=90, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
