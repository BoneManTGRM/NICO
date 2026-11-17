"""Build real artifacts offline so package-data regressions cannot hide in source imports."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile


def test_semgrep_rules_survive_sdist_wheel_and_install(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    source.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(root / name, source / name)
    for package in root.glob("nico*"):
        if package.is_dir() and (package / "__init__.py").is_file():
            shutil.copytree(package, source / package.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    expected = (root / "nico/semgrep_rules_v1.yml").read_bytes()
    dist = tmp_path / "dist"
    dist.mkdir()
    env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}

    def run(*args: str, cwd: Path) -> None:
        result = subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    run("-c", f"import setuptools.build_meta as b; b.build_sdist({str(dist)!r})", cwd=source)
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        member = next((m for m in archive.getmembers() if m.name.endswith("/nico/semgrep_rules_v1.yml")), None)
        assert member is not None, "sdist omits runtime Semgrep rules"
        assert archive.extractfile(member).read() == expected
        unpacked = tmp_path / "unpacked"
        archive.extractall(unpacked, filter="data")
    run("-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation", "--wheel-dir", str(dist), str(next(unpacked.iterdir())), cwd=tmp_path)
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert archive.read("nico/semgrep_rules_v1.yml") == expected
    installed = tmp_path / "installed"
    run("-m", "pip", "install", "--no-index", "--no-deps", "--target", str(installed), str(wheel), cwd=tmp_path)
    assert (installed / "nico/semgrep_rules_v1.yml").read_bytes() == expected
