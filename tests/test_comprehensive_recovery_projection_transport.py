"""Execute the real recovery TSX handlers; no production requests are made."""
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_comprehensive_recovery_projection_transport() -> None:
    node = shutil.which("node")
    assert node is not None, "Node is required by the existing NICO CI contract"
    result = subprocess.run(
        [node, str(ROOT / "tests/comprehensive_recovery_projection.cjs")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
