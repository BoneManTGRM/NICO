from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nico import frozen_sha_scanner_evidence_v1 as pipeline
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "nico/api/comprehensive_production_bootstrap.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/frozen-sha-scanner-qualification.yml").read_text(encoding="utf-8")
QUALIFIER = (ROOT / "scripts/frozen_sha_scanner_qualification.py").read_text(encoding="utf-8")


def test_qualification_is_frozen_to_the_merged_report_sha() -> None:
    assert pipeline.FROZEN_QUALIFICATION_SHA == "8ed545766fb4c5054798a02ea17ece0fe7bcab64"
    assert pipeline.FROZEN_QUALIFICATION_SHA in WORKFLOW
    assert "commit_sha != FROZEN_QUALIFICATION_SHA" in QUALIFIER


def test_disputed_scanners_are_required_twice() -> None:
    assert set(pipeline.CRITICAL_REPEATABILITY_TOOLS) == {
        "bandit",
        "eslint",
        "typescript",
        "gitleaks",
        "osv-scanner",
    }
    assert set(pipeline.CRITICAL_REPEATABILITY_TOOLS) <= set(pipeline.REQUIRED_TOOLS)
    source = (ROOT / "nico/frozen_sha_scanner_evidence_v1.py").read_text(encoding="utf-8")
    assert "pass_tools = (REQUIRED_TOOLS, CRITICAL_REPEATABILITY_TOOLS)" in source
    assert '"passes_required": 2' in source


