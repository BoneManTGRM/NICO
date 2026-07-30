from __future__ import annotations

from pathlib import Path

import nico.scanner_evidence_contract_v2 as contract
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _result(args: tuple[str, ...], returncode: int, stdout: str = "") -> WorkerCommandResult:
    return WorkerCommandResult(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def test_git_history_evidence_rejects_shallow_checkout(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)

    def fake_run(args, **kwargs):
        if tuple(args)[1:3] == ("rev-parse", "--is-shallow-repository"):
            return _result(tuple(args), 0, "true\n")
        return _result(tuple(args), 0)

    monkeypatch.setattr(contract, "run_command", fake_run)
    evidence = contract._git_history_evidence(workspace)
    assert evidence["verified"] is False
    assert evidence["shallow"] is True
    assert evidence["source"] == "local_git_probe"
    assert "shallow" in evidence["reason"]


def test_git_history_evidence_accepts_complete_head(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)

    def fake_run(args, **kwargs):
        if tuple(args)[1:3] == ("rev-parse", "--is-shallow-repository"):
            return _result(tuple(args), 0, "false\n")
        return _result(tuple(args), 0)

    monkeypatch.setattr(contract, "run_command", fake_run)
    evidence = contract._git_history_evidence(workspace)
    assert evidence == {
        "verified": True,
        "reason": "",
        "shallow": False,
        "head_verified": True,
        "source": "local_git_probe",
    }


def test_history_scanner_is_downgraded_without_full_history(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)
    spec = ScannerToolSpec(
        "gitleaks",
        ("gitleaks", "detect"),
        "secret",
        scans_git_history=True,
    )

    monkeypatch.setattr(
        contract,
        "_ORIGINAL_RUN_SCANNER_TOOL",
        lambda *args, **kwargs: {
            "tool": "gitleaks",
            "status": "completed",
            "findings": [],
            "output_capture_complete": True,
            "output_truncated": False,
            "verified_for_this_report": True,
        },
    )
    monkeypatch.setattr(
        contract,
        "_git_history_evidence",
        lambda workspace: {
            "verified": False,
            "reason": "repository checkout is shallow",
            "shallow": True,
            "head_verified": True,
            "source": "local_git_probe",
        },
    )

    result = contract._run_scanner_tool(spec, workspace)
    assert result["status"] == "partial"
    assert result["verified_for_this_report"] is False
    assert result["full_history_verified"] is False
    assert result["verified_complete"] is False
    assert result["artifact_hash"] == result["deterministic_fingerprint"]
    assert len(result["artifact_hash"]) == 64


def test_redundant_upstream_history_proof_is_preserved(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)
    spec = ScannerToolSpec(
        "trufflehog",
        ("trufflehog", "git", "file://{repo_dir}"),
        "secret",
        scans_git_history=True,
    )

    monkeypatch.setattr(
        contract,
        "_ORIGINAL_RUN_SCANNER_TOOL",
        lambda *args, **kwargs: {
            "tool": "trufflehog",
            "status": "completed",
            "findings": [],
            "output_capture_complete": True,
            "output_truncated": False,
            "verified_for_this_report": True,
            "full_history_verified": True,
            "history_depth_verified": True,
            "history_depth": "full",
            "history_scope": "full_git_history",
            "history_verification_note": "verified full history",
        },
    )

    def fail_if_reprobed(_workspace):
        raise AssertionError("redundant upstream proof should avoid a second local probe")

    monkeypatch.setattr(contract, "_git_history_evidence", fail_if_reprobed)
    result = contract._run_scanner_tool(spec, workspace)

    assert result["status"] == "completed"
    assert result["full_history_verified"] is True
    assert result["history_depth_verified"] is True
    assert result["history_verification_source"] == "upstream_scanner_history_truth_guard"
    assert result["verified_complete"] is True


def test_lone_upstream_history_flag_is_not_trusted() -> None:
    assert contract._trusted_upstream_history_evidence({"full_history_verified": True}) is None


def test_completed_scanner_requires_complete_capture(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)
    spec = ScannerToolSpec("bandit", ("bandit", "-r", "."), "static")

    monkeypatch.setattr(
        contract,
        "_ORIGINAL_RUN_SCANNER_TOOL",
        lambda *args, **kwargs: {
            "tool": "bandit",
            "status": "completed",
            "findings": [],
            "output_capture_complete": False,
            "output_truncated": True,
            "verified_for_this_report": True,
        },
    )

    result = contract._run_scanner_tool(spec, workspace)
    assert result["raw_artifact_retention_complete"] is False
    assert result["verified_complete"] is False
    assert result["full_history_verified"] is False


def test_legacy_scanner_wrapper_without_preparation_keyword_remains_supported(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    workspace = WorkerWorkspace(root=tmp_path)
    spec = ScannerToolSpec("eslint", ("eslint", "."), "static", requires_project_commands=True)
    observed: dict[str, object] = {}

    def legacy_wrapper(spec, workspace, *, runner):
        observed["runner"] = runner
        return {
            "tool": spec.name,
            "status": "completed",
            "findings": [],
            "output_capture_complete": True,
            "output_truncated": False,
            "verified_for_this_report": True,
        }

    monkeypatch.setattr(contract, "_ORIGINAL_RUN_SCANNER_TOOL", legacy_wrapper)
    result = contract._run_scanner_tool(spec, workspace, preparation=None)

    assert observed["runner"] is contract.run_command
    assert result["status"] == "completed"
    assert result["verified_complete"] is True
    assert result["scanner_evidence_contract_version"] == contract.VERSION
