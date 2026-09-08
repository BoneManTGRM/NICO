from pathlib import Path
import subprocess


def test_authenticated_retained_evidence_gateway():
    result = subprocess.run(
        ['node', '--test', 'tests/js/retained-evidence-gateway.test.cjs'],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