def test_bandit_full_json_above_old_capture_limit_is_parsed(tmp_path: Path) -> None:
    output = tmp_path / "bandit.json"
    padding = "x" * (21 * 1024 * 1024)
    output.write_text(
        json.dumps(
            {
                "errors": [],
                "results": [
                    {
                        "filename": "nico/example.py",
                        "line_number": 1,
                        "issue_severity": "LOW",
                        "issue_confidence": "HIGH",
                        "issue_text": padding,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = WorkerCommandResult(
        args=("bandit",),
        returncode=1,
        stdout="truncated preview",
        stderr="",
        output_truncated=True,
        stdout_path=str(output),
        stdout_bytes=output.stat().st_size,
    )
    findings, complete, reason = pipeline._parse_tool_output("bandit", result, output)
    assert complete is True
    assert reason == ""
    assert len(findings) == 1
    assert findings[0]["filename"] == "nico/example.py"


def test_bandit_excludes_vendor_and_generated_trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: f"/usr/bin/{name}")
    command, cwd, _, _ = pipeline._command_for(
        pipeline.TOOL_SPECS["bandit"],
        workspace,
        {"node_modules_ready": True},
    )
    assert cwd == workspace.repo_dir
    assert command is not None
    exclusion = command[command.index("-x") + 1]
    assert "node_modules" in exclusion
    assert ".next" in exclusion
    assert ".git" in exclusion


def test_scanner_owned_eslint_does_not_require_client_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    web = workspace.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="/usr/local/lib/node_modules\n", stderr=""),
    )
    command, cwd, env, reason = pipeline._command_for(
        pipeline.TOOL_SPECS["eslint"],
        workspace,
        {"node_modules_ready": True},
    )
    assert reason == "The scanner-owned ESLint runtime is unavailable."
    assert command is not None
    assert cwd == web
    assert "--config" in command
    config = Path(command[command.index("--config") + 1])
    assert config.is_file()
    assert "@typescript-eslint/parser" in config.read_text(encoding="utf-8")
    assert "/usr/local/lib/node_modules" in env["NODE_PATH"]


def test_typescript_uses_exact_project_tsconfig_and_larger_heap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    web = workspace.repo_dir / "apps" / "web"
    binary = web / "node_modules" / ".bin" / "tsc"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    (web / "tsconfig.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="/usr/local/lib/node_modules\n", stderr=""),
    )
    command, cwd, env, _ = pipeline._command_for(
        pipeline.TOOL_SPECS["typescript"],
        workspace,
        {"node_modules_ready": True},
    )
    assert command is not None
    assert cwd == web
    assert "-p" in command
    assert command[command.index("-p") + 1] == str(web / "tsconfig.json")
    assert int(env["NODE_OPTIONS"].rsplit("=", 1)[1]) >= 2048


def test_osv_requires_complete_cli_source_scan_not_capped_api_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: f"/opt/tools/{name}")
    command, cwd, _, _ = pipeline._command_for(
        pipeline.TOOL_SPECS["osv-scanner"],
        workspace,
        {"node_modules_ready": True},
    )
    assert command == ("/opt/tools/osv-scanner", "scan", "source", "-r", ".", "--format", "json")
    assert cwd == workspace.repo_dir
    source = (ROOT / "nico/frozen_sha_scanner_evidence_v1.py").read_text(encoding="utf-8")
    assert "partial API fallback is not accepted" in source
    assert "dependencies[:150]" not in source


def test_exact_history_checkout_has_no_shallow_depth_flag() -> None:
    source = (ROOT / "nico/frozen_sha_scanner_evidence_v1.py").read_text(encoding="utf-8")
    clone_body = source.split("def clone_repository_at_exact_history", 1)[1].split("def _node_environment", 1)[0]
    assert '"--depth"' not in clone_body
    assert '"--is-shallow-repository"' in clone_body
    assert '"rev-list", "--count", "HEAD"' in clone_body


def test_retained_artifacts_are_checksummed_and_secret_safe(tmp_path: Path) -> None:
    sensitive_value = "not-a-real-secret-value-123456"
    source = tmp_path / "secret.json"
    source.write_text(json.dumps([{"Raw": sensitive_value, "Detector": "test"}]), encoding="utf-8")
    destination = tmp_path / "retained" / "gitleaks.stdout"
    metadata = pipeline._retain_text(source, destination, secret_output=True)
    retained = destination.read_text(encoding="utf-8")
    assert sensitive_value not in retained
    assert "[REDACTED]" in retained
    assert metadata["sha256"] == pipeline._sha256_file(destination)
    assert metadata["size_bytes"] == destination.stat().st_size


def test_strict_provider_blocks_failed_or_nonrepeatable_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SimpleNamespace()
    provider._snapshot = lambda context: {"status": "attached", "snapshot_id": "snap", "commit_sha": "a" * 40}
    provider._scan_id = lambda context: "scan_failed"
    provider._counts = lambda scan: {"raw": 0, "material": 0, "review": 0, "excluded": 0}
    provider._result = lambda context, status="complete", **payload: {"status": status, **payload}
    monkeypatch.setattr(
        pipeline.base,
        "get_scan",
        lambda scan_id: {
            "scan_id": scan_id,
            "status": "blocked",
            "snapshot_match": True,
            "required_tools_complete": False,
            "failed_tools": ["bandit"],
            "repeatability": {"status": "blocked"},
        },
        raising=False,
    )
    result = pipeline._strict_provider(provider)({
        "repository": "BoneManTGRM/NICO",
        "run_id": "run",
        "customer_id": "customer",
        "project_id": "project",
    })
    assert result["status"] == "blocked"
    assert result["reason"] == "required_scanner_evidence_incomplete_or_nonrepeatable"
    assert result["failed_tools"] == ["bandit"]


def test_bootstrap_installs_scanner_truth_before_provider_registration() -> None:
    install = BOOTSTRAP.index("install_frozen_sha_scanner_evidence_v1(provider_module)")
    providers = BOOTSTRAP.index("install_native_comprehensive_providers(target)")
    executors = BOOTSTRAP.index("build_production_capability_executors(target)")
    assert install < providers < executors
    assert 'scanner_evidence_pipeline.get("bound") is True' in BOOTSTRAP
    assert "Fail-closed frozen-SHA scanner evidence pipeline was not installed" in BOOTSTRAP


def test_workflow_retains_artifacts_and_fails_on_incomplete_evidence() -> None:
    assert "Two clean passes at 8ed5457" in WORKFLOW
    assert "NICO_SCANNER_MAX_RETAINED_OUTPUT_BYTES" in WORKFLOW
    assert "--artifact-root" in WORKFLOW
    assert "if-no-files-found: error" in WORKFLOW
    assert "retention-days: 90" in WORKFLOW
    assert 'payload["required_tools_complete"] is True' in WORKFLOW
    assert 'payload["repeatability"]["equivalent"] is True' in WORKFLOW
    assert "statuses: write" in WORKFLOW
    assert "NICO/Frozen SHA Scanner Qualification" in WORKFLOW
    assert "steps.upload.outcome" in WORKFLOW


def test_workflow_is_registered_for_every_qualification_implementation_change() -> None:
    for required_path in (
        '"nico/frozen_sha_scanner_evidence_v1.py"',
        '"nico/api/comprehensive_production_bootstrap.py"',
        '"scripts/frozen_sha_scanner_qualification.py"',
        '"tests/test_frozen_sha_scanner_evidence_v1.py"',
    ):
        assert required_path in WORKFLOW
    assert "pull_request:" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
