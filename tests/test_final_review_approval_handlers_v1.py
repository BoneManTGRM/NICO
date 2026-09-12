"""Run the isolated TSX handler tests when the frontend toolchain is installed.

These tests use mock React/DOM/network adapters, not browser or production evidence.
The normal frontend installation supplies TypeScript; no packages are downloaded here.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_actual_final_review_handlers() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable; run the frontend handler suite after npm ci.")
    available = subprocess.run(
        [node, "-e", "require(require.resolve('typescript', {paths: [process.cwd() + '/apps/web']}))"],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    if available.returncode:
        pytest.skip("Frontend TypeScript is unavailable; install apps/web dependencies first.")
    result = subprocess.run(
        [node, "--test", "tests/frontend/final_review_approval.test.cjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
