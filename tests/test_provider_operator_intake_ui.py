"""Execute the operator UI and its intake boundary, including uncertain writes."""
from pathlib import Path
import shutil
import subprocess


def test_operator_intake_ui_and_submission_recovery():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which('node') or 'node', 'tests/frontend/provider-intake-ui.cjs'],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
