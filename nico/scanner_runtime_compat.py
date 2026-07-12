from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import nico.exact_snapshot_secret_history as history
import nico.full_assessment_scorecard as scorecard
import nico.scanner_worker as scanner_worker


SCANNER_RUNTIME_COMPAT_VERSION = "nico-scanner-runtime-compat-v1"
OSV_TIMEOUT_SECONDS = int(os.getenv("NICO_OSV_TIMEOUT_SECONDS", "120"))
HISTORY_TIMEOUT_SECONDS = int(os.getenv("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", "120"))
_COMPAT_TOOLS = {"osv-scanner", "gitleaks", "trufflehog"}
_DELEGATE_RUN_TOOL: Callable[..., dict[str, Any]] | None = None
_DEPENDENCY_SECTION_DELEGATE: Callable[..., dict[str, Any]] | None = None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def _json_payload(value: str) -> tuple[Any, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, "Scanner completed without machine-readable JSON output."
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if starts:
            try:
                return json.loads(text[min(starts) :]), None
            except json.JSONDecodeError:
                pass
    return None, "Scanner output could not be parsed as JSON."


def _osv_finding_fingerprints(payload: Any) -> set[str]:
    fingerprints: set[str] = set()

    def visit(value: Any, path: str = "root") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in {"vulnerabilities", "vulns"} and isinstance(child, list):
                    for index, finding in enumerate(child):
                        if isinstance(finding, dict):
                            database_specific = _dict(finding.get("database_specific"))
                            identifier = str(finding.get("id") or database_specific.get("id") or "")
                            material = identifier or json.dumps(finding, sort_keys=True, default=str)
                        else:
                            material = str(finding)
                        digest = hashlib.sha256(f"{path}:{index}:{material}".encode("utf-8", errors="replace")).hexdigest()[:20]
                        fingerprints.add(digest)
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload)
    return fingerprints


def _remaining(deadline: float, limit: int) -> int:
    return max(1, min(limit, int(deadline - time.monotonic())))


