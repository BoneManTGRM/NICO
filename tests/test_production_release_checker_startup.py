from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sysconfig
import venv

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def workflow_python(tmp_path_factory):
    """Dependencies are available, but editable checkout hooks are not executed."""
    environment = tmp_path_factory.mktemp("release-checker-python")
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / "bin" / "python"
    site_packages = next(environment.glob("lib/python*/site-packages"))
    # Adding a dependency directory does not execute its .pth/editable hooks.
    (site_packages / "dependencies.pth").write_text(
        sysconfig.get_path("purelib") + "\n", encoding="utf-8"
    )
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PYTHON") and key != "GITHUB_TOKEN"}
    probe = subprocess.run(
        [str(python), "-c", "import importlib.util; assert importlib.util.find_spec('nico') is None"],
        cwd=environment, env=env, capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0, probe.stderr
    return python, env


def test_workflow_file_entrypoint_starts_without_pythonpath(workflow_python):
    python, env = workflow_python
    result = subprocess.run(
        [str(python), "scripts/check_production_release_with_spanish.py", "--help"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Fail-closed NICO production release gate" in result.stdout
    assert "--record-deployment" in result.stdout


def test_workflow_entrypoint_blocks_and_writes_manifest_without_evidence(workflow_python, tmp_path):
    python, env = workflow_python
    output = tmp_path / "release-manifest.json"
    result = subprocess.run(
        [str(python), "scripts/check_production_release_with_spanish.py",
         "--repository", "synthetic/release-checker", "--sha", "a" * 40,
         "--backend-url", "invalid://backend", "--frontend-url", "invalid://frontend",
         "--github-api", "invalid://github", "--output", str(output),
         "--record-deployment"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["release_ready"] is False
    assert manifest["last_known_good_record"] == {
        "status": "not_recorded", "reason": "release_gate_blocked",
    }
    assert "workflow_spanish_comprehensive_production_proof" in manifest["blockers"]
