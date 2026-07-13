from __future__ import annotations

import json
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from nico import scanner_worker as base
from nico.full_assessment_complexity_score import full_assessment_scoring_with_complexity_handler
from nico.scanner_tool_runners import TOOL_SPECS, ScannerToolSpec, run_scanner_tool
from nico.storage import STORE
from nico.worker_execution import WorkerWorkspace


DEFAULT_FULL_SCANNERS = (
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

_SPEC_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
_CATEGORY_BY_TOOL = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
}
_SECTION_BY_CATEGORY = {
    "dependency": "dependency_health",
    "static": "static_analysis",
    "secret": "secrets_review",
}


def _requested_tools(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("tools")
    values = raw if isinstance(raw, list) and raw else list(DEFAULT_FULL_SCANNERS)
    result: list[str] = []
    for item in values:
        name = str(item or "").strip().lower()
        if name and name not in result:
            result.append(name)
    return result or list(DEFAULT_FULL_SCANNERS)


def _unavailable_tool(name: str, reason: str) -> dict[str, Any]:
    return {
        "tool": name,
        "status": "unavailable",
        "category": _CATEGORY_BY_TOOL.get(name, "unknown"),
        "reason": reason,
        "findings": [],
        "returncode": None,
        "timed_out": False,
        "output_truncated": False,
        "scans_git_history": name in {"gitleaks", "trufflehog"},
    }


def _failed_tool(spec: ScannerToolSpec, error: Exception) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "failed",
        "category": spec.category,
        "reason": f"{spec.name} failed safely inside the scanner worker: {type(error).__name__}",
        "findings": [],
        "returncode": None,
        "timed_out": False,
        "output_truncated": False,
        "scans_git_history": spec.scans_git_history,
    }


def _truthful_execution_state(result: dict[str, Any]) -> dict[str, Any]:
    item = dict(result)
    status = str(item.get("status") or "unknown").lower()
    findings = item.get("findings") if isinstance(item.get("findings"), list) else []
    returncode = item.get("returncode")
    if status == "completed" and returncode not in {None, 0} and not findings:
        item["status"] = "failed"
        item["reason"] = "The scanner returned a non-zero exit code without parseable finding evidence."
    item["finding_count"] = len(findings)
    item["completion_state"] = (
        "completed_with_findings"
        if item.get("status") == "completed" and findings
        else "completed_clean"
        if item.get("status") == "completed"
        else item.get("status")
    )
    return item


def _severity_name(finding: Any) -> str:
    if not isinstance(finding, dict):
        return "unknown"
    candidates = [
        finding.get("severity"),
        finding.get("level"),
        finding.get("issue_severity"),
        finding.get("confidence"),
        (finding.get("extra") or {}).get("severity") if isinstance(finding.get("extra"), dict) else None,
    ]
    text = " ".join(str(item or "").lower() for item in candidates)
    if any(token in text for token in ("critical", "verified", "error")):
        return "critical"
    if "high" in text:
        return "high"
    if any(token in text for token in ("medium", "moderate", "warning", "warn")):
        return "medium"
    if any(token in text for token in ("low", "info", "informational")):
        return "low"
    return "unknown"


def _finding_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: Counter[str] = Counter()
    by_tool: dict[str, int] = {}
    severity_by_category: dict[str, Counter[str]] = {}
    for item in results:
        findings = item.get("findings") if isinstance(item.get("findings"), list) else []
        if not findings:
            continue
        tool = str(item.get("tool") or "unknown")
        category = str(item.get("category") or _CATEGORY_BY_TOOL.get(tool, "unknown"))
        by_tool[tool] = len(findings)
        by_category[category] += len(findings)
        counts = severity_by_category.setdefault(category, Counter())
        for finding in findings:
            counts[_severity_name(finding)] += 1
    return {
        "total": sum(by_tool.values()),
        "by_tool": dict(sorted(by_tool.items())),
        "by_category": dict(sorted(by_category.items())),
        "severity_by_category": {
            category: dict(sorted(counts.items())) for category, counts in sorted(severity_by_category.items())
        },
    }


