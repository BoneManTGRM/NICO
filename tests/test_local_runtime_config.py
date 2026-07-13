from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nico.local_runtime_config import (
    LocalRuntimeConfigError,
    public_runtime_config,
    resolve_local_runtime_paths,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONFIG_MODULE = ROOT / "nico" / "local_runtime_config.py"
CLI_ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"
LOCAL_SCAN_SERVICE = ROOT / "nico" / "local_scan_service.py"


def test_default_paths_preserve_the_legacy_layout(tmp_path: Path) -> None:
    paths = resolve_local_runtime_paths({}, project_root=tmp_path)

    assert paths.project_root == tmp_path
    assert paths.nico_home == tmp_path / ".nico"
    assert paths.db_path == tmp_path / ".nico" / "nico.sqlite3"
    assert paths.report_dir == tmp_path / ".nico" / "reports"
    assert paths.test_lab == tmp_path / "nico" / "test_lab"
    assert paths.sample_repo == paths.test_lab / "sample_repo"
    assert paths.drift_repo == paths.test_lab / "drift_workspace"


def test_environment_overrides_preserve_path_semantics(tmp_path: Path) -> None:
    paths = resolve_local_runtime_paths(
        {
            "NICO_HOME": "relative-home",
            "NICO_DB_PATH": "relative-db.sqlite3",
            "NICO_REPORT_DIR": "relative-reports",
        },
        project_root=tmp_path,
    )

    assert paths.nico_home == Path("relative-home")
    assert paths.db_path == Path("relative-db.sqlite3")
    assert paths.report_dir == Path("relative-reports")

    inherited = resolve_local_runtime_paths(
        {"NICO_HOME": "relative-home"},
        project_root=tmp_path,
    )
    assert inherited.db_path == Path("relative-home") / "nico.sqlite3"
    assert inherited.report_dir == Path("relative-home") / "reports"


@pytest.mark.parametrize("key", ["NICO_HOME", "NICO_DB_PATH", "NICO_REPORT_DIR"])
def test_invalid_path_configuration_fails_closed(tmp_path: Path, key: str) -> None:
    with pytest.raises(LocalRuntimeConfigError):
        resolve_local_runtime_paths({key: "   "}, project_root=tmp_path)
    with pytest.raises(LocalRuntimeConfigError):
        resolve_local_runtime_paths({key: "unsafe\x00path"}, project_root=tmp_path)


def test_runtime_config_module_body_does_not_create_directories(tmp_path: Path) -> None:
    home = tmp_path / "state" / "nico-home"
    report_dir = tmp_path / "state" / "reports"
    db_path = tmp_path / "state" / "db" / "nico.sqlite3"
    env = os.environ.copy()
    env.update(
        {
            "NICO_HOME": str(home),
            "NICO_DB_PATH": str(db_path),
            "NICO_REPORT_DIR": str(report_dir),
        }
    )
    isolated_loader = f"""
import importlib.util
import json
import sys
spec = importlib.util.spec_from_file_location("nico_local_runtime_config_isolated", {str(RUNTIME_CONFIG_MODULE)!r})
assert spec is not None and spec.loader is not None
config = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = config
spec.loader.exec_module(config)
print(json.dumps(config.public_runtime_config()))
"""

    completed = subprocess.run(
        [sys.executable, "-c", isolated_loader],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["db_path"] == str(db_path)
    assert not home.exists()
    assert not report_dir.exists()
    assert not db_path.parent.exists()


def test_public_runtime_config_exposes_no_unrelated_environment_or_secrets(tmp_path: Path) -> None:
    env = {
        "NICO_HOME": str(tmp_path / "home"),
        "NICO_GITHUB_TOKEN": "secret-token-value",
        "DATABASE_URL": "postgresql://user:password@example.invalid/database",
    }
    paths = resolve_local_runtime_paths(env, project_root=tmp_path)
    encoded = json.dumps(public_runtime_config(paths, env), sort_keys=True)

    assert "secret-token-value" not in encoded
    assert "postgresql://" not in encoded
    assert set(public_runtime_config(paths, env)) == {
        "project_root",
        "nico_home",
        "db_path",
        "report_dir",
        "test_lab",
        "sources",
    }


def test_extracted_defaults_match_legacy_compatibility_constants() -> None:
    import nico.cli as legacy
    import nico.local_runtime_config as runtime

    assert runtime.PROJECT_ROOT == legacy.PROJECT_ROOT
    assert runtime.NICO_HOME == legacy.NICO_HOME
    assert runtime.DB_PATH == legacy.DB_PATH
    assert runtime.REPORT_DIR == legacy.REPORT_DIR
    assert runtime.TEST_LAB == legacy.TEST_LAB
    assert runtime.SAMPLE_REPO == legacy.SAMPLE_REPO
    assert runtime.DRIFT_REPO == legacy.DRIFT_REPO


def test_canonical_path_consumers_no_longer_source_paths_from_cli_monolith() -> None:
    entrypoint_source = CLI_ENTRYPOINT.read_text(encoding="utf-8")
    scan_source = LOCAL_SCAN_SERVICE.read_text(encoding="utf-8")

    assert "from nico.local_runtime_config import DB_PATH" in entrypoint_source
    runtime_import = next(
        line for line in scan_source.splitlines()
        if line.startswith("from nico.local_runtime_config import ")
    )
    assert all(name in runtime_import for name in ("DB_PATH", "DRIFT_REPO", "SAMPLE_REPO", "TEST_LAB"))
    assert "PROJECT_ROOT =" not in scan_source
    assert "from nico.cli import" not in entrypoint_source
    assert "from nico.cli import" not in scan_source
