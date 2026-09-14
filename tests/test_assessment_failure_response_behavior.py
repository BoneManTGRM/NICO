"""Exercise the actual browser fetch bridge with isolated network and DOM adapters."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_comprehensive_failure_bridge_requires_terminal_authority() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable; run the frontend suite after npm ci.")
    available = subprocess.run(
        [node, "-e", "require(require.resolve('typescript', {paths: [process.cwd() + '/apps/web']}))"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    if available.returncode:
        pytest.skip("Frontend TypeScript is unavailable; install apps/web dependencies first.")
    result = subprocess.run(
        [node, "--test", "tests/frontend/assessment_failure_response.test.cjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
