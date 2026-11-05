"""Complete render characterization using the installed frontend toolchain."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_report_actions_characterization():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable; install the frontend toolchain.")
    available = subprocess.run(
        [node, "-e", "require(require.resolve('typescript', {paths: [process.cwd() + '/apps/web']}))"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    if available.returncode:
        pytest.skip("Frontend TypeScript is unavailable; install apps/web dependencies first.")
    result = subprocess.run(
        [node, "--test", "tests/frontend/report_actions_characterization.test.cjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
