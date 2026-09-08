"""Actual CLI import boundary, isolated from pytest and editable installations."""
from pathlib import Path
import subprocess
import sys
import sysconfig

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = """_REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

"""
GATE_IMPORT = "from nico.complete_assessment_gate_v1 import require_retained_assessment, ScannerEvidenceBlocked\n"
CHILD = r"""
import pathlib
import sys

script = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
# -I -S omits cwd, PYTHONPATH, user site, .pth execution and editable finders.
# Add installed third-party wheels as plain directories, without site.addsitedir.
sys.path.extend(sys.argv[3:])
sys.path.insert(0, str(script.parent))
source = script.read_text(encoding="utf-8")
bootstrap = '''_REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

'''
gate_import = "from nico.complete_assessment_gate_v1 import require_retained_assessment, ScannerEvidenceBlocked\n"
if mode != "current":
    assert source.count(bootstrap) == 1
    source = source.replace(bootstrap, "")
if mode == "legacy_lazy":
    assert source.count(gate_import) == 1
    source = source.replace(gate_import, "")
    marker = "    try:\n        retention = require_retained_assessment"
    assert source.count(marker) == 1
    source = source.replace(marker, "    " + gate_import + marker)
sys.argv = [str(script), "--help"]
try:
    exec(compile(source, str(script), "exec"), {"__name__": "__main__", "__file__": str(script)})
except SystemExit as exc:
    assert exc.code == 0, exc.code
assert "nico.complete_assessment_gate_v1" in sys.modules, "validator_not_loaded_before_cli_work"
"""


def _invoke(tmp_path, entrypoint, mode="current"):
    wheel_paths = sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c", CHILD, str(ROOT / "scripts" / entrypoint), mode, *wheel_paths],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("entrypoint", [
    "completed_run_two_pass_acceptance_v1.py",
    "completed_run_authenticated_two_pass_acceptance_v1.py",
])
def test_actual_production_cli_loads_validator_before_work(tmp_path, entrypoint):
    result = _invoke(tmp_path, entrypoint)
    assert result.returncode == 0, result.stderr
    assert "--frontend-url" in result.stdout


def test_missing_checkout_bootstrap_is_rejected_even_with_ci_editable_install(tmp_path):
    result = _invoke(tmp_path, "completed_run_two_pass_acceptance_v1.py", "missing_bootstrap")
    assert result.returncode != 0
    assert "ModuleNotFoundError: No module named 'nico'" in result.stderr


def test_original_lazy_import_is_not_accepted_by_help_only_probe(tmp_path):
    result = _invoke(tmp_path, "completed_run_two_pass_acceptance_v1.py", "legacy_lazy")
    assert result.returncode != 0
    assert "validator_not_loaded_before_cli_work" in result.stderr
