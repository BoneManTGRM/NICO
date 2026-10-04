"""Real frontend modules with synthetic exact-run download fixtures."""
from pathlib import Path
import shutil
import re
import subprocess

import pytest


def test_retained_pdf_download_progress_integrity_and_recovery():
    if not shutil.which("node"):
        pytest.skip("Node runtime unavailable; frontend regression not verified")
    result = subprocess.run(
        ["node", "--test", "tests/js/review-pdf-download.test.cjs",
         "tests/js/artifact-timeout-diagnostics.test.cjs",
         "tests/js/workspace-review-pdf-fallback.test.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    output = result.stdout + result.stderr
    print(output, end="")
    assert result.returncode == 0, output
    test_count = re.search(r"(?m)^# tests (\d+)$", result.stdout)
    passed = re.search(r"(?m)^# pass (\d+)$", result.stdout)
    assert test_count and int(test_count.group(1)) >= 71, output
    assert passed and int(passed.group(1)) == int(test_count.group(1)), output
    assert "# skipped 0" in result.stdout, output
    assert "# fail 0" in result.stdout, output