def _communicate(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> tuple[int | None, str, str, float, bool]:
    started = time.monotonic()
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
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout or "", stderr or "", round(time.monotonic() - started, 2), False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return None, stdout or "", stderr or "", round(time.monotonic() - started, 2), True


def _osv_commands(repo_path: Path) -> list[tuple[str, list[str]]]:
    return [
        (
            "v2",
            [
                "osv-scanner",
                "scan",
                "source",
                "--format=json",
                "--verbosity=error",
                "--recursive",
                str(repo_path),
            ],
        ),
        (
            "v1-fallback",
            ["osv-scanner", "--format=json", "--recursive", str(repo_path)],
        ),
    ]


def _cli_mismatch(stderr: str) -> bool:
    value = str(stderr or "").lower()
    return any(marker in value for marker in ("unknown command", "unknown flag", "unrecognized option", "invalid command", "usage:"))


def _run_osv(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result("osv-scanner", cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if shutil.which("osv-scanner") is None:
        return scanner_worker.unavailable_result("osv-scanner", cfg, ["osv-scanner is not installed in this worker image."])

    attempts: list[str] = []
    for index, (variant, command) in enumerate(_osv_commands(repo_path)):
        timeout = _remaining(deadline, OSV_TIMEOUT_SECONDS)
        try:
            returncode, stdout, stderr, duration, timed_out = _communicate(command, cwd=repo_path, env=env, timeout=timeout)
        except Exception as exc:
            return {
                "scanner": "osv-scanner",
                "command_intent": cfg.get("intent", "OSV dependency review"),
                "status": "error",
                "execution_status": "execution_error",
                "execution_completed": False,
                "exit_code": None,
                "duration_seconds": 0,
                "evidence_summary": "OSV-Scanner failed safely before dependency triage completed.",
                "safe_output_preview": "",
                "risk_severity": "unknown",
                "recommended_repair": "Repair the hosted scanner runtime and rerun the exact snapshot.",
                "unavailable_data_notes": [f"{type(exc).__name__}: {exc}"],
                "secret_redaction_applied": False,
                "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
            }

        if timed_out:
            preview, redacted = scanner_worker.redact(stderr)
            return {
                "scanner": "osv-scanner",
                "command_intent": cfg.get("intent", "OSV dependency review"),
                "status": "timeout",
                "execution_status": "timeout",
                "execution_completed": False,
                "exit_code": None,
                "duration_seconds": duration,
                "evidence_summary": f"OSV-Scanner timed out after {timeout} seconds.",
                "safe_output_preview": "",
                "risk_severity": "unknown",
                "recommended_repair": "Increase the bounded dependency-scanner runtime or narrow the authorized scope.",
                "unavailable_data_notes": [preview[:1000] or "OSV-Scanner timed out."],
                "secret_redaction_applied": redacted,
                "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
                "command_variant": variant,
            }

        payload, parse_error = _json_payload(stdout)
        normal_exit = returncode in {0, 1}
        if normal_exit and parse_error is None:
            fingerprints = _osv_finding_fingerprints(payload)
            finding_count = len(fingerprints)
            if returncode not in {0, None} and finding_count == 0:
                stderr_preview, _ = scanner_worker.redact(stderr)
                attempts.append(
                    f"{variant}: exit={returncode}; nonzero exit without a parsed vulnerability record; "
                    f"{stderr_preview[:400] or 'no diagnostic'}"
                )
                break
            execution_status = "completed_with_findings" if finding_count else "completed_clean"
            stderr_preview, redacted = scanner_worker.redact(stderr)
            notes = [stderr_preview[:1000]] if stderr_preview else []
            return {
                "scanner": "osv-scanner",
                "command_intent": cfg.get("intent", "OSV dependency review"),
                "status": "passed",
                "execution_status": execution_status,
                "execution_completed": True,
                "exit_code": returncode,
                "duration_seconds": duration,
                "evidence_summary": f"OSV-Scanner dependency scan {execution_status}: vulnerability records={finding_count}.",
                "safe_output_preview": f"vulnerability_records={finding_count}; command_variant={variant}",
                "risk_severity": "high" if finding_count else "low",
                "recommended_repair": "Review every OSV vulnerability record and update affected direct or transitive dependencies before approval." if finding_count else "Retain lockfiles and rerun OSV-Scanner after dependency changes.",
                "unavailable_data_notes": notes,
                "secret_redaction_applied": redacted,
                "finding_count": finding_count,
                "vulnerability_fingerprint_count": finding_count,
                "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
                "command_variant": variant,
            }

        stderr_preview, _ = scanner_worker.redact(stderr)
        attempts.append(f"{variant}: exit={returncode}; {parse_error or stderr_preview[:400] or 'no diagnostic'}")
        if index == 0 and _cli_mismatch(stderr):
            continue
        break

    return {
        "scanner": "osv-scanner",
        "command_intent": cfg.get("intent", "OSV dependency review"),
        "status": "failed",
        "execution_status": "execution_failed",
        "execution_completed": False,
        "exit_code": None,
        "duration_seconds": 0,
        "evidence_summary": "OSV-Scanner did not produce valid completed dependency evidence.",
        "safe_output_preview": "",
        "risk_severity": "unknown",
        "recommended_repair": "Verify the installed OSV-Scanner CLI version and network access, then rerun the exact snapshot.",
        "unavailable_data_notes": attempts,
        "secret_redaction_applied": False,
        "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
    }


def _history_command(name: str, repo_path: Path, report_path: Path) -> list[str]:
    if name == "gitleaks":
        return [
            "gitleaks",
            "git",
            "--no-banner",
            "--redact",
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
            ".",
        ]
    if name == "trufflehog":
        return [
            "trufflehog",
            "git",
            f"file://{repo_path}",
            "--results=verified,unknown,unverified",
            "--json",
            "--no-update",
            "--no-verification",
        ]
    raise ValueError(f"Unsupported history scanner: {name}")


def _run_history(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result(name, cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    binary = str(cfg.get("binary") or name)
    if shutil.which(binary) is None:
        return scanner_worker.unavailable_result(name, cfg, [f"{binary} is not installed in this worker image."])

    metadata = history.history_metadata(repo_path)
    timeout = _remaining(deadline, HISTORY_TIMEOUT_SECONDS)
    with tempfile.TemporaryDirectory(prefix=f"nico-{name}-compat-") as report_dir:
        report_path = Path(report_dir) / f"{name}.json"
        command = _history_command(name, repo_path, report_path)
        try:
            returncode, stdout, stderr, duration, timed_out = _communicate(command, cwd=repo_path, env=env, timeout=timeout)
        except Exception as exc:
            return {
                "scanner": name,
                "command_intent": cfg.get("intent", name),
                "status": "error",
                "execution_status": "execution_error",
                "execution_completed": False,
                "exit_code": None,
                "duration_seconds": 0,
                "evidence_summary": f"{name} failed safely before current-CLI history triage completed.",
                "safe_output_preview": "",
                "risk_severity": "unknown",
                "recommended_repair": "Repair the hosted history-scanner runtime and rerun the exact snapshot.",
                "unavailable_data_notes": [f"{type(exc).__name__}: {exc}"],
                "secret_redaction_applied": False,
                "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
                **metadata,
            }

        if timed_out:
            preview, redacted = scanner_worker.redact(stderr)
            return {
                "scanner": name,
                "command_intent": cfg.get("intent", name),
                "status": "timeout",
                "execution_status": "timeout",
                "execution_completed": False,
                "exit_code": None,
                "duration_seconds": duration,
                "evidence_summary": f"{name} timed out after {timeout} seconds before exact git-history review completed.",
                "safe_output_preview": "",
                "risk_severity": "unknown",
                "recommended_repair": "Increase the bounded history-scanner runtime or reduce repository history after human review.",
                "unavailable_data_notes": [preview[:1000] or "Git-history scanner timed out."],
                "secret_redaction_applied": redacted,
                "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
                **metadata,
            }

        if name == "gitleaks":
            report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else stdout
            findings, parse_note = history.parse_gitleaks_findings(report_text)
            normal_exit = returncode in {0, 1}
        else:
            findings, parse_note = history.parse_trufflehog_findings(stdout)
            normal_exit = returncode == 0

        fatal_parse_notes = {
            "Gitleaks report could not be parsed as JSON.",
            "Gitleaks report did not contain a JSON finding list.",
            "TruffleHog output could not be parsed as JSON lines.",
        }
        execution_completed = normal_exit and parse_note not in fatal_parse_notes
        if name == "gitleaks" and returncode not in {0, None} and not findings:
            execution_completed = False
        verified = sum(bool(item.get("verified")) for item in findings)
        candidates = len(findings) - verified
        execution_status = "completed_with_findings" if findings else "completed_clean"
        if not execution_completed:
            execution_status = "execution_failed"
        notes: list[str] = []
        if parse_note:
            notes.append(parse_note)
        if name == "gitleaks" and returncode not in {0, None} and not findings:
            notes.append("Gitleaks returned nonzero without a parseable finding report; this is execution failure, not clean evidence.")
        if not metadata.get("full_history_covered"):
            notes.append("Git history depth could not be verified as full; this result cannot support a full-history clean claim.")
        stderr_preview, stderr_redacted = scanner_worker.redact(stderr)
        if not execution_completed and stderr_preview:
            notes.append(stderr_preview[:1000])
        return {
            "scanner": name,
            "command_intent": cfg.get("intent", name),
            "status": "passed" if execution_completed else "failed",
            "execution_status": execution_status,
            "execution_completed": execution_completed,
            "exit_code": returncode,
            "duration_seconds": duration,
            "evidence_summary": (
                f"{name} exact git-history scan {execution_status}: findings={len(findings)}, "
                f"verified={verified}, candidates={candidates}, commits={_int(metadata.get('history_commit_count'))}, "
                f"history={metadata.get('history_depth') or 'unknown'}."
            ),
            "safe_output_preview": history._safe_preview(findings),
            "risk_severity": "critical" if verified else "high" if findings else "low" if execution_completed else "unknown",
            "recommended_repair": "Human-validate every history candidate and rotate any confirmed credential outside NICO before removing it from repository history.",
            "unavailable_data_notes": list(dict.fromkeys(notes)),
            "secret_redaction_applied": True,
            "finding_count": len(findings),
            "verified_finding_count": verified,
            "candidate_finding_count": candidates,
            "triage_version": history.HISTORY_VERSION,
            "runtime_compat_version": SCANNER_RUNTIME_COMPAT_VERSION,
            **metadata,
        }


def runtime_compatible_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name == "osv-scanner":
        return _run_osv(cfg, repo_path, env, deadline)
    if name in {"gitleaks", "trufflehog"}:
        return _run_history(name, cfg, repo_path, env, deadline)
    delegate = _DELEGATE_RUN_TOOL
    if delegate is None:
        raise RuntimeError("Scanner runtime compatibility was not installed before worker execution.")
    return delegate(name, cfg, repo_path, env, deadline)


def dependency_section_with_osv_triage(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    delegate = _DEPENDENCY_SECTION_DELEGATE
    if delegate is None:
        raise RuntimeError("Dependency score delegate is unavailable.")
    section = deepcopy(delegate(repo, scanner))
    osv = _scanner_result(scanner, "osv-scanner")
    if not osv or osv.get("execution_completed") is not True:
        return section

    findings = _int(osv.get("finding_count"))
    evidence = [str(item) for item in _list(section.get("evidence"))]
    evidence.append(f"OSV-Scanner structured result: {osv.get('execution_status') or 'completed'}; vulnerability records={findings}.")
    section["evidence"] = evidence
    section["verified_claims"] = evidence
    section["dependency_scanner_triage"] = {
        "osv_execution_completed": True,
        "osv_execution_status": osv.get("execution_status") or "completed",
        "osv_vulnerability_record_count": findings,
        "runtime_compat_version": osv.get("runtime_compat_version") or SCANNER_RUNTIME_COMPAT_VERSION,
    }
    if findings:
        section["score"] = min(_int(section.get("score")), 55)
        section["status"] = "yellow" if section["score"] >= 55 else "red"
        findings_list = [str(item) for item in _list(section.get("findings"))]
        findings_list.append(f"Review and remediate {findings} OSV vulnerability record(s) before report approval.")
        section["findings"] = list(dict.fromkeys(findings_list))
    return section


def install_scanner_runtime_compat() -> dict[str, Any]:
    global _DELEGATE_RUN_TOOL, _DEPENDENCY_SECTION_DELEGATE

    installed = bool(getattr(scanner_worker, "_nico_scanner_runtime_compat_installed", False))
    if not installed:
        _DELEGATE_RUN_TOOL = scanner_worker.run_tool
        _DEPENDENCY_SECTION_DELEGATE = scorecard._dependency_section
        scanner_worker.run_tool = runtime_compatible_run_tool
        scorecard._dependency_section = dependency_section_with_osv_triage
        scanner_worker._nico_scanner_runtime_compat_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": SCANNER_RUNTIME_COMPAT_VERSION,
        "tools": sorted(_COMPAT_TOOLS),
        "osv_timeout_seconds": OSV_TIMEOUT_SECONDS,
        "history_timeout_seconds": HISTORY_TIMEOUT_SECONDS,
        "rule": "Current hosted scanner CLIs must produce parseable structured evidence; findings are distinct from execution failure, and full-history claims still require verified full git depth.",
    }


__all__ = [
    "HISTORY_TIMEOUT_SECONDS",
    "OSV_TIMEOUT_SECONDS",
    "SCANNER_RUNTIME_COMPAT_VERSION",
    "dependency_section_with_osv_triage",
    "install_scanner_runtime_compat",
    "runtime_compatible_run_tool",
]
