from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nico import evidence_pipeline_repair_v1 as repair
from nico import hosted_full_evidence_runtime_v2 as runtime
from nico import scanner_tool_runners as runners
from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace

FIXED_SHA = "8ed545766fb4c5054798a02ea17ece0fe7bcab64"


def _result(
    args: tuple[str, ...],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    stdout_path: Path | None = None,
    output_truncated: bool = False,
) -> WorkerCommandResult:
    return WorkerCommandResult(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        output_truncated=output_truncated,
        stdout_path=str(stdout_path) if stdout_path else None,
        stdout_bytes=stdout_path.stat().st_size if stdout_path and stdout_path.exists() else len(stdout.encode()),
        stderr_bytes=len(stderr.encode()),
    )


def test_fixed_sha_refresh_payload_requires_two_runs_for_nico() -> None:
    payload = runtime._payload_for_result(
        {
            "repository": "BoneManTGRM/NICO",
            "immutable_commit_sha": FIXED_SHA,
            "authorized_by": "refresh-full-evidence",
        }
    )

    assert payload["ref"] == FIXED_SHA
    assert payload["commit_sha"] == FIXED_SHA
    assert payload["target_commit_sha"] == FIXED_SHA
    assert payload["required_consecutive_runs"] == 2


def test_eslint_without_configuration_is_verified_not_applicable(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    repo_dir = tmp_path / "repo"
    web_dir = repo_dir / "apps" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "package.json").write_text('{"private": true}', encoding="utf-8")
    (web_dir / "package-lock.json").write_text('{"lockfileVersion": 3, "packages": {}}', encoding="utf-8")
    workspace = WorkerWorkspace(root=tmp_path)
    eslint = next(spec for spec in runners.TOOL_SPECS if spec.name == "eslint")

    payload = runners.run_scanner_tool(eslint, workspace, runner=lambda *args, **kwargs: _result(tuple(args[0])))
    normalized = normalize_scanner_worker_artifact({"tools": {"eslint": payload}})

    assert payload["status"] == "not_applicable"
    assert payload["verified_for_this_report"] is True
    assert normalized["tools"]["eslint"]["completed"] is True


