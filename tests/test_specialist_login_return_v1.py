"""Behavioral regressions for exact-run specialist sign-in navigation.

The Node harness transpiles the production TS/TSX and stubs framework hooks and
network/navigation boundaries. It does not authenticate against production.
"""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ["middleware:en", "middleware:es", "routes", "cookie"] + [
    f"{case}:{locale}"
    for case in (
        "existing", "post", "language", "network", "denied", "unsafe",
        "default", "nested", "duplicate", "unauthenticated", "language-unsafe",
    )
    for locale in ("en", "es")
]


@pytest.mark.parametrize("case", CASES)
def test_specialist_login_preserves_safe_exact_run(case: str) -> None:
    result = subprocess.run(
        ["node", str(ROOT / "tests/fixtures/specialist_login_return_harness.cjs"), case],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {case}" in result.stdout
