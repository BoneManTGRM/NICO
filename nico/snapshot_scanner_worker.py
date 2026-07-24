from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from nico import scanner_tool_runners as tool_runners
from nico import scanner_worker as base
from nico.storage import STORE
from nico.worker_execution import WorkerWorkspace

_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_EXCLUDED_PATH_PARTS = {"tests", "test", "fixtures", "fixture", "examples", "example", "samples", "sample"}
_VOLATILE_FINGERPRINT_KEYS = {
    "duration_seconds",
    "stderr_bytes",
    "stdout_bytes",
    "created_at",
    "updated_at",
    "completed_at",
    "diagnostic_id",
}


def _git(command: list[str], *, cwd: Path | None, env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        shell=False,
        check=False,
        start_new_session=True,
    )


def clone_repository_at_snapshot(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    """Fetch the exact commit and its complete ancestor history without later commits."""

    if shutil.which("git") is None:
        return None, "", ["git is unavailable in this worker image; snapshot-bound repository clone was skipped."]
    if not _COMMIT_SHA_RE.fullmatch(str(commit_sha or "")):
        return None, "", ["A valid full repository snapshot commit SHA is required before scanner execution."]

    repo_path = workspace / "repo"
    repo_path.mkdir(parents=True, exist_ok=False)
    commands = (
        (["git", "init", "--quiet", str(repo_path)], None),
        (["git", "remote", "add", "origin", base.safe_repo_url(repository)], repo_path),
        (
            [
                "git",
                "-c",
                "protocol.version=2",
                "fetch",
                "--filter=blob:none",
                "--no-tags",
                "origin",
                commit_sha,
            ],
            repo_path,
        ),
        (["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], repo_path),
    )
    for command, cwd in commands:
        completed = _git(command, cwd=cwd, env=env, timeout=300)
        preview, _ = base.redact((completed.stdout or "") + "\n" + (completed.stderr or ""))
        if completed.returncode != 0:
            shutil.rmtree(repo_path, ignore_errors=True)
            return None, "", [f"snapshot-bound git command failed ({' '.join(command[:3])}): {preview[:1000]}"]

    resolved = _git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
    actual_sha = (resolved.stdout or "").strip().lower()
    if resolved.returncode != 0 or actual_sha != commit_sha.lower():
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual_sha, ["Scanner checkout did not match the assessment snapshot commit; scanner execution was blocked."]

    shallow = _git(["git", "rev-parse", "--is-shallow-repository"], cwd=repo_path, env=env, timeout=30)
    if shallow.returncode != 0 or (shallow.stdout or "").strip().lower() != "false":
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual_sha, ["Exact-commit checkout was shallow; full-history secret scanning was blocked rather than overstated."]

    size = base.directory_size(repo_path)
    if size > base.MAX_REPO_BYTES:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual_sha, [f"repository exceeds max size limit: {size} bytes > {base.MAX_REPO_BYTES} bytes"]
    return repo_path, actual_sha, []


def _history_evidence(repo_path: Path, expected_sha: str, env: dict[str, str]) -> dict[str, Any]:
    head = _git(["git", "rev-parse", "HEAD"], cwd=repo_path, env=env, timeout=30)
    shallow = _git(["git", "rev-parse", "--is-shallow-repository"], cwd=repo_path, env=env, timeout=30)
    count = _git(["git", "rev-list", "--count", "HEAD"], cwd=repo_path, env=env, timeout=120)
    actual = (head.stdout or "").strip().lower()
    is_shallow = (shallow.stdout or "").strip().lower() != "false"
    try:
        commit_count = max(0, int((count.stdout or "0").strip()))
    except ValueError:
        commit_count = 0
    verified = bool(
        head.returncode == 0
        and shallow.returncode == 0
        and count.returncode == 0
        and actual == expected_sha.lower()
        and not is_shallow
        and commit_count >= 1
    )
    return {
        "full_history_verified": verified,
        "history_head_sha": actual,
        "history_commit_count": commit_count,
        "shallow_repository": is_shallow,
        "history_scope": "all ancestors reachable from the exact snapshot commit",
    }


def _requested_specs(payload: dict[str, Any]) -> list[tool_runners.ScannerToolSpec]:
    requested = [str(item or "").strip().lower() for item in payload.get("tools") or [] if str(item or "").strip()]
    by_name = {spec.name: spec for spec in tool_runners.TOOL_SPECS}
    names = requested or [
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    ]
    return [by_name[name] for name in names if name in by_name]


def _tool_name(item: dict[str, Any]) -> str:
    return str(item.get("tool") or item.get("scanner") or "unknown")


def _finding_path(finding: dict[str, Any]) -> str:
    return str(
        finding.get("file_path")
        or finding.get("filename")
        or finding.get("path")
        or finding.get("filePath")
        or ""
    ).replace("\\", "/")


def _test_or_example_path(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    filename = parts[-1] if parts else ""
    return bool(
        any(part in _EXCLUDED_PATH_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith("_test.py")
        or filename.endswith(".test.ts")
        or filename.endswith(".test.tsx")
        or filename.endswith(".spec.ts")
        or filename.endswith(".spec.tsx")
    )


def _severity(finding: dict[str, Any]) -> str:
    text = " ".join(
        str(value or "").lower()
        for value in (
            finding.get("severity"),
            finding.get("issue_severity"),
            finding.get("level"),
            finding.get("confidence"),
            (finding.get("extra") or {}).get("severity") if isinstance(finding.get("extra"), dict) else "",
            (finding.get("database_specific") or {}).get("severity") if isinstance(finding.get("database_specific"), dict) else "",
        )
    )
    if "critical" in text:
        return "critical"
    if "high" in text or "error" in text:
        return "high"
    if "medium" in text or "moderate" in text or "warning" in text:
        return "medium"
    if "low" in text or "info" in text:
        return "low"
    return "unknown"


def _tool_triage(item: dict[str, Any]) -> dict[str, int]:
    findings = [finding for finding in item.get("findings") or [] if isinstance(finding, dict)]
    tool = _tool_name(item)
    category = str(item.get("category") or "unknown")
    excluded_test_only = sum(1 for finding in findings if _test_or_example_path(_finding_path(finding)))
    production = [finding for finding in findings if not _test_or_example_path(_finding_path(finding))]

    if tool == "bandit" and isinstance(item.get("bandit_triage"), dict):
        triage = item["bandit_triage"]
        blocking = int(triage.get("blocking_count") or 0) + int(triage.get("unresolved_high_confidence_count") or 0)
        review = int(triage.get("needs_review_count") or 0)
        approved = int(triage.get("approved_count") or 0)
        return {
            "raw": len(findings),
            "material": max(0, blocking),
            "review_required": max(0, review),
            "approved_or_nonblocking": max(0, approved),
            "excluded_test_only": excluded_test_only,
        }

    high = sum(1 for finding in production if _severity(finding) in {"high", "critical"})
    medium = sum(1 for finding in production if _severity(finding) == "medium")
    if category == "secret":
        verified = sum(1 for finding in production if bool(finding.get("Verified") or finding.get("verified")))
        return {
            "raw": len(findings),
            "material": verified,
            "review_required": max(0, len(production) - verified),
            "approved_or_nonblocking": 0,
            "excluded_test_only": excluded_test_only,
        }
    if category == "dependency":
        return {
            "raw": len(findings),
            "material": high,
            "review_required": max(0, len(production) - high),
            "approved_or_nonblocking": 0,
            "excluded_test_only": excluded_test_only,
        }
    return {
        "raw": len(findings),
        "material": high,
        "review_required": medium + sum(1 for finding in production if _severity(finding) in {"low", "unknown"}),
        "approved_or_nonblocking": 0,
        "excluded_test_only": excluded_test_only,
    }


def _finding_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, Counter[str]] = {}
    by_tool: dict[str, dict[str, int]] = {}
    for item in results:
        tool = _tool_name(item)
        category = str(item.get("category") or "unknown")
        triage = _tool_triage(item)
        by_tool[tool] = triage
        counts = by_category.setdefault(category, Counter())
        for key, value in triage.items():
            counts[key] += value
    category_payload = {category: dict(sorted(counts.items())) for category, counts in sorted(by_category.items())}
    return {
        "raw_total": sum(item.get("raw", 0) for item in by_tool.values()),
        "material_total": sum(item.get("material", 0) for item in by_tool.values()),
        "review_required_total": sum(item.get("review_required", 0) for item in by_tool.values()),
        "approved_or_nonblocking_total": sum(item.get("approved_or_nonblocking", 0) for item in by_tool.values()),
        "excluded_test_only_total": sum(item.get("excluded_test_only", 0) for item in by_tool.values()),
        "by_tool": dict(sorted(by_tool.items())),
        "by_category": category_payload,
        "truth_model": "material_confirmed_or_high_severity_only; review and test-only findings disclosed separately",
    }


def _canonical(value: Any, repo_path: Path) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical(item, repo_path)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_FINGERPRINT_KEYS
        }
    if isinstance(value, list):
        normalized = [_canonical(item, repo_path) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, str):
        return value.replace(str(repo_path), "<repo>").replace("\\", "/")
    return value


def _result_fingerprint(results: list[dict[str, Any]], repo_path: Path) -> str:
    payload = [
        _canonical(
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "returncode": item.get("returncode"),
                "output_capture_complete": item.get("output_capture_complete"),
                "full_history_verified": item.get("full_history_verified"),
                "findings": item.get("findings") or [],
                "reason": item.get("reason") or "",
            },
            repo_path,
        )
        for item in results
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _repeatability_evidence(
    *,
    scan_id: str,
    customer_id: str,
    project_id: str,
    repository: str,
    commit_sha: str,
    tools_requested: list[str],
    fingerprint: str,
) -> dict[str, Any]:
    previous = []
    for item in STORE.list("scanner_runs", customer_id=customer_id, project_id=project_id):
        if str(item.get("scan_id") or item.get("id") or "") == scan_id:
            continue
        if str(item.get("repository") or "").lower() != repository.lower():
            continue
        if str(item.get("snapshot_commit_sha") or "").lower() != commit_sha.lower():
            continue
        if list(item.get("tools_requested") or []) != tools_requested:
            continue
        prior_fingerprint = str(item.get("scanner_result_fingerprint") or "")
        if prior_fingerprint:
            previous.append((str(item.get("scan_id") or item.get("id") or ""), prior_fingerprint))
    matches = [prior_id for prior_id, prior_fingerprint in previous if prior_fingerprint == fingerprint]
    if matches:
        status = "verified"
    elif previous:
        status = "mismatch"
    else:
        status = "single_run"
    return {
        "status": status,
        "same_sha_required": True,
        "fingerprint": fingerprint,
        "prior_comparison_count": len(previous),
        "matching_prior_scan_id": matches[-1] if matches else "",
        "two_matching_runs": bool(matches),
    }


def _run_snapshot_scan(scan_id: str, payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer_id") or "default_customer"
    project_id = payload.get("project_id") or "default_project"
    base.SCAN_JOBS[scan_id]["status"] = "running"
    base.SCAN_JOBS[scan_id]["current_stage"] = "snapshot_checkout"
    base.SCAN_JOBS[scan_id]["progress_percent"] = 10
    base.SCAN_JOBS[scan_id]["updated_at"] = base.now_iso()
    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])

    results: list[dict[str, Any]] = []
    unavailable_notes: list[str] = []
    redaction_applied = False
    repo_size = 0
    actual_commit_sha = ""
    specs = _requested_specs(payload)
    started = time.monotonic()
    history_evidence: dict[str, Any] = {
        "full_history_verified": False,
        "history_head_sha": "",
        "history_commit_count": 0,
        "shallow_repository": True,
        "history_scope": "unavailable",
    }
    preparation: tool_runners.ProjectCommandPreparation | None = None
    fingerprint = ""
    repeatability: dict[str, Any] = {"status": "unavailable", "two_matching_runs": False}

    with tempfile.TemporaryDirectory(prefix="nico-snapshot-scan-") as workspace_name:
        workspace_root = Path(workspace_name)
        env = base.clean_env(workspace_root)
        repo_path: Path | None = None
        try:
            repo_path, actual_commit_sha, clone_notes = clone_repository_at_snapshot(
                str(payload.get("repository") or ""),
                str(payload.get("snapshot_commit_sha") or ""),
                workspace_root,
                env,
            )
            unavailable_notes.extend(clone_notes)
            if repo_path:
                repo_size = base.directory_size(repo_path)
                history_evidence = _history_evidence(repo_path, str(payload.get("snapshot_commit_sha") or ""), env)
                workspace = WorkerWorkspace(root=workspace_root)
                if any(spec.requires_project_commands for spec in specs) and tool_runners.project_commands_allowed():
                    base.SCAN_JOBS[scan_id]["current_stage"] = "project_dependency_preparation"
                    base.SCAN_JOBS[scan_id]["progress_percent"] = 18
                    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])
                    preparation = tool_runners.prepare_project_commands(workspace)
                base.SCAN_JOBS[scan_id]["current_stage"] = "scanner_suite"
                base.SCAN_JOBS[scan_id]["progress_percent"] = 20
                STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])
                for index, spec in enumerate(specs, start=1):
                    base.SCAN_JOBS[scan_id]["active_tool"] = spec.name
                    base.SCAN_JOBS[scan_id]["progress_percent"] = 20 + round((index - 1) / max(1, len(specs)) * 70)
                    base.SCAN_JOBS[scan_id]["updated_at"] = base.now_iso()
                    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])
                    try:
                        result = tool_runners.run_scanner_tool(spec, workspace, preparation=preparation)
                    except Exception as exc:  # pragma: no cover - defensive per-tool boundary
                        result = {
                            "tool": spec.name,
                            "status": "failed",
                            "category": spec.category,
                            "reason": f"{spec.name} failed safely inside the snapshot worker: {type(exc).__name__}",
                            "findings": [],
                            "verified_for_this_report": False,
                            "current_run": True,
                            "scans_git_history": spec.scans_git_history,
                        }
                    if spec.scans_git_history:
                        result.update(history_evidence)
                        if not history_evidence.get("full_history_verified") and result.get("status") == "completed":
                            result["status"] = "failed"
                            result["verified_for_this_report"] = False
                            result["reason"] = "The tool completed, but full Git history through the exact snapshot commit was not verified."
                    redaction_applied = redaction_applied or "[REDACTED]" in str(result)
                    results.append(result)
                fingerprint = _result_fingerprint(results, repo_path)
                repeatability = _repeatability_evidence(
                    scan_id=scan_id,
                    customer_id=str(customer_id),
                    project_id=str(project_id),
                    repository=str(payload.get("repository") or ""),
                    commit_sha=str(payload.get("snapshot_commit_sha") or ""),
                    tools_requested=[spec.name for spec in specs],
                    fingerprint=fingerprint,
                )
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            unavailable_notes.append(f"Snapshot-bound worker failed safely: {type(exc).__name__}")

    unavailable = [_tool_name(item) for item in results if item.get("status") == "unavailable"]
    failed = [_tool_name(item) for item in results if item.get("status") in {"failed", "error"}]
    timed_out = [_tool_name(item) for item in results if item.get("status") == "timeout"]
    completed = [_tool_name(item) for item in results if item.get("status") == "completed"]
    snapshot_match = bool(actual_commit_sha) and actual_commit_sha == str(payload.get("snapshot_commit_sha") or "").lower()
    summary = _finding_summary(results)
    history_tools = [
        _tool_name(item)
        for item in results
        if item.get("scans_git_history") and item.get("status") == "completed" and item.get("full_history_verified") is True
    ]
    project_preparation = {
        "status": preparation.status,
        "node_modules_ready": preparation.node_modules_ready,
        "reason": preparation.reason,
        "returncode": preparation.returncode,
        "timed_out": preparation.timed_out,
        "output_truncated": preparation.output_truncated,
    } if preparation else {"status": "not_required", "node_modules_ready": False}
    base.SCAN_JOBS[scan_id].update(
        {
            "status": "complete" if snapshot_match else "unavailable",
            "current_stage": "complete" if snapshot_match else "snapshot_verification_failed",
            "progress_percent": 100,
            "updated_at": base.now_iso(),
            "completed_at": base.now_iso(),
            "duration_seconds": round(time.monotonic() - started, 2),
            "run_id": payload.get("run_id") or base.SCAN_JOBS[scan_id].get("run_id") or "",
            "snapshot_id": payload.get("snapshot_id") or "",
            "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
            "actual_commit_sha": actual_commit_sha,
            "snapshot_match": snapshot_match,
            "tools_requested": [spec.name for spec in specs],
            "tools_run": completed,
            "unavailable_tools": unavailable,
            "failed_tools": failed,
            "timed_out_tools": timed_out,
            "full_history_verified_tools": history_tools,
            "history_evidence": history_evidence,
            "project_preparation": project_preparation,
            "scanner_results": results,
            "scanner_result_fingerprint": fingerprint,
            "repeatability": repeatability,
            "finding_summary": summary,
            "finding_count": summary["raw_total"],
            "material_finding_count": summary["material_total"],
            "review_required_finding_count": summary["review_required_total"],
            "excluded_test_only_finding_count": summary["excluded_test_only_total"],
            "evidence_summary": {
                "mode": "snapshot_bound_modern_scanner_worker_v2",
                "repository": payload.get("repository"),
                "run_id": payload.get("run_id") or base.SCAN_JOBS[scan_id].get("run_id") or "",
                "snapshot_id": payload.get("snapshot_id") or "",
                "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
                "actual_commit_sha": actual_commit_sha,
                "snapshot_match": snapshot_match,
                "repo_size_bytes": repo_size,
                "tools_requested": len(specs),
                "tools_run": len(completed),
                "unavailable_tools": len(unavailable),
                "failed_tools": len(failed),
                "timed_out_tools": len(timed_out),
                "full_history_verified_tools": history_tools,
                "history_evidence": history_evidence,
                "project_preparation": project_preparation,
                "scanner_result_fingerprint": fingerprint,
                "repeatability": repeatability,
                "finding_summary": summary,
            },
            "unavailable_data_notes": unavailable_notes,
            "secret_redaction_applied": redaction_applied,
            "redaction_policy_applied": True,
            "retention_note": "Temporary snapshot-bound scan workspace was deleted after completion.",
            "human_review_required": True,
            "code_modification_allowed": False,
            "draft_pr_creation_allowed": False,
        }
    )
    STORE.put("scanner_runs", scan_id, base.SCAN_JOBS[scan_id])
    STORE.audit(
        "scanner.snapshot_completed",
        {
            "scan_id": scan_id,
            "status": base.SCAN_JOBS[scan_id]["status"],
            "snapshot_id": payload.get("snapshot_id") or "",
            "snapshot_commit_sha": payload.get("snapshot_commit_sha") or "",
            "actual_commit_sha": actual_commit_sha,
            "snapshot_match": snapshot_match,
            "tools_run": completed,
            "failed_tools": failed,
            "timed_out_tools": timed_out,
            "full_history_verified_tools": history_tools,
            "scanner_result_fingerprint": fingerprint,
            "repeatability_status": repeatability.get("status"),
            "material_finding_count": summary["material_total"],
            "review_required_finding_count": summary["review_required_total"],
            "excluded_test_only_finding_count": summary["excluded_test_only_total"],
        },
        customer_id=customer_id,
        project_id=project_id,
    )


