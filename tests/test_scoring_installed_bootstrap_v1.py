"""Owned retained-input controls through installed production scoring bindings.

These are synthetic corpora, not live assessments or accuracy calibration against
historical reports. Only the retained scan-storage read is replaced by a fixture.
"""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
@pytest.mark.parametrize("language", ["python", "node", "mixed"])
def test_installed_scoring_preserves_fixed_input_truth(bootstrap, language):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "_installed_scoring_probe.py"), bootstrap, language],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-6000:]