def _run_full_scan(scan_id: str, payload: dict[str, Any]) -> None:
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")
    requested = _requested_tools(payload)
    job = base.SCAN_JOBS[scan_id]
    job["status"] = "running"
    job["updated_at"] = base.now_iso()
    STORE.put("scanner_runs", scan_id, job)

    results: list[dict[str, Any]] = []
    unavailable_notes: list[str] = []
    repo_size = 0
    clone_available = False
    started = time.monotonic()

    import tempfile

    with tempfile.TemporaryDirectory(prefix="nico-full-scan-") as workspace_name:
        root = Path(workspace_name)
        env = base.clean_env(root)
        try:
            repo_path, clone_notes = base.clone_repository(str(payload.get("repository") or ""), root, env)
            unavailable_notes.extend(clone_notes)
            if repo_path:
                clone_available = True
                repo_size = base.directory_size(repo_path)
                workspace = WorkerWorkspace(root=root)
                for name in requested:
                    spec = _SPEC_BY_NAME.get(name)
                    if spec is None:
                        results.append(_unavailable_tool(name, "The requested scanner is not registered in NICO's controlled tool catalog."))
                        continue
                    try:
                        results.append(_truthful_execution_state(run_scanner_tool(spec, workspace)))
                    except Exception as exc:  # pragma: no cover - defensive per-tool boundary
                        results.append(_failed_tool(spec, exc))
            else:
                reason = "; ".join(clone_notes) or "Repository checkout was unavailable."
                results.extend(_unavailable_tool(name, reason) for name in requested)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            unavailable_notes.append(f"Full scanner worker failed safely: {type(exc).__name__}")
            results.extend(_unavailable_tool(name, "The repository scanner workspace could not be prepared.") for name in requested)

    completed = [str(item.get("tool")) for item in results if item.get("status") == "completed"]
    unavailable = [str(item.get("tool")) for item in results if item.get("status") == "unavailable"]
    failed = [str(item.get("tool")) for item in results if item.get("status") == "failed"]
    timed_out = [str(item.get("tool")) for item in results if item.get("status") == "timeout"]
    findings = _finding_summary(results)
    redaction_applied = "[REDACTED]" in json.dumps(results, sort_keys=True, default=str)

    job.update(
        {
            "status": "complete" if clone_available else "unavailable",
            "updated_at": base.now_iso(),
            "completed_at": base.now_iso(),
            "duration_seconds": round(time.monotonic() - started, 2),
            "run_id": payload.get("run_id") or job.get("run_id") or "",
            "tools_requested": requested,
            "tools_run": completed,
            "unavailable_tools": unavailable,
            "failed_tools": failed,
            "timed_out_tools": timed_out,
            "tools_with_findings": sorted(findings["by_tool"]),
            "finding_count": findings["total"],
            "finding_summary": findings,
            "scanner_results": results,
            "evidence_summary": {
                "mode": "controlled_full_assessment_scanner",
                "repository": payload.get("repository"),
                "run_id": payload.get("run_id") or job.get("run_id") or "",
                "repo_size_bytes": repo_size,
                "tools_requested": len(requested),
                "tools_run": len(completed),
                "unavailable_tools": len(unavailable),
                "failed_tools": len(failed),
                "timed_out_tools": len(timed_out),
                "finding_count": findings["total"],
                "finding_summary": findings,
            },
            "unavailable_data_notes": unavailable_notes,
            "secret_redaction_applied": redaction_applied,
            "redaction_policy_applied": True,
            "retention_note": "Temporary Full Assessment scan workspace was deleted after completion.",
            "human_review_required": True,
        }
    )
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit(
        "scanner.full_assessment_completed",
        {
            "scan_id": scan_id,
            "run_id": job.get("run_id"),
            "status": job.get("status"),
            "tools_requested": requested,
            "tools_run": completed,
            "finding_count": findings["total"],
        },
        customer_id=customer_id,
        project_id=project_id,
    )


