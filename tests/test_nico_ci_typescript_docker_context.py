"""Exercise Docker's real context filtering without pulls, RUN, or application build."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess

from nico.nico_ci_typescript_github_v1 import TRUSTED_FILES, WORKFLOW

ROOT = Path(__file__).resolve().parents[1]


def test_reviewed_workflow_survives_real_docker_context(tmp_path):
    context = tmp_path / "context"
    output = tmp_path / "export"
    context.mkdir()
    shutil.copyfile(ROOT / ".dockerignore", context / ".dockerignore")
    for relative in TRUSTED_FILES:
        target = context / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    excluded = (".github/workflows/unrelated.yml", ".github/CODEOWNERS",
                ".github/actions/example/action.yml", ".github/workflows/nested/private.yml",
                ".git/config", ".env", "node_modules/example/index.js")
    for relative in excluded:
        target = context / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("owned excluded sentinel")
    # Same COPY . . context boundary as production, with no base image or RUN.
    assert "COPY . ." in (ROOT / "Dockerfile").read_text()
    result = subprocess.run(
        ["docker", "build", "--network=none", "--pull=false", "--output",
         f"type=local,dest={output}", "-f", "-", str(context)],
        input="FROM scratch\nCOPY . /\n", text=True, capture_output=True,
        timeout=90, check=False,
        env={**os.environ, "DOCKER_CONFIG": str(tmp_path / "docker-config")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for relative in TRUSTED_FILES:
        assert (output / relative).is_file(), f"reviewed controller file excluded: {relative}"
        assert hashlib.sha256((output / relative).read_bytes()).digest() == hashlib.sha256((ROOT / relative).read_bytes()).digest()
    for relative in excluded:
        assert not (output / relative).exists(), f"unrelated/private context included: {relative}"
    assert [p.relative_to(output).as_posix() for p in (output / ".github").rglob("*") if p.is_file()] == [WORKFLOW]
