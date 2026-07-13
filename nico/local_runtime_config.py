from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class LocalRuntimeConfigError(ValueError):
    """Raised when local runtime path configuration is unsafe or ambiguous."""


@dataclass(frozen=True)
class LocalRuntimePaths:
    project_root: Path
    nico_home: Path
    db_path: Path
    report_dir: Path
    test_lab: Path
    sample_repo: Path
    drift_repo: Path


def _configured_path(
    env: Mapping[str, str],
    key: str,
    default: Path,
) -> Path:
    raw = env.get(key)
    if raw is None:
        return default
    value = str(raw)
    if not value.strip():
        raise LocalRuntimeConfigError(f"{key} must not be empty")
    if "\x00" in value:
        raise LocalRuntimeConfigError(f"{key} contains an invalid null byte")
    return Path(value)


def resolve_local_runtime_paths(
    env: Mapping[str, str] | None = None,
    *,
    project_root: Path | str | None = None,
) -> LocalRuntimePaths:
    """Resolve local paths without touching the filesystem or reading secrets."""

    source = os.environ if env is None else env
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[1]
    home = _configured_path(source, "NICO_HOME", root / ".nico")
    db_path = _configured_path(source, "NICO_DB_PATH", home / "nico.sqlite3")
    report_dir = _configured_path(source, "NICO_REPORT_DIR", home / "reports")
    test_lab = root / "nico" / "test_lab"
    return LocalRuntimePaths(
        project_root=root,
        nico_home=home,
        db_path=db_path,
        report_dir=report_dir,
        test_lab=test_lab,
        sample_repo=test_lab / "sample_repo",
        drift_repo=test_lab / "drift_workspace",
    )


def public_runtime_config(
    paths: LocalRuntimePaths | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return only non-secret path metadata suitable for diagnostics and tests."""

    resolved = paths or RUNTIME_PATHS
    source = os.environ if env is None else env
    return {
        "project_root": str(resolved.project_root),
        "nico_home": str(resolved.nico_home),
        "db_path": str(resolved.db_path),
        "report_dir": str(resolved.report_dir),
        "test_lab": str(resolved.test_lab),
        "sources": {
            "nico_home": "environment" if "NICO_HOME" in source else "default",
            "db_path": "environment" if "NICO_DB_PATH" in source else "default",
            "report_dir": "environment" if "NICO_REPORT_DIR" in source else "default",
        },
    }


RUNTIME_PATHS = resolve_local_runtime_paths()
PROJECT_ROOT = RUNTIME_PATHS.project_root
NICO_HOME = RUNTIME_PATHS.nico_home
DB_PATH = RUNTIME_PATHS.db_path
REPORT_DIR = RUNTIME_PATHS.report_dir
TEST_LAB = RUNTIME_PATHS.test_lab
SAMPLE_REPO = RUNTIME_PATHS.sample_repo
DRIFT_REPO = RUNTIME_PATHS.drift_repo


__all__ = [
    "LocalRuntimeConfigError",
    "LocalRuntimePaths",
    "resolve_local_runtime_paths",
    "public_runtime_config",
    "RUNTIME_PATHS",
    "PROJECT_ROOT",
    "NICO_HOME",
    "DB_PATH",
    "REPORT_DIR",
    "TEST_LAB",
    "SAMPLE_REPO",
    "DRIFT_REPO",
]
