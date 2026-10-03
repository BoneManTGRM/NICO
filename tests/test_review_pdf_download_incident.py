"""Real frontend modules with synthetic exact-run download fixtures."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_retained_pdf_download_progress_integrity_and_recovery():
    if not shutil.which("node"):
        pytest.skip("Node runtime unavailable; frontend regression not verified")
    result = subprocess.run(
        ["node", "--test", "tests/js/review-pdf-download.test.cjs",
         "tests/js/artifact-timeout-diagnostics.test.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