def start_full_assessment_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before the Full Assessment scanner runs."}
    repository = str(payload.get("repository") or "")
    if not repository:
        return {"status": "blocked", "error": "repository is required."}
    authorized_by = str(payload.get("authorized_by") or "").strip()
    if not authorized_by or authorized_by.lower() == "unspecified":
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        base.safe_repo_url(repository)
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    requested = _requested_tools(payload)
    scan_id = f"scan_full_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "run_id": payload.get("run_id") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": repository,
        "status": "queued",
        "created_at": base.now_iso(),
        "updated_at": base.now_iso(),
        "authorized_by": authorized_by,
        "authorization_scope": payload.get("authorization_scope"),
        "code_modification_allowed": False,
        "draft_pr_creation_allowed": False,
        "tools_requested": requested,
        "tools_run": [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "tools_with_findings": [],
        "finding_count": 0,
        "finding_summary": {"total": 0, "by_tool": {}, "by_category": {}, "severity_by_category": {}},
        "max_repo_bytes": base.MAX_REPO_BYTES,
        "human_review_required": True,
    }
    base.SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit(
        "scanner.full_assessment_queued",
        {"scan_id": scan_id, "run_id": job.get("run_id"), "repository": repository, "tools_requested": requested},
        customer_id=job["customer_id"],
        project_id=job["project_id"],
    )
    threading.Thread(target=_run_full_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job


def get_full_assessment_scan(scan_id: str) -> dict[str, Any]:
    return base.SCAN_JOBS.get(scan_id) or STORE.get("scanner_runs", scan_id) or {"status": "not_found", "scan_id": scan_id}


def full_assessment_scanner_handler(context: dict[str, Any], _outputs: dict[str, Any]) -> dict[str, Any]:
    if context.get("scan_id"):
        scan = get_full_assessment_scan(str(context["scan_id"]))
        if scan.get("status") == "not_found":
            return {
                "status": "unavailable",
                "message": "Requested scanner run was not found; completed scanner evidence cannot be attached.",
                "scan": scan,
                "evidence": {"run_id": context["run_id"], "scan_id": context["scan_id"]},
            }
        scanner_run_id = str(scan.get("run_id") or "")
        if scanner_run_id and scanner_run_id != str(context.get("run_id") or ""):
            return {
                "status": "blocked",
                "message": "Scanner run_id does not match the Full Assessment run_id; evidence attachment is blocked.",
                "scan": scan,
                "evidence": {"run_id": context["run_id"], "scan_id": context["scan_id"], "scanner_run_id": scanner_run_id},
            }
        return {
            "status": scan.get("status") or "unknown",
            "message": "Existing scanner run was loaded for this Full Assessment.",
            "scan": scan,
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": context["scan_id"],
                "tools_requested": scan.get("tools_requested", []),
                "tools_run": scan.get("tools_run", []),
            },
        }

    if not context.get("run_scanners"):
        return {
            "status": "skipped",
            "message": "Scanner worker was skipped by request; scoring must treat scanner evidence as unavailable.",
            "evidence": {"run_id": context["run_id"], "scanner_worker": "skipped"},
        }

    scan = start_full_assessment_scan(
        {
            "repository": context["repository"],
            "authorized": True,
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "run_id": context["run_id"],
            "authorized_by": context["authorized_by"],
            "authorization_scope": context["authorization_scope"],
            "tools": context.get("tools") or list(DEFAULT_FULL_SCANNERS),
        }
    )
    if scan.get("status") == "blocked":
        return {
            "status": "blocked",
            "message": str(scan.get("error") or "Full Assessment scanner blocked"),
            "scan": scan,
            "evidence": {"run_id": context["run_id"]},
        }
    return {
        "status": scan.get("status") or "queued",
        "message": "Full Assessment scanner worker was queued with the exact requested tool contract.",
        "scan": scan,
        "evidence": {
            "run_id": context["run_id"],
            "scan_id": scan.get("scan_id"),
            "tools_requested": scan.get("tools_requested", []),
        },
    }


def full_assessment_evidence_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    scanner = outputs.get("scanner_worker") if isinstance(outputs.get("scanner_worker"), dict) else {}
    scan = scanner.get("scan") if isinstance(scanner.get("scan"), dict) else {}
    scan_id = str(scan.get("scan_id") or context.get("scan_id") or "")
    if not scan_id:
        return {
            "status": "skipped",
            "message": "No scanner run was created, so scanner evidence remains unavailable for this Full Assessment.",
            "evidence": {"run_id": context["run_id"], "scan_id": ""},
        }

    status = str(scan.get("status") or scanner.get("status") or "unknown")
    if status in {"queued", "running"}:
        return {
            "status": "pending",
            "message": "Scanner run exists but has not completed; same-run scanner evidence remains pending.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": status},
        }
    if status != "complete":
        return {
            "status": "failed" if status in {"failed", "error"} else status if status in {"blocked", "unavailable"} else "unavailable",
            "message": "Scanner run did not produce attachable completed evidence.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": status},
        }

    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    evidence = {
        "status": "attached",
        "run_id": context["run_id"],
        "scan_id": scan_id,
        "scanner_status": status,
        "tools_requested": list(scan.get("tools_requested") or []),
        "tools_run": list(scan.get("tools_run") or []),
        "unavailable_tools": list(scan.get("unavailable_tools") or []),
        "failed_tools": list(scan.get("failed_tools") or []),
        "timed_out_tools": list(scan.get("timed_out_tools") or []),
        "tools_with_findings": list(scan.get("tools_with_findings") or []),
        "finding_count": int(scan.get("finding_count") or 0),
        "finding_summary": summary,
        "scanner_results_count": len(scan.get("scanner_results") or []),
        "evidence_summary": scan.get("evidence_summary") if isinstance(scan.get("evidence_summary"), dict) else {},
        "unavailable_data_notes": list(scan.get("unavailable_data_notes") or []),
        "secret_redaction_applied": bool(scan.get("secret_redaction_applied")),
        "redaction_policy_applied": bool(scan.get("redaction_policy_applied")),
        "retention_note": scan.get("retention_note") or "Scanner evidence was read from the retained scanner record.",
        "human_review_required": True,
    }
    return {
        "status": "complete",
        "message": "Completed scanner evidence, exact requested-tool coverage, and parsed finding counts were attached to this Full Assessment.",
        "scanner_evidence": evidence,
        "evidence": evidence,
    }


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict) and item.get("id")
    }


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _recompute_score(assessment: dict[str, Any]) -> None:
    from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS

    sections = _section_map(assessment)
    weighted = 0
    total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section or section.get("status") == "gray":
            continue
        weighted += int(section.get("score") or 0) * weight
        total += weight
    score = round(weighted / total) if total else 0
    signal = assessment.setdefault("maturity_signal", {})
    signal["score"] = score
    signal["level"] = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    signal["summary"] = "Weighted technical score includes explicit scanner finding caps; tool execution coverage is not treated as a clean result."
    scorecard = assessment.setdefault("scorecard", {})
    scorecard["technical_score"] = score
    scorecard["scanner_finding_truth_applied"] = True


