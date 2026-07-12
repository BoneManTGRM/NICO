from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import nico.assessment_score_integrity as integrity
import nico.full_assessment_scorecard as scorecard
import nico.scanner_worker as scanner_worker

TRIAGE_VERSION = "nico-exact-snapshot-static-triage-v1"
_STATIC_TOOLS = {"bandit", "semgrep"}
_TEST_PARTS = {"test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples"}
_DELEGATE_RUN_TOOL: Callable[..., dict[str, Any]] | None = None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_test_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/")
    parts = {part.lower() for part in normalized.split("/") if part}
    name = Path(normalized).name.lower()
    return bool(parts & _TEST_PARTS) or name.startswith("test_") or name.endswith(
        ("_test.py", ".test.js", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts", ".spec.tsx")
    )


def _load_json_payload(text: str) -> Any:
    value = str(text or "").strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        opening = min((index for index in (value.find("{"), value.find("[")) if index >= 0), default=-1)
        if opening < 0:
            return None
        try:
            return json.loads(value[opening:])
        except json.JSONDecodeError:
            return None


def _bandit_findings(payload: Any) -> list[dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    for item in _list(results):
        if not isinstance(item, dict):
            continue
        path = str(item.get("filename") or "")
        severity = str(item.get("issue_severity") or "unknown").lower()
        confidence = str(item.get("issue_confidence") or "unknown").lower()
        test_only = _is_test_path(path)
        material = not test_only and (
            (severity == "high" and confidence in {"high", "medium"})
            or (severity == "medium" and confidence == "high")
        )
        findings.append(
            {
                "tool": "bandit",
                "rule_id": str(item.get("test_id") or item.get("test_name") or "unknown"),
                "path": path,
                "line": _int(item.get("line_number")),
                "severity": severity,
                "confidence": confidence,
                "test_only": test_only,
                "material": material,
                "review_required": not material and not test_only,
                "message": str(item.get("issue_text") or "Bandit finding")[:240],
            }
        )
    return findings


def _semgrep_findings(payload: Any) -> list[dict[str, Any]]:
    results = payload.get("results") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    for item in _list(results):
        if not isinstance(item, dict):
            continue
        extra = _dict(item.get("extra"))
        metadata = _dict(extra.get("metadata"))
        path = str(item.get("path") or "")
        severity = str(extra.get("severity") or metadata.get("severity") or "warning").lower()
        confidence = str(metadata.get("confidence") or "unknown").lower()
        test_only = _is_test_path(path)
        material = not test_only and severity in {"error", "critical", "high"}
        findings.append(
            {
                "tool": "semgrep",
                "rule_id": str(item.get("check_id") or "unknown"),
                "path": path,
                "line": _int(_dict(item.get("start")).get("line")),
                "severity": severity,
                "confidence": confidence,
                "test_only": test_only,
                "material": material,
                "review_required": not material and not test_only,
                "message": str(extra.get("message") or "Semgrep finding")[:240],
            }
        )
    return findings


def parse_static_findings(name: str, stdout: str) -> tuple[list[dict[str, Any]], str | None]:
    payload = _load_json_payload(stdout)
    if payload is None:
        return [], "Static analyzer output could not be parsed as JSON."
    if name == "bandit":
        return _bandit_findings(payload), None
    if name == "semgrep":
        return _semgrep_findings(payload), None
    return [], f"No structured parser exists for {name}."


def _structured_counts(findings: list[dict[str, Any]]) -> dict[str, Any]:
    severity = Counter(str(item.get("severity") or "unknown") for item in findings)
    confidence = Counter(str(item.get("confidence") or "unknown") for item in findings)
    material = [item for item in findings if item.get("material")]
    review = [item for item in findings if item.get("review_required")]
    excluded = [item for item in findings if item.get("test_only")]
    return {
        "finding_count": len(findings),
        "material_finding_count": len(material),
        "review_finding_count": len(review),
        "excluded_test_finding_count": len(excluded),
        "severity_counts": dict(sorted(severity.items())),
        "confidence_counts": dict(sorted(confidence.items())),
    }


def _safe_preview(findings: list[dict[str, Any]], limit: int = 30) -> str:
    lines = []
    for item in findings[:limit]:
        disposition = "material" if item.get("material") else "test-only" if item.get("test_only") else "review"
        lines.append(
            f"{item.get('tool')}:{item.get('rule_id')} {item.get('path')}:{item.get('line')} "
            f"severity={item.get('severity')} confidence={item.get('confidence')} disposition={disposition}"
        )
    return "\n".join(lines)


def _run_structured_static_tool(
    name: str,
    cfg: dict[str, Any],
    repo_path: Path,
    env: dict[str, str],
    deadline: float,
) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result(name, cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if shutil.which(str(cfg.get("binary") or name)) is None:
        return scanner_worker.unavailable_result(name, cfg, [f"{cfg.get('binary') or name} is not installed in this worker image."])
    command, cwd, notes = scanner_worker.command_for_tool(name, repo_path)
    if not command:
        return scanner_worker.unavailable_result(name, cfg, notes)

    remaining = max(1, min(scanner_worker.DEFAULT_TOOL_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    started = time.monotonic()
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
            preview, redacted = scanner_worker.redact((stdout or "") + "\n" + (stderr or ""))
            return {
                "scanner": name,
                "command_intent": cfg.get("intent", name),
                "status": "timeout",
                "execution_status": "timeout",
                "execution_completed": False,
                "exit_code": None,
                "duration_seconds": round(time.monotonic() - started, 2),
                "evidence_summary": f"{name} timed out after {remaining} seconds.",
                "safe_output_preview": preview,
                "risk_severity": "unknown",
                "recommended_repair": "Increase worker resources or narrow the scan scope after human review.",
                "unavailable_data_notes": ["Tool timed out before structured triage completed."],
                "secret_redaction_applied": redacted,
            }

        findings, parse_error = parse_static_findings(name, stdout or "")
        counts = _structured_counts(findings)
        normal_finding_exit = process.returncode in {0, 1}
        execution_completed = parse_error is None and normal_finding_exit
        status = "passed" if execution_completed else "failed"
        material = _int(counts.get("material_finding_count"))
        review = _int(counts.get("review_finding_count"))
        excluded = _int(counts.get("excluded_test_finding_count"))
        execution_status = "completed_with_findings" if counts["finding_count"] else "completed_clean"
        if not execution_completed:
            execution_status = "execution_failed"
        summary = (
            f"{name} execution {execution_status}: findings={counts['finding_count']}, material={material}, "
            f"review={review}, test-only={excluded}."
        )
        unavailable = list(notes)
        if parse_error:
            unavailable.append(parse_error)
        stderr_preview, stderr_redacted = scanner_worker.redact(stderr or "")
        if not execution_completed and stderr_preview:
            unavailable.append(stderr_preview[:1000])
        severity = "high" if material else "medium" if review else "low"
        return {
            "scanner": name,
            "command_intent": cfg.get("intent", name),
            "status": status,
            "execution_status": execution_status,
            "execution_completed": execution_completed,
            "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 2),
            "evidence_summary": summary,
            "safe_output_preview": _safe_preview(findings),
            "risk_severity": severity,
            "recommended_repair": "Prioritize material production findings, human-review non-material production findings, and keep test-only findings separate from production risk scoring.",
            "unavailable_data_notes": unavailable,
            "secret_redaction_applied": stderr_redacted,
            "findings": findings[:100],
            "triage_version": TRIAGE_VERSION,
            **counts,
        }
    except Exception as exc:
        return {
            "scanner": name,
            "command_intent": cfg.get("intent", name),
            "status": "error",
            "execution_status": "execution_error",
            "execution_completed": False,
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 2),
            "evidence_summary": f"{name} failed safely before structured triage completed.",
            "safe_output_preview": "",
            "risk_severity": "unknown",
            "recommended_repair": "Review worker configuration and rerun after the analyzer environment is fixed.",
            "unavailable_data_notes": [f"{type(exc).__name__}: {exc}"],
            "secret_redaction_applied": False,
        }


def triaged_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name in _STATIC_TOOLS:
        return _run_structured_static_tool(name, cfg, repo_path, env, deadline)
    delegate = _DELEGATE_RUN_TOOL
    if delegate is None:
        raise RuntimeError("Exact-snapshot static triage was not installed before scanner execution.")
    return delegate(name, cfg, repo_path, env, deadline)


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def triaged_static_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    sampled = _int(signals.get("risk_pattern_hits"))
    built_in = _scanner_result(scanner, "nico-static")
    built_hits = _int(built_in.get("finding_count"))
    built_in_ran = str(built_in.get("status") or "") in {"passed", "failed"}

    results = [_scanner_result(scanner, name) for name in ("bandit", "semgrep")]
    completed = [item for item in results if item.get("execution_completed") is True]
    material = sum(_int(item.get("material_finding_count")) for item in completed)
    review = sum(_int(item.get("review_finding_count")) for item in completed)
    excluded = sum(_int(item.get("excluded_test_finding_count")) for item in completed)
    failed = [item for item in results if item and item.get("execution_completed") is not True and item.get("status") in {"failed", "error"}]
    timed_out = [item for item in results if item.get("status") == "timeout"]

    eslint = _scanner_result(scanner, "eslint")
    eslint_completed = str(eslint.get("status") or "") == "passed"

    score = 58 if sampled == 0 else max(30, 55 - sampled * 5)
    if built_in_ran:
        score += 16
    score += min(20, len(completed) * 8 + (4 if eslint_completed else 0))
    score -= min(40, material * 7)
    score -= min(12, round(review * 0.4))
    score -= len(failed) * 8
    score -= len(timed_out) * 6
    if not built_in_ran and not completed:
        score = min(score, 60)
    if material:
        score = min(score, 74)
    score = max(25, min(90, score))

    evidence = [
        f"Sampled-file static risk-pattern hits: {sampled}.",
        f"NICO current-tree static scanner status={built_in.get('status') or 'not run'}; material hits={built_hits}; files={_int(built_in.get('files_scanned'))}.",
        f"Structured exact-snapshot analyzers completed={len(completed)}/2; material findings={material}; review findings={review}; excluded test-only findings={excluded}.",
        f"ESLint exact-snapshot execution status={eslint.get('status') or 'not run'}.",
    ]
    for item in completed:
        evidence.append(str(item.get("evidence_summary") or ""))

    findings: list[str] = []
    if built_hits:
        findings.append(f"Review {built_hits} built-in current-tree static pattern hit(s).")
    if material:
        findings.append(f"Prioritize {material} material high-confidence production finding(s) from Bandit/Semgrep before report approval.")
    if review:
        findings.append(f"Human-review {review} non-material production finding(s); these are not scored as confirmed high-risk defects.")
    if failed or timed_out:
        findings.append("One or more structured analyzers failed or timed out; semantic static-analysis coverage is incomplete.")

    unavailable = ["Completed analyzer execution and a clean bounded pattern result are not proof that no vulnerability exists."]
    if len(completed) < 2:
        unavailable.append("Bandit and Semgrep did not both produce parseable exact-snapshot evidence for this run.")
    if not eslint_completed:
        unavailable.append("ESLint exact-snapshot evidence was not completed; JavaScript/TypeScript semantic lint coverage remains unavailable.")

    confidence = "structured-scanner-bound" if len(completed) == 2 and built_in_ran else "current-tree-scanner-bound" if built_in_ran else "limited"
    section = scorecard._section(
        "static_analysis",
        "Static Analysis",
        score,
        "Static-analysis maturity combines bounded full-checkout scanning with structured Bandit/Semgrep triage that separates material production findings, review items, and test-only evidence.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence=confidence,
    )
    section["static_triage"] = {
        "version": TRIAGE_VERSION,
        "material_finding_count": material,
        "review_finding_count": review,
        "excluded_test_finding_count": excluded,
        "structured_analyzers_completed": len(completed),
        "execution_failures": len(failed),
        "timeouts": len(timed_out),
    }
    return section


def install_exact_snapshot_static_triage() -> dict[str, Any]:
    global _DELEGATE_RUN_TOOL
    installed = bool(getattr(scanner_worker, "_nico_exact_snapshot_static_triage_installed", False))
    if not installed:
        _DELEGATE_RUN_TOOL = scanner_worker.run_tool
    scanner_worker.run_tool = triaged_run_tool
    scorecard._static_section = triaged_static_section
    integrity.calibrated_static_section = triaged_static_section
    scanner_worker._nico_exact_snapshot_static_triage_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": TRIAGE_VERSION,
        "tools": sorted(_STATIC_TOOLS),
        "rule": "Nonzero analyzer exits caused by parseable findings are treated as completed evidence; only material production findings materially reduce the score.",
        "test_only_rule": "Findings in tests, fixtures, examples, and samples remain disclosed but are excluded from production-risk scoring.",
    }


__all__ = [
    "TRIAGE_VERSION",
    "install_exact_snapshot_static_triage",
    "parse_static_findings",
    "triaged_run_tool",
    "triaged_static_section",
]
