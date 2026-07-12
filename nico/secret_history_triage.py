from __future__ import annotations

import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import nico.assessment_score_integrity as score_integrity
import nico.exact_snapshot_secret_history as history
import nico.full_assessment_scorecard as scorecard
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_runtime_compat as runtime_compat
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers

SECRET_HISTORY_TRIAGE_VERSION = "nico-secret-history-triage-v2"
_HISTORY_TOOLS = {"gitleaks", "trufflehog"}
_TEST_PARTS = {"test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples"}
_DELEGATE_RUN_TOOL: Callable[..., dict[str, Any]] | None = None
_SECRETS_SECTION_DELEGATE: Callable[..., dict[str, Any]] | None = None
_ATTACHMENT_DELEGATE: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_test_path(value: Any) -> bool:
    normalized = str(value or "").replace("\\", "/")
    parts = {part.lower() for part in normalized.split("/") if part}
    name = Path(normalized).name.lower()
    return bool(parts & _TEST_PARTS) or name.startswith("test_") or name.endswith(
        ("_test.py", ".test.js", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts", ".spec.tsx")
    )


def classify_history_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for raw in findings:
        item = deepcopy(raw)
        test_only = _is_test_path(item.get("path"))
        verified = bool(item.get("verified"))
        material = verified or not test_only
        item["test_only"] = test_only
        item["material"] = material
        item["review_required"] = material and not verified
        item["disposition"] = "material" if material else "test-only"
        classified.append(item)
    return classified


def _safe_preview(findings: list[dict[str, Any]], limit: int = 30) -> str:
    return "\n".join(
        f"{item.get('tool')}:{item.get('rule_id')} {item.get('path')}:{item.get('line')} "
        f"commit={item.get('commit_fingerprint') or 'unknown'} verified={bool(item.get('verified'))} "
        f"disposition={item.get('disposition') or 'review'}"
        for item in findings[:limit]
    )


def _run_history(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result(name, cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    binary = str(cfg.get("binary") or name)
    if shutil.which(binary) is None:
        return scanner_worker.unavailable_result(name, cfg, [f"{binary} is not installed in this worker image."])

    metadata = history.history_metadata(repo_path)
    timeout = max(1, min(runtime_compat.HISTORY_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    import tempfile

    with tempfile.TemporaryDirectory(prefix=f"nico-{name}-triage-") as report_dir:
        report_path = Path(report_dir) / f"{name}.json"
        command = runtime_compat._history_command(name, repo_path, report_path)
        try:
            returncode, stdout, stderr, duration, timed_out = runtime_compat._communicate(
                command, cwd=repo_path, env=env, timeout=timeout
            )
        except Exception as exc:
            result = scanner_worker.unavailable_result(name, cfg, [f"{type(exc).__name__}: {exc}"])
            result.update(
                {
                    "status": "error",
                    "execution_status": "execution_error",
                    "execution_completed": False,
                    "duration_seconds": 0,
                    **metadata,
                }
            )
            return result

        if timed_out:
            preview, redacted = scanner_worker.redact(stderr)
            result = scanner_worker.unavailable_result(name, cfg, [preview[:1000] or f"{name} timed out."])
            result.update(
                {
                    "status": "timeout",
                    "execution_status": "timeout",
                    "execution_completed": False,
                    "duration_seconds": duration,
                    "secret_redaction_applied": redacted,
                    **metadata,
                }
            )
            return result

        if name == "gitleaks":
            report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else stdout
            parsed, parse_note = history.parse_gitleaks_findings(report_text)
            normal_exit = returncode in {0, 1}
        else:
            parsed, parse_note = history.parse_trufflehog_findings(stdout)
            normal_exit = returncode == 0

        fatal_notes = {
            "Gitleaks report could not be parsed as JSON.",
            "Gitleaks report did not contain a JSON finding list.",
            "TruffleHog output could not be parsed as JSON lines.",
        }
        findings = classify_history_findings(parsed)
        execution_completed = normal_exit and parse_note not in fatal_notes
        if name == "gitleaks" and returncode not in {0, None} and not parsed:
            execution_completed = False

        material = [item for item in findings if item.get("material")]
        review = [item for item in material if item.get("review_required")]
        excluded = [item for item in findings if item.get("test_only") and not item.get("verified")]
        verified = [item for item in findings if item.get("verified")]
        execution_status = "completed_with_findings" if findings else "completed_clean"
        if not execution_completed:
            execution_status = "execution_failed"
        notes: list[str] = []
        if parse_note:
            notes.append(parse_note)
        if not metadata.get("full_history_covered"):
            notes.append("Git history depth could not be verified as full; this result cannot support a full-history clean claim.")
        stderr_preview, redacted = scanner_worker.redact(stderr)
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
                f"{name} exact git-history scan {execution_status}: total={len(findings)}, material={len(material)}, "
                f"review={len(review)}, excluded-test-only={len(excluded)}, verified={len(verified)}, "
                f"commits={_int(metadata.get('history_commit_count'))}, history={metadata.get('history_depth') or 'unknown'}."
            ),
            "safe_output_preview": _safe_preview(findings),
            "risk_severity": "critical" if verified else "high" if material else "low" if execution_completed else "unknown",
            "recommended_repair": "Rotate confirmed credentials outside NICO; human-review production candidates; keep synthetic test fixtures distinct from production risk.",
            "unavailable_data_notes": list(dict.fromkeys(notes)),
            "secret_redaction_applied": True or redacted,
            # Legacy scoring fields intentionally contain score-bearing production findings.
            "finding_count": len(material),
            "candidate_finding_count": len(review),
            "verified_finding_count": len(verified),
            # Additional transparent totals disclose every parser match.
            "total_finding_count": len(findings),
            "material_finding_count": len(material),
            "review_finding_count": len(review),
            "excluded_test_finding_count": len(excluded),
            "triage_version": SECRET_HISTORY_TRIAGE_VERSION,
            **metadata,
        }


def secret_history_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name in _HISTORY_TOOLS:
        return _run_history(name, cfg, repo_path, env, deadline)
    if _DELEGATE_RUN_TOOL is None:
        raise RuntimeError("Secret-history triage was not installed before worker execution.")
    return _DELEGATE_RUN_TOOL(name, cfg, repo_path, env, deadline)


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def secret_history_section_with_test_triage(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    if _SECRETS_SECTION_DELEGATE is None:
        raise RuntimeError("Secrets score delegate is unavailable.")
    section = deepcopy(_SECRETS_SECTION_DELEGATE(repo, scanner))
    results = [_scanner_result(scanner, name) for name in ("gitleaks", "trufflehog")]
    completed = [item for item in results if item.get("execution_completed") is True and item.get("full_history_covered") is True]
    total = sum(_int(item.get("total_finding_count", item.get("finding_count"))) for item in completed)
    material = sum(_int(item.get("material_finding_count", item.get("finding_count"))) for item in completed)
    review = sum(_int(item.get("review_finding_count", item.get("candidate_finding_count"))) for item in completed)
    excluded = sum(_int(item.get("excluded_test_finding_count")) for item in completed)

    evidence = [str(item) for item in _list(section.get("evidence"))]
    evidence.append(
        f"Secret-history disposition: total={total}, material={material}, review-required={review}, excluded test-only={excluded}; verified-full-history scanners={len(completed)}/2."
    )
    findings = [str(item) for item in _list(section.get("findings"))]
    if excluded:
        findings.append(
            f"Human-confirm {excluded} unverified test-only history match(es) remain synthetic fixtures; they are disclosed but not scored as production credential exposure."
        )
    section["evidence"] = list(dict.fromkeys(evidence))
    section["verified_claims"] = section["evidence"]
    section["findings"] = list(dict.fromkeys(findings))
    section["secret_history_triage"] = {
        "version": SECRET_HISTORY_TRIAGE_VERSION,
        "history_scanners_completed": len(completed),
        "total_finding_count": total,
        "material_finding_count": material,
        "review_finding_count": review,
        "excluded_test_finding_count": excluded,
        "verified_finding_count": sum(_int(item.get("verified_finding_count")) for item in completed),
    }
    return section


SAFE_ATTACHMENT_FIELDS = (
    "execution_status",
    "execution_completed",
    "finding_count",
    "candidate_finding_count",
    "verified_finding_count",
    "total_finding_count",
    "material_finding_count",
    "review_finding_count",
    "excluded_test_finding_count",
    "full_history_covered",
    "history_commit_count",
    "history_depth",
    "snapshot_commit_sha",
    "triage_version",
)


def secret_history_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    if _ATTACHMENT_DELEGATE is None:
        raise RuntimeError("Secret-history attachment bridge is unavailable.")
    result = _ATTACHMENT_DELEGATE(context, outputs)
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result
    scanner_step = _dict(outputs.get("scanner_worker"))
    scan = _dict(scanner_step.get("scan"))
    raw = {
        str(item.get("scanner") or "").lower(): item
        for item in _list(scan.get("scanner_results"))
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() in _HISTORY_TOOLS
    }
    evidence = deepcopy(_dict(result.get("scanner_evidence") or result.get("evidence")))
    sanitized = [item for item in _list(evidence.get("scanner_results")) if isinstance(item, dict)]
    by_name = {str(item.get("scanner") or "").lower(): item for item in sanitized}
    for name, raw_item in raw.items():
        target = by_name.setdefault(name, {"scanner": name, "status": raw_item.get("status") or "unknown"})
        for field in SAFE_ATTACHMENT_FIELDS:
            if field in raw_item:
                target[field] = deepcopy(raw_item[field])
    evidence["scanner_results"] = list(by_name.values())
    evidence["secret_history_triage_version"] = SECRET_HISTORY_TRIAGE_VERSION
    output = dict(result)
    output["scanner_evidence"] = evidence
    output["evidence"] = evidence
    return output


def install_secret_history_triage() -> dict[str, Any]:
    global _DELEGATE_RUN_TOOL, _SECRETS_SECTION_DELEGATE, _ATTACHMENT_DELEGATE
    installed = bool(getattr(scanner_worker, "_nico_secret_history_triage_v2_installed", False))
    if not installed:
        _DELEGATE_RUN_TOOL = scanner_worker.run_tool
        _SECRETS_SECTION_DELEGATE = scorecard._secrets_section
        _ATTACHMENT_DELEGATE = snapshot_handlers._snapshot_evidence_attachment_handler
    scanner_worker.run_tool = secret_history_run_tool
    scorecard._secrets_section = secret_history_section_with_test_triage
    score_integrity.calibrated_secrets_section = secret_history_section_with_test_triage
    snapshot_handlers._snapshot_evidence_attachment_handler = secret_history_attachment_handler
    mid_handlers._snapshot_evidence_attachment_handler = secret_history_attachment_handler
    scanner_worker._nico_secret_history_triage_v2_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": SECRET_HISTORY_TRIAGE_VERSION,
        "tools": sorted(_HISTORY_TOOLS),
        "rule": "Verified findings remain material everywhere; unverified production history candidates remain score-bearing review items; unverified test/fixture paths remain disclosed but are excluded from production credential scoring.",
    }


__all__ = [
    "SECRET_HISTORY_TRIAGE_VERSION",
    "classify_history_findings",
    "install_secret_history_triage",
    "secret_history_section_with_test_triage",
]