def start_snapshot_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before snapshot-bound scanner execution."}
    repository = str(payload.get("repository") or "")
    commit_sha = str(payload.get("snapshot_commit_sha") or "").lower()
    snapshot_id = str(payload.get("snapshot_id") or "")
    if not repository:
        return {"status": "blocked", "error": "repository is required."}
    if not snapshot_id or not _COMMIT_SHA_RE.fullmatch(commit_sha):
        return {"status": "blocked", "error": "A captured repository snapshot ID and full commit SHA are required."}
    if not str(payload.get("authorized_by") or "").strip() or str(payload.get("authorized_by")).strip().lower() == "unspecified":
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        base.safe_repo_url(repository)
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    specs = _requested_specs(payload)
    scan_id = f"scan_snapshot_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "run_id": payload.get("run_id") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": repository,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": commit_sha,
        "actual_commit_sha": "",
        "snapshot_match": False,
        "status": "queued",
        "current_stage": "queued",
        "progress_percent": 2,
        "created_at": base.now_iso(),
        "updated_at": base.now_iso(),
        "authorized_by": payload.get("authorized_by"),
        "authorization_scope": payload.get("authorization_scope"),
        "code_modification_allowed": False,
        "draft_pr_creation_allowed": False,
        "tools_requested": [spec.name for spec in specs],
        "tools_run": [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "full_history_verified_tools": [],
        "scanner_result_fingerprint": "",
        "repeatability": {"status": "pending", "two_matching_runs": False},
        "finding_summary": {
            "raw_total": 0,
            "material_total": 0,
            "review_required_total": 0,
            "approved_or_nonblocking_total": 0,
            "excluded_test_only_total": 0,
            "by_tool": {},
            "by_category": {},
        },
        "max_repo_bytes": base.MAX_REPO_BYTES,
        "human_review_required": True,
    }
    base.SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit(
        "scanner.snapshot_queued",
        {
            "scan_id": scan_id,
            "run_id": job.get("run_id"),
            "repository": repository,
            "snapshot_id": snapshot_id,
            "snapshot_commit_sha": commit_sha,
            "tools_requested": job["tools_requested"],
        },
        customer_id=job["customer_id"],
        project_id=job["project_id"],
    )
    threading.Thread(target=_run_snapshot_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job


__all__ = [
    "clone_repository_at_snapshot",
    "start_snapshot_scan",
]
