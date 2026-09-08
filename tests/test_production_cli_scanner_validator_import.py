"""Exercise the production CLI import boundary without pytest's repository path."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("entrypoint", [
    "completed_run_two_pass_acceptance_v1.py",
    "completed_run_authenticated_two_pass_acceptance_v1.py",
])
def test_production_cli_resolves_retained_scanner_validator_without_pythonpath(tmp_path, entrypoint):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / entrypoint), "--help"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--frontend-url" in result.stdout
    assert "Traceback" not in result.stderr
