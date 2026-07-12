from __future__ import annotations

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

import nico.assessment_score_integrity as integrity
import nico.full_assessment_scorecard as scorecard
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers

HISTORY_VERSION = "nico-exact-snapshot-secret-history-v1"
_HISTORY_TOOLS = {"gitleaks", "trufflehog"}
_DELEGATE_RUN_TOOL: Callable[..., dict[str, Any]] | None = None
_ATTACHMENT_DELEGATE: Callable[..., dict[str, Any]] | None = None


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fingerprint(value: Any) -> str:
    import hashlib

    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16] if text else ""


def _git_value(repo_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        )
    except Exception:
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def history_metadata(repo_path: Path) -> dict[str, Any]:
    shallow = _git_value(repo_path, ["rev-parse", "--is-shallow-repository"]).lower()
    count = _int(_git_value(repo_path, ["rev-list", "--count", "HEAD"]))
    commit_sha = _git_value(repo_path, ["rev-parse", "HEAD"]).lower()
    full = shallow == "false" and count > 0
    return {
        "full_history_covered": full,
        "history_depth": "full" if full else "shallow_or_unverified",
        "history_commit_count": count,
        "snapshot_commit_sha": commit_sha,
    }


def _load_json(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _json_lines(value: str) -> tuple[list[Any], bool]:
    items: list[Any] = []
    invalid = False
    for line in str(value or "").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            items.append(json.loads(text))
        except json.JSONDecodeError:
            invalid = True
    return items, invalid


def parse_gitleaks_findings(value: str) -> tuple[list[dict[str, Any]], str | None]:
    payload = _load_json(value)
    if payload is None:
        return [], "Gitleaks report could not be parsed as JSON."
    if not isinstance(payload, list):
        return [], "Gitleaks report did not contain a JSON finding list."
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        commit = str(item.get("Commit") or item.get("commit") or "")
        findings.append(
            {
                "tool": "gitleaks",
                "rule_id": str(item.get("RuleID") or item.get("rule_id") or "unknown"),
                "path": str(item.get("File") or item.get("file") or ""),
                "line": _int(item.get("StartLine") or item.get("line")),
                "commit_fingerprint": _fingerprint(commit),
                "verified": False,
                "material": True,
            }
        )
    return findings, None


def _trufflehog_source(item: dict[str, Any]) -> dict[str, Any]:
    source = _dict(item.get("SourceMetadata"))
    data = _dict(source.get("Data"))
    git = _dict(data.get("Git"))
    return {
        "path": str(git.get("file") or git.get("File") or ""),
        "line": _int(git.get("line") or git.get("Line")),
        "commit": str(git.get("commit") or git.get("Commit") or ""),
    }


def parse_trufflehog_findings(value: str) -> tuple[list[dict[str, Any]], str | None]:
    payload, invalid = _json_lines(value)
    if invalid and not payload:
        return [], "TruffleHog output could not be parsed as JSON lines."
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        source = _trufflehog_source(item)
        verified = bool(item.get("Verified"))
        findings.append(
            {
                "tool": "trufflehog",
                "rule_id": str(item.get("DetectorName") or item.get("DetectorType") or "unknown"),
                "path": source["path"],
                "line": source["line"],
                "commit_fingerprint": _fingerprint(source["commit"]),
                "verified": verified,
                "material": True,
            }
        )
    return findings, "Some TruffleHog output lines were not parseable and were excluded." if invalid else None


def _safe_preview(findings: list[dict[str, Any]], limit: int = 30) -> str:
    return "\n".join(
        f"{item.get('tool')}:{item.get('rule_id')} {item.get('path')}:{item.get('line')} "
        f"commit={item.get('commit_fingerprint') or 'unknown'} verified={bool(item.get('verified'))}"
        for item in findings[:limit]
    )


def _history_command(name: str, repo_path: Path, report_path: Path) -> list[str]:
    if name == "gitleaks":
        return [
            "gitleaks",
            "detect",
            "--no-banner",
            "--redact",
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
            "--source",
            ".",
        ]
    if name == "trufflehog":
        return [
            "trufflehog",
            "git",
            f"file://{repo_path}",
            "--json",
            "--no-update",
            "--no-verification",
        ]
    raise ValueError(f"Unsupported history scanner: {name}")


def _run_history_tool(
    name: str,
    cfg: dict[str, Any],
    repo_path: Path,
    env: dict[str, str],
    deadline: float,
) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result(name, cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    binary = str(cfg.get("binary") or name)
    if shutil.which(binary) is None:
        return scanner_worker.unavailable_result(name, cfg, [f"{binary} is not installed in this worker image."])

    metadata = history_metadata(repo_path)
    remaining = max(1, min(scanner_worker.DEFAULT_TOOL_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"nico-{name}-report-") as report_dir:
        report_path = Path(report_dir) / f"{name}.json"
        command = _history_command(name, repo_path, report_path)
        try:
            process = subprocess.Popen(
                command,
                cwd=str(repo_path),
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
                stderr_preview, redacted = scanner_worker.redact(stderr or "")
                return {
                    "scanner": name,
                    "command_intent": cfg.get("intent", name),
                    "status": "timeout",
                    "execution_status": "timeout",
                    "execution_completed": False,
                    "exit_code": None,
                    "duration_seconds": round(time.monotonic() - started, 2),
                    "evidence_summary": f"{name} timed out before exact git-history review completed.",
                    "safe_output_preview": "",
                    "risk_severity": "unknown",
                    "recommended_repair": "Increase the bounded scanner runtime or reduce repository history after human review.",
                    "unavailable_data_notes": ["Git-history scanner timed out.", stderr_preview[:1000]],
                    "secret_redaction_applied": redacted,
                    **metadata,
                }

            if name == "gitleaks":
                report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else (stdout or "")
                findings, parse_note = parse_gitleaks_findings(report_text)
            else:
                findings, parse_note = parse_trufflehog_findings(stdout or "")

            normal_exit = process.returncode in {0, 1}
            execution_completed = normal_exit and parse_note not in {
                "Gitleaks report could not be parsed as JSON.",
                "Gitleaks report did not contain a JSON finding list.",
                "TruffleHog output could not be parsed as JSON lines.",
            }
            status = "passed" if execution_completed else "failed"
            verified = sum(bool(item.get("verified")) for item in findings)
            candidate = len(findings) - verified
            execution_status = "completed_with_findings" if findings else "completed_clean"
            if not execution_completed:
                execution_status = "execution_failed"
            notes: list[str] = []
            if parse_note:
                notes.append(parse_note)
            if not metadata["full_history_covered"]:
                notes.append("Git history depth could not be verified as full; this scanner result cannot support a full-history clean claim.")
            stderr_preview, stderr_redacted = scanner_worker.redact(stderr or "")
            if not execution_completed and stderr_preview:
                notes.append(stderr_preview[:1000])
            summary = (
                f"{name} exact git-history scan {execution_status}: findings={len(findings)}, "
                f"verified={verified}, candidates={candidate}, commits={metadata['history_commit_count']}, "
                f"history={metadata['history_depth']}."
            )
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
                "risk_severity": "critical" if verified else "high" if findings else "low",
                "recommended_repair": "Human-validate every history candidate and rotate any confirmed credential outside NICO before removing it from repository history.",
                "unavailable_data_notes": notes,
                "secret_redaction_applied": True,
                "finding_count": len(findings),
                "verified_finding_count": verified,
                "candidate_finding_count": candidate,
                "triage_version": HISTORY_VERSION,
                **metadata,
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
                "evidence_summary": f"{name} failed safely before exact git-history triage completed.",
                "safe_output_preview": "",
                "risk_severity": "unknown",
                "recommended_repair": "Review scanner installation and history checkout, then rerun the exact snapshot.",
                "unavailable_data_notes": [f"{type(exc).__name__}: {exc}"],
                "secret_redaction_applied": False,
                **metadata,
            }


def history_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name in _HISTORY_TOOLS:
        return _run_history_tool(name, cfg, repo_path, env, deadline)
    delegate = _DELEGATE_RUN_TOOL
    if delegate is None:
        raise RuntimeError("Exact-snapshot secret history scanning was not installed before worker execution.")
    return delegate(name, cfg, repo_path, env, deadline)


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def history_secrets_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    sampled = _int(signals.get("potential_secret_pattern_hits"))
    built_in = _scanner_result(scanner, "nico-secrets")
    built_counts = _dict(built_in.get("finding_counts"))
    current_high = _int(built_counts.get("high"))
    current_medium = _int(built_counts.get("medium"))
    current_low = _int(built_counts.get("low"))
    current_completed = str(built_in.get("status") or "") in {"passed", "failed"}

    history = [_scanner_result(scanner, name) for name in ("gitleaks", "trufflehog")]
    completed = [
        item
        for item in history
        if item.get("execution_completed") is True and item.get("full_history_covered") is True
    ]
    history_findings = sum(_int(item.get("finding_count")) for item in completed)
    verified = sum(_int(item.get("verified_finding_count")) for item in completed)
    candidates = sum(_int(item.get("candidate_finding_count")) for item in completed)
    failed = [item for item in history if item and item.get("execution_completed") is not True and item.get("status") in {"failed", "error"}]
    timed_out = [item for item in history if item.get("status") == "timeout"]

    score = 68 if sampled == 0 else max(25, 60 - sampled * 8)
    if current_completed:
        score += 12
    score += min(16, len(completed) * 8)
    score -= min(55, current_high * 35)
    score -= min(18, current_medium * 8)
    score -= min(4, current_low)
    score -= min(60, verified * 40)
    score -= min(45, candidates * 12)
    score -= len(failed) * 8
    score -= len(timed_out) * 6
    if len(completed) < 2:
        score = min(score, 74)
    if history_findings:
        score = min(score, 60)
    if verified:
        score = min(score, 35)
    score = max(20, min(95, score))

    evidence = [
        f"Sampled current-tree material credential candidates={sampled}.",
        f"NICO current-tree credential classifier status={built_in.get('status') or 'not run'}; high={current_high}, medium={current_medium}, low={current_low}; files={_int(built_in.get('files_scanned'))}.",
        f"Exact git-history scanners completed with verified full history={len(completed)}/2; findings={history_findings}; verified={verified}; candidates={candidates}.",
        "Raw credential values are never returned or retained in assessment evidence.",
    ]
    for name, item in zip(("Gitleaks", "TruffleHog"), history):
        if item.get("execution_completed") and item.get("full_history_covered"):
            evidence.append(
                f"{name} exact git-history scan completed with {_int(item.get('finding_count'))} finding(s) across {_int(item.get('history_commit_count'))} commit(s)."
            )

    findings: list[str] = []
    if current_high:
        findings.append(f"Immediately triage {current_high} high-confidence current-tree credential candidate(s).")
    if current_medium:
        findings.append(f"Human-validate {current_medium} medium-confidence current-tree credential candidate(s).")
    if verified:
        findings.append(f"Immediately rotate and remediate {verified} verified git-history credential finding(s).")
    if candidates:
        findings.append(f"Human-validate {candidates} unverified git-history credential candidate(s) before approval.")
    if failed or timed_out:
        findings.append("One or more history scanners failed or timed out; a clean history claim is prohibited.")

    unavailable = ["Clean scanner execution reduces observed risk but is not proof that no credential exists outside the scanned repository history."]
    if len(completed) < 2:
        unavailable.append("Gitleaks and TruffleHog did not both produce exact full-history evidence for this run.")

    confidence = "history-scanner-and-repository-bound" if len(completed) == 2 else "current-tree-scanner-bound" if current_completed else "limited"
    section = scorecard._section(
        "secrets_review",
        "Secrets Exposure Review",
        score,
        "Secrets maturity combines masked current-tree classification with exact-snapshot Gitleaks and TruffleHog git-history evidence when both scanners complete against verified full history.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence=confidence,
    )
    section["secret_history_triage"] = {
        "version": HISTORY_VERSION,
        "history_scanners_completed": len(completed),
        "history_finding_count": history_findings,
        "verified_finding_count": verified,
        "candidate_finding_count": candidates,
        "execution_failures": len(failed),
        "timeouts": len(timed_out),
    }
    return section


def history_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    delegate = _ATTACHMENT_DELEGATE
    if delegate is None:
        raise RuntimeError("Exact-snapshot history attachment was not installed.")
    result = delegate(context, outputs)
    if result.get("status") != "complete":
        return result

    scanner_step = _dict(outputs.get("scanner_worker"))
    scan = _dict(scanner_step.get("scan"))
    raw_results = [item for item in _list(scan.get("scanner_results")) if isinstance(item, dict)]
    evidence = deepcopy(_dict(result.get("scanner_evidence") or result.get("evidence")))
    sanitized = [item for item in _list(evidence.get("scanner_results")) if isinstance(item, dict)]
    by_name = {str(item.get("scanner") or ""): item for item in sanitized}
    allowed = (
        "execution_status",
        "execution_completed",
        "finding_count",
        "material_finding_count",
        "review_finding_count",
        "excluded_test_finding_count",
        "severity_counts",
        "confidence_counts",
        "verified_finding_count",
        "candidate_finding_count",
        "full_history_covered",
        "history_commit_count",
        "history_depth",
        "snapshot_commit_sha",
        "triage_version",
    )
    for raw in raw_results:
        name = str(raw.get("scanner") or "")
        if not name:
            continue
        target = by_name.setdefault(
            name,
            {
                "scanner": name,
                "status": raw.get("status") or "unknown",
                "evidence_summary": raw.get("evidence_summary") or "",
                "unavailable_data_notes": raw.get("unavailable_data_notes") or [],
            },
        )
        for key in allowed:
            if key in raw:
                target[key] = deepcopy(raw[key])

    evidence["scanner_results"] = list(by_name.values())
    evidence["history_scanner_version"] = HISTORY_VERSION
    evidence["structured_triage_fields_attached"] = True
    result["scanner_evidence"] = evidence
    result["evidence"] = evidence
    return result


def install_exact_snapshot_secret_history() -> dict[str, Any]:
    global _DELEGATE_RUN_TOOL, _ATTACHMENT_DELEGATE
    installed = bool(getattr(scanner_worker, "_nico_exact_snapshot_secret_history_installed", False))
    if not installed:
        _DELEGATE_RUN_TOOL = scanner_worker.run_tool
        _ATTACHMENT_DELEGATE = snapshot_handlers._snapshot_evidence_attachment_handler

    catalog = scanner_worker.TOOL_CATALOG
    scanner_worker.TOOL_CATALOG = {
        **({"nico-secrets": catalog["nico-secrets"]} if "nico-secrets" in catalog else {}),
        "gitleaks": {"binary": "gitleaks", "intent": "Exact git-history credential review", "tier": "secret_history"},
        "trufflehog": {"binary": "trufflehog", "intent": "Exact git-history credential review", "tier": "secret_history"},
        **{key: value for key, value in catalog.items() if key not in {"nico-secrets", "gitleaks", "trufflehog"}},
    }
    scanner_worker.run_tool = history_run_tool
    scorecard._secrets_section = history_secrets_section
    integrity.calibrated_secrets_section = history_secrets_section
    snapshot_handlers._snapshot_evidence_attachment_handler = history_attachment_handler
    mid_handlers._snapshot_evidence_attachment_handler = history_attachment_handler
    scanner_worker._nico_exact_snapshot_secret_history_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": HISTORY_VERSION,
        "tools": sorted(_HISTORY_TOOLS),
        "rule": "A high-confidence clean history score requires both scanners to complete against a checkout independently verified as full git history.",
        "redaction_rule": "Raw, redacted, and encoded credential values are never persisted in the assessment evidence record.",
    }


__all__ = [
    "HISTORY_VERSION",
    "history_attachment_handler",
    "history_metadata",
    "history_run_tool",
    "history_secrets_section",
    "install_exact_snapshot_secret_history",
    "parse_gitleaks_findings",
    "parse_trufflehog_findings",
]
