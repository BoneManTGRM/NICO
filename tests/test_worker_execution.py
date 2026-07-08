from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nico.worker_execution import (
    WorkerLimits,
    cleanup_workspace,
    make_workspace,
    run_command,
    validate_ref,
    validate_repository,
    workspace_from_temp,
)


def test_validate_repository_accepts_owner_name_and_urls():
    assert validate_repository("BoneManTGRM/NICO") == "BoneManTGRM/NICO"
    assert validate_repository("https://github.com/BoneManTGRM/NICO.git") == "BoneManTGRM/NICO"


@pytest.mark.parametrize("value", ["", "owner only", "owner/repo/../../x", "owner/repo with space", "owner/repo.git/extra"])
def test_validate_repository_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        validate_repository(value)


def test_validate_ref_accepts_normal_refs():
    assert validate_ref("main") == "main"
    assert validate_ref("release/2026.07") == "release/2026.07"
    assert validate_ref("feature-worker_1") == "feature-worker_1"


@pytest.mark.parametrize("value", ["", "../main", "feature branch", "main~1", "main^", "main:evil", "bad*ref", "-main", "/main", "main.lock"])
def test_validate_ref_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        validate_ref(value)


def test_run_command_captures_success(tmp_path: Path):
    result = run_command((sys.executable, "-c", "print('ok')"), cwd=tmp_path, limits=WorkerLimits(timeout_seconds=5))

    assert result.ok is True
    assert result.stdout.strip() == "ok"
    assert result.stderr == ""


def test_run_command_truncates_output(tmp_path: Path):
    result = run_command(
        (sys.executable, "-c", "print('x' * 100)"),
        cwd=tmp_path,
        limits=WorkerLimits(timeout_seconds=5, max_output_chars=30),
    )

    assert result.ok is True
    assert result.output_truncated is True
    assert "truncated by NICO worker" in result.stdout


def test_run_command_times_out(tmp_path: Path):
    result = run_command(
        (sys.executable, "-c", "import time; time.sleep(2)"),
        cwd=tmp_path,
        limits=WorkerLimits(timeout_seconds=1, max_output_chars=1000),
    )

    assert result.ok is False
    assert result.timed_out is True
    assert result.returncode == 124


def test_workspace_cleanup_removes_directory():
    temp = make_workspace()
    workspace = workspace_from_temp(temp)
    root = workspace.root
    assert root.exists()

    cleanup_workspace(workspace)
    assert not root.exists()
    temp.cleanup()