def apply_scanner_finding_truth(assessment: dict[str, Any], scanner_evidence: dict[str, Any]) -> dict[str, Any]:
    summary = scanner_evidence.get("finding_summary") if isinstance(scanner_evidence.get("finding_summary"), dict) else {}
    by_category = summary.get("by_category") if isinstance(summary.get("by_category"), dict) else {}
    severities = summary.get("severity_by_category") if isinstance(summary.get("severity_by_category"), dict) else {}
    sections = _section_map(assessment)
    changed = False

    for category, section_id in _SECTION_BY_CATEGORY.items():
        count = int(by_category.get(category) or 0)
        if count <= 0:
            continue
        section = sections.get(section_id)
        if not section:
            continue
        category_severity = severities.get(category) if isinstance(severities.get(category), dict) else {}
        high_or_critical = int(category_severity.get("high") or 0) + int(category_severity.get("critical") or 0)
        previous = int(section.get("score") or 0)
        cap = 54 if high_or_critical else 79
        revised = min(previous, cap)
        section["score"] = revised
        section["status"] = "green" if revised >= 80 else "yellow" if revised >= 55 else "red"
        section["confidence"] = "scanner-findings-require-human-triage"
        evidence = section.setdefault("evidence", [])
        _append_unique(evidence, f"Full Assessment scanners reported {count} {category} item(s); high/critical classification count={high_or_critical}.")
        section["verified_claims"] = list(evidence)
        findings = section.setdefault("findings", [])
        _append_unique(findings, f"Triage {count} scanner-reported {category} item(s) before treating this section as clean or client-ready.")
        breakdown = section.setdefault("score_evidence_breakdown", {})
        breakdown["scanner_finding_pre_cap_score"] = previous
        breakdown["scanner_finding_cap"] = cap
        breakdown["scanner_finding_final_score"] = revised
        breakdown["scanner_finding_count"] = count
        breakdown["scanner_high_or_critical_count"] = high_or_critical
        changed = True

    scorecard = assessment.setdefault("scorecard", {})
    scorecard["scanner_finding_summary"] = summary
    scorecard["scanner_finding_truth_applied"] = changed
    if changed:
        top_findings = assessment.setdefault("findings", [])
        _append_unique(top_findings, f"Scanner tools reported {int(summary.get('total') or 0)} item(s) requiring human triage; execution completion was not treated as a clean result.")
        _recompute_score(assessment)
    return assessment


def full_assessment_scoring_with_scanner_truth_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    result = full_assessment_scoring_with_complexity_handler(context, outputs)
    if result.get("status") != "complete" or not isinstance(result.get("assessment"), dict):
        return result
    attachment = outputs.get("evidence_attachment") if isinstance(outputs.get("evidence_attachment"), dict) else {}
    scanner_evidence = attachment.get("scanner_evidence") if isinstance(attachment.get("scanner_evidence"), dict) else {}
    result["assessment"] = apply_scanner_finding_truth(result["assessment"], scanner_evidence)
    scorecard = result["assessment"].get("scorecard") if isinstance(result["assessment"].get("scorecard"), dict) else {}
    result.setdefault("evidence", {})["scanner_finding_truth_applied"] = bool(scorecard.get("scanner_finding_truth_applied"))
    result["evidence"]["scanner_finding_count"] = int((scorecard.get("scanner_finding_summary") or {}).get("total") or 0)
    return result