def test_typescript_uses_exact_lockfile_and_complete_output(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")
    repo_dir = tmp_path / "repo"
    web_dir = repo_dir / "apps" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "package.json").write_text('{"private": true}', encoding="utf-8")
    (web_dir / "package-lock.json").write_text('{"lockfileVersion": 3, "packages": {}}', encoding="utf-8")
    (web_dir / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}', encoding="utf-8")
    workspace = WorkerWorkspace(root=tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_which(name: str) -> str | None:
        if name == "npm":
            return "/usr/bin/npm"
        return None

    monkeypatch.setattr(repair.shutil, "which", fake_which)

    def fake_runner(args: tuple[str, ...], **kwargs: Any) -> WorkerCommandResult:
        command = tuple(str(part) for part in args)
        calls.append(command)
        stdout_path = kwargs.get("stdout_path")
        if len(command) > 1 and command[1] == "ci":
            binary = web_dir / "node_modules" / ".bin" / "tsc"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            os.chmod(binary, 0o755)
            if stdout_path:
                Path(stdout_path).write_text("installed", encoding="utf-8")
            return _result(command, stdout_path=Path(stdout_path) if stdout_path else None)
        assert "--noEmit" in command
        if stdout_path:
            Path(stdout_path).write_text(
                "app/example.ts(4,2): error TS2322: Type 'string' is not assignable to type 'number'.\n",
                encoding="utf-8",
            )
        return _result(
            command,
            returncode=2,
            stdout="...[truncated by NICO worker]",
            stdout_path=Path(stdout_path) if stdout_path else None,
            output_truncated=True,
        )

    typescript = next(spec for spec in runners.TOOL_SPECS if spec.name == "typescript")
    artifact = runners.run_scanner_tools(workspace, specs=(typescript,), runner=fake_runner)
    payload = artifact["tools"]["typescript"]

    assert sum(1 for command in calls if len(command) > 1 and command[1] == "ci") == 1
    assert payload["status"] == "completed"
    assert payload["output_capture_complete"] is True
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["code"] == "TS2322"
    assert payload["raw_output_artifact"]["sha256"]


def test_bandit_reads_full_file_when_preview_is_truncated(tmp_path: Path, monkeypatch: Any) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    workspace = WorkerWorkspace(root=tmp_path)
    findings = [
        {
            "filename": f"nico/module_{index}.py",
            "line_number": index + 1,
            "issue_severity": "MEDIUM",
            "issue_confidence": "HIGH",
            "test_id": "B101",
        }
        for index in range(4000)
    ]

    monkeypatch.setattr(repair.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_runner(args: tuple[str, ...], **kwargs: Any) -> WorkerCommandResult:
        stdout_path = Path(kwargs["stdout_path"])
        stdout_path.write_text(json.dumps({"results": findings}), encoding="utf-8")
        return _result(
            tuple(args),
            returncode=1,
            stdout='{ "results": [ ...[truncated by NICO worker]',
            stdout_path=stdout_path,
            output_truncated=True,
        )

    bandit = next(spec for spec in runners.TOOL_SPECS if spec.name == "bandit")
    payload = runners.run_scanner_tool(bandit, workspace, runner=fake_runner)

    assert payload["status"] == "completed"
    assert payload["output_capture_complete"] is True
    assert payload["findings_count"] == 4000
    assert payload["raw_output_artifact"]["bytes"] > len(payload["stderr"])


def test_osv_fallback_queries_every_exact_dependency_not_first_150(tmp_path: Path, monkeypatch: Any) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    packages = {"": {"name": "fixture", "version": "1.0.0"}}
    for index in range(220):
        packages[f"node_modules/package-{index}"] = {"version": "1.0.0"}
    (repo_dir / "package.json").write_text('{"private": true}', encoding="utf-8")
    (repo_dir / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": packages}),
        encoding="utf-8",
    )
    workspace = WorkerWorkspace(root=tmp_path)
    batches: list[int] = []

    class Response:
        def __init__(self, count: int) -> None:
            self.count = count

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"results": [{} for _ in range(self.count)]}

    def fake_post(url: str, *, json: dict[str, Any], timeout: int) -> Response:
        count = len(json["queries"])
        batches.append(count)
        return Response(count)

    original_which = repair.shutil.which
    monkeypatch.setattr(repair.shutil, "which", lambda name: None if name == "osv-scanner" else original_which(name))
    monkeypatch.setattr(runners.requests, "post", fake_post)
    osv = next(spec for spec in runners.TOOL_SPECS if spec.name == "osv-scanner")
    payload = runners.run_scanner_tool(osv, workspace, runner=lambda *args, **kwargs: _result(tuple(args[0])))

    assert payload["status"] == "completed"
    assert payload["queried_dependency_count"] == 220
    assert sum(batches) == 220
    assert payload["coverage_complete"] is True


def test_repeatability_requires_two_clean_identical_fixed_sha_artifacts() -> None:
    tools = {
        name: {
            "tool": name,
            "status": "completed",
            "findings": [],
            "findings_count": 0,
            "full_history_verified": name in {"gitleaks", "trufflehog"},
        }
        for name in _required_tools()
    }
    normalized = normalize_scanner_worker_artifact({"tools": tools})
    base = {
        "worker_execution_state": "completed",
        "checkout": {"commit_sha": FIXED_SHA},
        "tools": tools,
        "normalized": normalized,
        "repeatability_fingerprint": "same-fingerprint",
        "provenance_verified": True,
        "artifact_hash": "first",
    }

    merged = repair._merge_repeatability_artifacts([dict(base), {**base, "artifact_hash": "second"}], FIXED_SHA)

    assert merged["repeatability_verified"] is True
    assert merged["repeatability"]["clean_runs"] == 2
    assert merged["repeatability"]["observed_commit_shas"] == [FIXED_SHA, FIXED_SHA]
    assert merged["provenance_verified"] is True


def _required_tools() -> tuple[str, ...]:
    return (
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    )
