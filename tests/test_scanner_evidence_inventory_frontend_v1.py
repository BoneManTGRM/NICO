"""Exercise the actual narrowly allowlisted TypeScript proxy."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_evidence_proxy_preserves_authenticated_read_only_boundary():
    result = subprocess.run(
        ["node", "--test", "tests/js/scanner-evidence-inventory.test.cjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
