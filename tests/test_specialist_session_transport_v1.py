"""Run behavioral session-route and loopback transport regressions.

The harness executes production TypeScript. It substitutes NextResponse at the
framework boundary and uses only synthetic credentials, never production access.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_specialist_session_transport_is_fail_closed_and_recoverable() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/specialist-session-transport.test.cjs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
