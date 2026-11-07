"""Synthetic material inputs exercise real artifact builders and installed scoring.

Storage and the local API service remain fixtures; native scanners and deployed
services are not exercised. Both PDFs' visible score labels must preserve canonical scores.
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
def test_installed_material_scoring_survives_bilingual_rendering(bootstrap, language):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "_installed_scoring_probe.py"),
         bootstrap, language, "material"],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-6000:]
