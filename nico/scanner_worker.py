from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from nico.storage import STORE


SHELL_EXECUTION_ALLOWED = False
ENABLE_SCANNER_EXECUTION = os.getenv("NICO_ENABLE_SCANNER_EXECUTION", "true").lower() == "true"
ALLOW_PROJECT_COMMANDS = os.getenv("NICO_ALLOW_PROJECT_COMMANDS", "false").lower() == "true"
MAX_OUTPUT_CHARS = int(os.getenv("NICO_MAX_TOOL_OUTPUT", "12000"))
DEFAULT_TOOL_TIMEOUT_SECONDS = int(os.getenv("NICO_TOOL_TIMEOUT_SECONDS", "45"))
TOTAL_SCAN_TIMEOUT_SECONDS = int(os.getenv("NICO_TOTAL_SCAN_TIMEOUT_SECONDS", "300"))
MAX_REPO_BYTES = int(os.getenv("NICO_MAX_REPO_BYTES", "150000000"))

TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "pip-audit": {"binary": "pip-audit", "intent": "Python dependency review", "tier": "dependency"},
    "npm-audit": {"binary": "npm", "intent": "Node dependency review", "tier": "dependency"},
    "osv-scanner": {"binary": "osv-scanner", "intent": "OSV dependency review", "tier": "dependency"},
    "semgrep": {"binary": "semgrep", "intent": "static analysis", "tier": "static"},
    "bandit": {"binary": "bandit", "intent": "Python static review", "tier": "static"},
    "eslint": {"binary": "eslint", "intent": "JavaScript and TypeScript linting", "tier": "project_command"},
    "pytest": {"binary": "pytest", "intent": "Python test run", "tier": "project_command"},
    "npm-test": {"binary": "npm", "intent": "Node test run", "tier": "project_command"},
    "npm-build": {"binary": "npm", "intent": "Node production build", "tier": "project_command"},
}

SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
SCAN_JOBS: dict[str, dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact(text: str) -> tuple[str, bool]:
    safe = text or ""
    changed = False
    for pattern in SECRET_PATTERNS:
        safe, count = pattern.subn("[REDACTED]", safe)
        changed = changed or bool(count)
    return safe[:MAX_OUTPUT_CHARS], changed


def selected_tools(requested_tools: list[str] | None) -> dict[str, dict[str, Any]]:
    if not requested_tools:
        return TOOL_CATALOG
    selected = {name: cfg for name, cfg in TOOL_CATALOG.items() if name in requested_tools}
    return selected or TOOL_CATALOG


def safe_repo_url(repository: str) -> str:
    value = (repository or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        return f"https://github.com/{value}.git"
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc.lower() == "github.com" and parsed.path.count("/") >= 2:
        path = parsed.path.rstrip("/")
        return value if path.endswith(".git") else f"https://github.com{path}.git"
    raise ValueError("repository must be owner/name or an https://github.com/owner/repo URL")


def clean_env(home: Path) -> dict[str, str]:
    return {"PATH": os.getenv("PATH", ""), "HOME": str(home), "TMPDIR": str(home), "PYTHONUNBUFFERED": "1"}


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
            if total > MAX_REPO_BYTES:
                break
    return total


def command_for_tool(name: str, repo_path: Path) -> tuple[list[str] | None, Path, list[str]]:
    notes: list[str] = []
    if name == "pip-audit":
        req = repo_path / "requirements.txt"
        if not req.exists():
            return None, repo_path, ["requirements.txt not found; pip-audit repository mode unavailable."]
        return ["pip-audit", "-r", str(req), "-f", "json"], repo_path, notes
    if name == "npm-audit":
        lockfiles = list(repo_path.glob("package-lock.json")) + list(repo_path.glob("*/package-lock.json")) + list(repo_path.glob("*/*/package-lock.json"))
        if not lockfiles:
            return None, repo_path, ["package-lock.json not found; npm audit unavailable without installing dependencies."]
        return ["npm", "audit", "--json", "--package-lock-only", "--ignore-scripts"], lockfiles[0].parent, notes
    if name == "osv-scanner":
        return ["osv-scanner", "--format", "json", str(repo_path)], repo_path, notes
    if name == "semgrep":
        return ["semgrep", "scan", "--json", "--config", "auto", str(repo_path)], repo_path, notes
    if name == "bandit":
        if not list(repo_path.rglob("*.py")):
            return None, repo_path, ["No Python files found for bandit."]
        return ["bandit", "-r", str(repo_path), "-f", "json"], repo_path, notes
    if name == "eslint":
        return ["eslint", ".", "--format", "json"], repo_path, notes
    if name == "pytest":
        return ["pytest", "-q"], repo_path, notes
    if name == "npm-test":
        return ["npm", "test", "--", "--watch=false"], repo_path, notes
    if name == "npm-build":
        return ["npm", "run", "build"], repo_path, notes
    return None, repo_path, [f"Unknown scanner: {name}"]


def unavailable_result(name: str, cfg: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    return {
        "scanner": name,
        "command_intent": cfg.get("intent", name),
        "status": "unavailable",
        "exit_code": None,
        "duration_seconds": 0,
        "evidence_summary": f"{name} was not executed.",
        "safe_output_preview": "",
        "risk_severity": "unknown",
        "recommended_repair": "Install/enable the scanner or provide the required manifest, then rerun in an isolated worker.",
        "unavailable_data_notes": notes,
    }


def run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not ENABLE_SCANNER_EXECUTION:
        return unavailable_result(name, cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if cfg.get("tier") == "project_command" and not ALLOW_PROJECT_COMMANDS:
        return unavailable_result(name, cfg, ["Project code/test/build commands require NICO_ALLOW_PROJECT_COMMANDS=true and stronger isolation."])
    if shutil.which(cfg["binary"]) is None:
        return unavailable_result(name, cfg, [f"{cfg['binary']} is not installed in this worker image."])
    command, cwd, notes = command_for_tool(name, repo_path)
    if not command:
        return unavailable_result(name, cfg, notes)
    remaining = max(1, min(DEFAULT_TOOL_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            shell=False,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            preview, redacted = redact((stdout or "") + "\n" + (stderr or ""))
            return {
                "scanner": name,
                "command_intent": cfg.get("intent", name),
                "status": "timeout",
                "exit_code": None,
                "duration_seconds": round(time.monotonic() - start, 2),
                "evidence_summary": f"{name} timed out after {remaining} seconds.",
                "safe_output_preview": preview,
                "risk_severity": "unknown",
                "recommended_repair": "Increase worker resources or narrow the scan scope after human review.",
                "unavailable_data_notes": ["Tool timed out."],
                "secret_redaction_applied": redacted,
            }
        preview, redacted = redact((stdout or "") + "\n" + (stderr or ""))
        status = "passed" if process.returncode == 0 else "failed"
        severity = "high" if re.search(r"(?i)critical|high", preview) else "medium" if status == "failed" else "low"
        return {
            "scanner": name,
            "command_intent": cfg.get("intent", name),
            "status": status,
            "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - start, 2),
            "evidence_summary": preview[:1200] or f"{name} completed with no output.",
            "safe_output_preview": preview,
            "risk_severity": severity,
            "recommended_repair": "Review scanner evidence, prioritize high-severity items, and create approval-gated repair suggestions.",
            "unavailable_data_notes": notes,
            "secret_redaction_applied": redacted,
        }
    except Exception as exc:
        return {
            "scanner": name,
            "command_intent": cfg.get("intent", name),
            "status": "error",
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - start, 2),
            "evidence_summary": f"{name} failed safely: {exc}",
            "safe_output_preview": "",
            "risk_severity": "unknown",
            "recommended_repair": "Review worker configuration and rerun only after the environment is fixed.",
            "unavailable_data_notes": [str(exc)],
            "secret_redaction_applied": False,
        }

def clone_repository(repository: str, workspace: Path, env: dict[str, str]) -> tuple[Path | None, list[str]]:
    if shutil.which("git") is None:
        return None, ["git is unavailable in this worker image; repository clone skipped."]
    repo_path = workspace / "repo"
    command = ["git", "clone", "--depth", "1", safe_repo_url(repository), str(repo_path)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90, env=env, shell=False, check=False)
    preview, _ = redact((completed.stdout or "") + "\n" + (completed.stderr or ""))
    if completed.returncode != 0:
        return None, [f"git clone failed: {preview[:1000]}"]
    size = directory_size(repo_path)
    if size > MAX_REPO_BYTES:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, [f"repository exceeds max size limit: {size} bytes > {MAX_REPO_BYTES} bytes"]
    return repo_path, []


def _run_scan(scan_id: str, payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer_id") or "default_customer"
    project_id = payload.get("project_id") or "default_project"
    SCAN_JOBS[scan_id]["status"] = "running"
    SCAN_JOBS[scan_id]["updated_at"] = now_iso()
    STORE.put("scanner_runs", scan_id, SCAN_JOBS[scan_id])

    results: list[dict[str, Any]] = []
    unavailable_notes: list[str] = []
    redaction_applied = False
    repo_size = 0
    deadline = time.monotonic() + TOTAL_SCAN_TIMEOUT_SECONDS

    with tempfile.TemporaryDirectory(prefix="nico-scan-") as workspace_name:
        workspace = Path(workspace_name)
        env = clean_env(workspace)
        try:
            repo_path, clone_notes = clone_repository(payload.get("repository", ""), workspace, env)
            unavailable_notes.extend(clone_notes)
            if repo_path:
                repo_size = directory_size(repo_path)
                for name, cfg in selected_tools(payload.get("tools") or []).items():
                    if time.monotonic() >= deadline:
                        results.append(unavailable_result(name, cfg, ["Total scan timeout reached before this scanner ran."]))
                        continue
                    result = run_tool(name, cfg, repo_path, env, deadline)
                    redaction_applied = redaction_applied or bool(result.get("secret_redaction_applied"))
                    results.append(result)
        except Exception as exc:
            unavailable_notes.append(f"Worker failed safely: {exc}")

    unavailable = [item["scanner"] for item in results if item.get("status") == "unavailable"]
    failed = [item["scanner"] for item in results if item.get("status") in {"failed", "error"}]
    timed_out = [item["scanner"] for item in results if item.get("status") == "timeout"]
    SCAN_JOBS[scan_id].update({
        "status": "complete" if results or unavailable_notes else "failed",
        "updated_at": now_iso(),
        "completed_at": now_iso(),
        "run_id": payload.get("run_id") or SCAN_JOBS[scan_id].get("run_id") or "",
        "tools_requested": list(selected_tools(payload.get("tools") or []).keys()),
        "tools_run": [item["scanner"] for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}],
        "unavailable_tools": unavailable,
        "failed_tools": failed,
        "timed_out_tools": timed_out,
        "scanner_results": results,
        "evidence_summary": {
            "mode": "controlled_scanner_worker",
            "repository": payload.get("repository"),
            "run_id": payload.get("run_id") or SCAN_JOBS[scan_id].get("run_id") or "",
            "repo_size_bytes": repo_size,
            "tools_requested": len(selected_tools(payload.get("tools") or [])),
            "tools_run": len([item for item in results if item.get("status") in {"passed", "failed", "timeout", "error"}]),
            "unavailable_tools": len(unavailable),
            "failed_tools": len(failed),
            "timed_out_tools": len(timed_out),
        },
        "unavailable_data_notes": unavailable_notes,
        "secret_redaction_applied": redaction_applied,
        "retention_note": "Temporary scan workspace was deleted after completion.",
        "human_review_required": True,
    })
    STORE.put("scanner_runs", scan_id, SCAN_JOBS[scan_id])
    STORE.audit("scanner.completed", {"scan_id": scan_id, "status": SCAN_JOBS[scan_id]["status"]}, customer_id=customer_id, project_id=project_id)


def start_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before scanner worker runs."}
    if not payload.get("repository"):
        return {"status": "blocked", "error": "repository is required."}
    if not str(payload.get("authorized_by") or "").strip() or str(payload.get("authorized_by")).strip().lower() == "unspecified":
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        safe_repo_url(payload.get("repository", ""))
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    scan_id = f"scan_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "run_id": payload.get("run_id") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": payload.get("repository"),
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "authorized_by": payload.get("authorized_by"),
        "authorization_scope": payload.get("authorization_scope"),
        "code_modification_allowed": False,
        "draft_pr_creation_allowed": bool(payload.get("draft_pr_creation_allowed", False)),
        "tools_requested": list(selected_tools(payload.get("tools") or []).keys()),
        "tools_run": [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "max_repo_bytes": MAX_REPO_BYTES,
        "tool_timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
        "total_scan_timeout_seconds": TOTAL_SCAN_TIMEOUT_SECONDS,
        "max_output_chars": MAX_OUTPUT_CHARS,
        "human_review_required": True,
    }
    SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit("scanner.queued", {"scan_id": scan_id, "run_id": job.get("run_id"), "repository": payload.get("repository")}, customer_id=job["customer_id"], project_id=job["project_id"])
    threading.Thread(target=_run_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job


def get_scan(scan_id: str) -> dict[str, Any]:
    return SCAN_JOBS.get(scan_id) or STORE.get("scanner_runs", scan_id) or {"status": "not_found", "scan_id": scan_id}
