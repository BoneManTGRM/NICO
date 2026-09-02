from __future__ import annotations

import gzip
import json
from pathlib import Path

from nico.scanner_evidence_pipeline_v1 import (
    REQUIRED_EVIDENCE_TOOLS,
    _deterministic_fingerprint,
    _eslint_config,
    _javascript_source_targets,
    _raw_blob,
    _run_bandit,
    _run_eslint,
    _run_osv,
    _run_typescript,
    _semgrep_config,
    materialize_raw_artifacts,
)
from nico.scanner_tool_runners import ProjectCommandPreparation, ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace

ROOT = Path(__file__).resolve().parents[1]


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    return workspace


def test_bandit_complete_file_capture_survives_truncated_preview(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr("nico.bandit_json_execution_v61.shutil.which", lambda name: f"/tools/{name}")

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        Path(args[args.index("-o") + 1]).write_text(
            json.dumps(
                {
                    "errors": [],
                    "metrics": {},
                    "results": [
                        {
                            "filename": "nico/example.py",
                            "test_name": "assert_used",
                            "test_id": "B101",
                            "issue_severity": "LOW",
                            "issue_confidence": "HIGH",
                            "issue_text": "Use of assert detected",
                            "line_number": 9,
                            "line_range": [9],
                            "code": "assert value",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        stdout_path.write_text("Bandit preview only", encoding="utf-8")
        return WorkerCommandResult(
            args=tuple(args),
            returncode=1,
            stdout="Bandit preview only",
            stderr="",
            output_truncated=True,
            stdout_path=str(stdout_path),
            stdout_bytes=32 * 1024 * 1024,
        )

    result = _run_bandit(
        ScannerToolSpec("bandit", ("bandit",), "static", timeout_seconds=30, max_output_chars=100),
        workspace,
        runner,
    )

    assert result["status"] == "completed"
    assert result["output_truncated"] is True
    assert result["output_capture_complete"] is True
    assert result["raw_artifact_capture_complete"] is True
    assert result["raw_artifact_format"] == "json"
    assert result["findings_count"] == 1
    assert result["execution_source"] == "canonical_bandit_json_v62"
    assert result["bandit_csv_parser_used"] is False


def test_osv_uses_v2_source_scan_before_legacy_fallback(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr("nico.scanner_evidence_pipeline_v1.shutil.which", lambda name: f"/tools/{name}")
    calls: list[tuple[str, ...]] = []

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        calls.append(tuple(args))
        stdout_path.write_text('{"results": []}', encoding="utf-8")
        return WorkerCommandResult(
            args=tuple(args), returncode=0, stdout='{"results": []}', stderr="",
            stdout_path=str(stdout_path), stdout_bytes=15,
        )

    result = _run_osv(
        ScannerToolSpec("osv-scanner", ("osv-scanner",), "dependency", timeout_seconds=30),
        workspace,
        runner,
    )

    assert result["status"] == "completed"
    assert calls[0][1:4] == ("scan", "source", "-r")
    assert len(calls) == 1
    assert result["command_variant"] == 1


def test_redacted_raw_artifacts_are_gzipped_checksummed_and_retained(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_text("token = abcdefghijklmnop\n", encoding="utf-8")
    artifact = {
        "tools": {
            tool: {"tool": tool, "status": "completed", "verified_for_this_report": True}
            for tool in REQUIRED_EVIDENCE_TOOLS
        },
        "required_scanner_completion": True,
        "raw_artifact_capture_complete": True,
        "raw_artifact_blobs": {
            tool: _raw_blob(tool, source, "txt") for tool in REQUIRED_EVIDENCE_TOOLS
        },
    }

    materialize_raw_artifacts(
        artifact,
        tmp_path / "retained",
        repository="BoneManTGRM/NICO",
        commit_sha="8ed545766fb4c5054798a02ea17ece0fe7bcab64",
        run_id="proof-1",
    )

    assert artifact["raw_artifact_retention_complete"] is True
    assert artifact["scanner_evidence_ready"] is True
    assert set(artifact["raw_artifacts"]) == set(REQUIRED_EVIDENCE_TOOLS)
    for metadata in artifact["raw_artifacts"].values():
        path = tmp_path / "retained" / metadata["storage_key"]
        assert path.stat().st_mode & 0o777 == 0o600
        retained = gzip.decompress(path.read_bytes()).decode("utf-8")
        assert "abcdefghijklmnop" not in retained
        assert "[REDACTED]" in retained


def test_production_bootstrap_installs_final_scanner_pipeline_before_exact_binding() -> None:
    source = (ROOT / "nico/api/terminal_authority_bootstrap.py").read_text(encoding="utf-8")
    install = source.index("install_scanner_evidence_pipeline_v1()")
    exact = source.index("install_exact_commit_binding()")
    assert install < exact
    assert "durable_redacted_raw_artifacts" in source
    assert "public_scanner_tool_api_unchanged" in source


def test_docker_runtime_has_bounded_large_capture_memory_and_durable_root() -> None:
    source = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "NICO_MAX_SCANNER_PARSE_BYTES=268435456" in source
    assert "NICO_NODE_OPTIONS=--max-old-space-size=2048" in source
    assert "NICO_SCANNER_RAW_ARTIFACT_ROOT=/data/scanner-artifacts" in source
    assert "NICO_ESLINT_MODULE_ROOT=/usr/local/lib/node_modules" in source
    assert "NICO_ESLINT_PARSER_ENTRY=/usr/local/lib/node_modules/@typescript-eslint/parser/dist/index.js" in source
    assert "/data/scanner-artifacts" in source


def test_frozen_sha_proof_requires_two_complete_equivalent_runs() -> None:
    proof = (ROOT / "scripts/frozen_scanner_evidence_proof.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/frozen-sha-scanner-proof.yml").read_text(encoding="utf-8")
    dispatch = (ROOT / ".github/workflows/phase6-proof-dispatch.yml").read_text(encoding="utf-8")
    assert "run_number=1" in proof
    assert "run_number=2" in proof
    assert "two_consecutive_clean_runs" in proof
    assert "deterministic_fingerprints_equal" in proof
    assert "raw_artifact_retention_complete" in proof
    assert "workflow_dispatch:" in workflow
    assert "workflow_call:" in workflow
    assert "TARGET_SHA: ${{ inputs.target_sha }}" in workflow
    assert "phase6-final-comprehensive-${{ env.TARGET_SHA }}" in workflow
    assert "build_phase6_verification_package.py" in workflow
    assert workflow.count("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1") == 2
    assert "retention-days: 90" in workflow
    assert "Wait for authoritative exact-SHA required checks" in dispatch
    assert "gh workflow run frozen-sha-scanner-proof.yml" in dispatch
    assert "-f target_sha=\"$TARGET_SHA\"" in dispatch


def test_pipeline_does_not_replace_public_scanner_tool_api() -> None:
    source = (ROOT / "nico/scanner_evidence_pipeline_v1.py").read_text(encoding="utf-8")
    assert "scanner_tool_runners.run_scanner_tool =" not in source
    assert "hosted_scanner_worker.run_scanner_tools = final_run_scanner_tools" in source
    assert "missing_evidence_is_not_clean" in source


def test_eslint_profile_uses_explicit_module_root(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    web_dir = workspace.repo_dir / "apps" / "web"
    web_dir.mkdir(parents=True)
    module = tmp_path / "scanner-node" / "@typescript-eslint" / "parser"
    (module / "dist").mkdir(parents=True)
    entry = module / "dist" / "index.js"
    entry.write_text("module.exports = {};\n", encoding="utf-8")
    (module / "package.json").write_text('{"name":"@typescript-eslint/parser","main":"dist/index.js"}', encoding="utf-8")
    monkeypatch.setenv("NICO_ESLINT_MODULE_ROOT", str(tmp_path / "scanner-node"))

    config, reason = _eslint_config(workspace, web_dir)

    assert reason == ""
    assert config is not None
    assert str(entry.resolve()) in config.read_text(encoding="utf-8")


def test_root_node_project_routes_eslint_and_typescript_to_entire_project(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    project = workspace.repo_dir
    (project / "src").mkdir()
    (project / "src" / "server.ts").write_text(
        "export const ready = true;\n", encoding="utf-8"
    )
    (project / "tsconfig.json").write_text("{}", encoding="utf-8")
    bin_dir = project / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    for name in ("eslint", "tsc"):
        binary = bin_dir / name
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)
    parser = tmp_path / "parser.js"
    parser.write_text("module.exports = {};\n", encoding="utf-8")
    monkeypatch.setenv("NICO_ESLINT_PARSER_ENTRY", str(parser))
    monkeypatch.setattr(
        "nico.scanner_evidence_pipeline_v1.shutil.which", lambda name: None
    )
    preparation = ProjectCommandPreparation("completed", project, True)
    calls: list[tuple[tuple[str, ...], Path]] = []

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del limits, extra_env
        calls.append((tuple(args), cwd))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("[]" if "eslint" in Path(args[0]).name else "", encoding="utf-8")
        return WorkerCommandResult(
            args=tuple(args), returncode=0, stdout="", stderr="",
            stdout_path=str(stdout_path), stdout_bytes=2 if "eslint" in Path(args[0]).name else 0,
        )

    eslint = _run_eslint(
        ScannerToolSpec("eslint", ("eslint",), "static"),
        workspace,
        runner,
        preparation,
    )
    typescript = _run_typescript(
        ScannerToolSpec("typescript", ("tsc",), "static"),
        workspace,
        runner,
        preparation,
    )

    assert _javascript_source_targets(project) == (".",)
    assert eslint["status"] == "completed"
    assert typescript["status"] == "completed"
    assert calls[0][1] == project
    assert calls[0][0][1] == "."
    assert calls[1][1] == project
    assert calls[1][0][-1] == str(project / "tsconfig.json")


def test_semgrep_profile_is_local_deterministic_and_metrics_independent(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    config = _semgrep_config(workspace)
    text = config.read_text(encoding="utf-8")

    assert "rules:" in text
    assert "nico.python.subprocess-shell" in text
    assert "nico.javascript.new-function" in text
    assert "--config auto" not in (ROOT / "nico/scanner_evidence_pipeline_v1.py").read_text(encoding="utf-8")


def test_trufflehog_fingerprint_ignores_volatile_internal_clone_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    base = {
        "tool": "trufflehog",
        "status": "completed",
        "returncode": 0,
        "full_history_verified": True,
        "output_capture_complete": True,
        "findings": [{
            "DetectorName": "Example",
            "SourceMetadata": {"Data": {"Git": {
                "commit": "abc123",
                "file": "example.txt",
                "line": 7,
                "repository_local_path": "/tmp/trufflehog-111-random",
            }}},
        }],
    }
    other = json.loads(json.dumps(base))
    other["findings"][0]["SourceMetadata"]["Data"]["Git"]["repository_local_path"] = "/tmp/trufflehog-999-other"
    changed = json.loads(json.dumps(base))
    changed["findings"][0]["SourceMetadata"]["Data"]["Git"]["line"] = 8

    assert _deterministic_fingerprint(base, workspace) == _deterministic_fingerprint(other, workspace)
    assert _deterministic_fingerprint(base, workspace) != _deterministic_fingerprint(changed, workspace)
