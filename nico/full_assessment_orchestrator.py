from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from nico.storage import new_id, utc_now

FULL_ASSESSMENT_STEPS = [
    "authorization",
    "repo_evidence",
    "scanner_worker",
    "evidence_attachment",
    "scoring",
    "reports",
    "approval_request",
]

DEFAULT_FULL_RUN_TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
]

StepHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


class FullAssessmentBlocked(ValueError):
    """Raised when the full-run request fails a safe preflight gate."""


def normalize_repository_target(payload: dict[str, Any]) -> str:
    """Normalize a GitHub owner/repo or GitHub URL into owner/repo form.

    This intentionally accepts only GitHub repository targets. The full-run
    orchestrator is an authorized defensive repository assessment workflow, not
    a generic URL scanner.
    """

    raw = str(payload.get("repository") or payload.get("target") or "").strip()
    raw = raw.removesuffix(".git").strip(" /")
    match = re.match(r"^https://github\.com/([^/]+)/([^/#?]+)", raw, re.IGNORECASE)
    if match:
        raw = f"{match.group(1)}/{match.group(2)}"
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", raw):
        return ""
    return raw


def _authorized(payload: dict[str, Any]) -> bool:
    return bool(payload.get("authorization_confirmed") or payload.get("authorized"))


def _base_context(payload: dict[str, Any]) -> dict[str, Any]:
    repository = normalize_repository_target(payload)
    return {
        "run_id": str(payload.get("run_id") or new_id("fullrun")),
        "scan_id": str(payload.get("scan_id") or ""),
        "repository": repository,
        "customer_id": str(payload.get("customer_id") or "default_customer"),
        "project_id": str(payload.get("project_id") or "default_project"),
        "client_name": str(payload.get("client_name") or ""),
        "project_name": str(payload.get("project_name") or ""),
        "authorized_by": str(payload.get("authorized_by") or "unspecified"),
        "authorization_scope": str(payload.get("authorization_scope") or "repository assessment only"),
        "mode": str(payload.get("mode") or "express"),
        "run_scanners": bool(payload.get("run_scanners", True)),
        "refresh_full_evidence": bool(payload.get("refresh_full_evidence", True)),
        "build_reports": bool(payload.get("build_reports", True)),
        "create_final_review_request": bool(payload.get("create_final_review_request", True)),
        "tools": payload.get("tools") if isinstance(payload.get("tools"), list) else DEFAULT_FULL_RUN_TOOLS,
        "created_at": utc_now(),
    }


def _progress(step: str, status: str, message: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"step": step, "status": status}
    if message:
        item["message"] = message
    if evidence:
        item["evidence"] = evidence
    return item


def _empty_response(context: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": context.get("run_id") or "",
        "repository": context.get("repository") or "",
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "mode": context.get("mode") or "express",
        "progress": [],
        "scanner": {"scan_id": context.get("scan_id") or "", "status": "not_started"},
        "scanner_evidence": {"status": "not_attached", "scan_id": context.get("scan_id") or ""},
        "assessment": {},
        "reports": {"markdown": "", "html": "", "pdf_base64": "", "pdf_filename": "nico-assessment.pdf", "pdf_error": ""},
        "approval": {"approval_id": "", "status": "not_requested"},
        "human_review_required": True,
        "client_ready": False,
        "generated_at": context.get("created_at") or utc_now(),
    }


def _repo_evidence_handler(context: dict[str, Any], _outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "complete",
        "message": "Repository target, customer/project scope, run_id, and authorization metadata are bound for this full-run.",
        "evidence": {
            "run_id": context["run_id"],
            "repository": context["repository"],
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "refresh_full_evidence": context["refresh_full_evidence"],
        },
    }


def _run_id_matches(scan: dict[str, Any], run_id: str) -> bool:
    scan_run_id = str(scan.get("run_id") or "")
    return not scan_run_id or not run_id or scan_run_id == run_id


def _scanner_worker_handler(context: dict[str, Any], _outputs: dict[str, Any]) -> dict[str, Any]:
    from nico.scanner_worker import get_scan, start_scan

    if context.get("scan_id"):
        scan = get_scan(context["scan_id"])
        if scan.get("status") == "not_found":
            return {
                "status": "unavailable",
                "message": "Requested scanner run was not found; completed scanner evidence cannot be attached.",
                "scan": scan,
                "evidence": {"run_id": context["run_id"], "scan_id": context["scan_id"]},
            }
        if not _run_id_matches(scan, context["run_id"]):
            return {
                "status": "blocked",
                "message": "Scanner run_id does not match the full-run id; evidence attachment is blocked.",
                "scan": scan,
                "evidence": {"run_id": context["run_id"], "scan_id": context["scan_id"], "scanner_run_id": scan.get("run_id")},
            }
        return {
            "status": scan.get("status") or "unknown",
            "message": "Existing scanner run was loaded for this full-run.",
            "scan": scan,
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": context["scan_id"],
                "tools_requested": scan.get("tools_requested", []),
                "customer_id": scan.get("customer_id"),
                "project_id": scan.get("project_id"),
            },
        }

    if not context.get("run_scanners"):
        return {
            "status": "skipped",
            "message": "Scanner worker was skipped by request; scoring must treat scanner evidence as unavailable.",
            "evidence": {"run_id": context["run_id"], "scanner_worker": "skipped"},
        }

    scan = start_scan(
        {
            "repository": context["repository"],
            "authorized": True,
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "run_id": context["run_id"],
            "authorized_by": context["authorized_by"],
            "authorization_scope": context["authorization_scope"],
            "tools": context.get("tools") or DEFAULT_FULL_RUN_TOOLS,
        }
    )
    if scan.get("status") == "blocked":
        return {"status": "blocked", "message": str(scan.get("error") or "scanner worker blocked"), "scan": scan, "evidence": {"run_id": context["run_id"]}}
    return {
        "status": scan.get("status") or "queued",
        "message": "Scanner worker was queued and bound to the full-run id.",
        "scan": scan,
        "evidence": {
            "run_id": context["run_id"],
            "scan_id": scan.get("scan_id"),
            "tools_requested": scan.get("tools_requested", []),
            "customer_id": scan.get("customer_id"),
            "project_id": scan.get("project_id"),
        },
    }


def _summarize_completed_scanner_evidence(scan: dict[str, Any], run_id: str) -> dict[str, Any]:
    results = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    return {
        "status": "attached",
        "run_id": run_id,
        "scan_id": scan.get("scan_id") or "",
        "scanner_status": scan.get("status") or "unknown",
        "tools_requested": scan.get("tools_requested", []),
        "tools_run": scan.get("tools_run", []),
        "unavailable_tools": scan.get("unavailable_tools", []),
        "failed_tools": scan.get("failed_tools", []),
        "timed_out_tools": scan.get("timed_out_tools", []),
        "scanner_results_count": len(results),
        "evidence_summary": scan.get("evidence_summary") if isinstance(scan.get("evidence_summary"), dict) else {},
        "unavailable_data_notes": scan.get("unavailable_data_notes", []),
        "secret_redaction_applied": bool(scan.get("secret_redaction_applied")),
        "retention_note": scan.get("retention_note") or "Scanner evidence was read from the retained scanner record.",
        "human_review_required": True,
    }


def _evidence_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    scanner = outputs.get("scanner_worker") or {}
    scan = scanner.get("scan") if isinstance(scanner.get("scan"), dict) else {}
    scan_id = scan.get("scan_id") or context.get("scan_id")
    if not scan_id:
        return {
            "status": "skipped",
            "message": "No scanner run was created, so scanner artifact attachment remains unavailable for this run.",
            "evidence": {"run_id": context["run_id"], "scan_id": ""},
        }

    scanner_step_status = str(scanner.get("status") or "")
    if scanner_step_status in {"blocked", "failed", "unavailable"}:
        status = "failed" if scanner_step_status == "failed" else scanner_step_status
        return {
            "status": status,
            "message": "Scanner step did not provide attachable completed evidence.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": scanner_step_status},
        }

    scanner_status = str(scan.get("status") or "unknown")
    if scanner_status in {"queued", "running"}:
        return {
            "status": "pending",
            "message": "Scanner run exists but has not completed; scanner evidence remains pending.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": scanner_status},
        }
    if scanner_status == "complete":
        evidence = _summarize_completed_scanner_evidence(scan, context["run_id"])
        return {
            "status": "complete",
            "message": "Completed scanner evidence was attached to the full-run response.",
            "scanner_evidence": evidence,
            "evidence": evidence,
        }
    if scanner_status == "not_found":
        return {
            "status": "unavailable",
            "message": "Scanner run was not found; scanner evidence is unavailable.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": scanner_status},
        }
    if scanner_status in {"failed", "error", "blocked"}:
        return {
            "status": "failed" if scanner_status in {"failed", "error"} else "blocked",
            "message": "Scanner run did not complete successfully; scanner evidence was not attached as complete.",
            "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": scanner_status},
        }
    return {
        "status": "unavailable",
        "message": "Scanner run status is not attachable as completed evidence.",
        "evidence": {"run_id": context["run_id"], "scan_id": scan_id, "scanner_status": scanner_status},
    }


def _section_status(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 55:
        return "yellow"
    if score <= 0:
        return "gray"
    return "red"


def _scanner_score(scanner_evidence: dict[str, Any]) -> int:
    if scanner_evidence.get("status") != "attached":
        return 0
    requested = len(scanner_evidence.get("tools_requested") or [])
    run = len(scanner_evidence.get("tools_run") or [])
    unavailable = len(scanner_evidence.get("unavailable_tools") or [])
    failed = len(scanner_evidence.get("failed_tools") or [])
    timed_out = len(scanner_evidence.get("timed_out_tools") or [])
    if failed or timed_out:
        return 60
    if unavailable:
        return 72
    if requested and run >= requested:
        return 90
    if run:
        return 75
    return 45


def _scoring_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    attachment = outputs.get("evidence_attachment") or {}
    scanner_evidence = attachment.get("scanner_evidence") if isinstance(attachment.get("scanner_evidence"), dict) else attachment.get("evidence") or {}
    if scanner_evidence.get("status") != "attached":
        return {
            "status": "planned",
            "message": "Assessment scoring waits for completed same-run scanner evidence; no maturity score was generated from pending or unavailable scanner data.",
            "evidence": {"run_id": context["run_id"], "scanner_evidence_status": scanner_evidence.get("status") or "not_attached"},
        }

    score = _scanner_score(scanner_evidence)
    section = {
        "id": "scanner_evidence",
        "label": "Scanner Evidence Attachment",
        "score": score,
        "status": _section_status(score),
        "summary": "Completed same-run scanner evidence was attached and summarized for draft assessment scoring.",
        "evidence": [
            f"Scanner run {scanner_evidence.get('scan_id')} completed for full-run {context['run_id']}.",
            f"Tools requested={len(scanner_evidence.get('tools_requested') or [])}; tools run={len(scanner_evidence.get('tools_run') or [])}; unavailable={len(scanner_evidence.get('unavailable_tools') or [])}; failed={len(scanner_evidence.get('failed_tools') or [])}; timed out={len(scanner_evidence.get('timed_out_tools') or [])}.",
            scanner_evidence.get("retention_note") or "Scanner evidence was read from the retained scanner record.",
        ],
        "findings": [f"Scanner failed tools: {', '.join(scanner_evidence.get('failed_tools') or [])}"] if scanner_evidence.get("failed_tools") else [],
        "unavailable": list(scanner_evidence.get("unavailable_data_notes") or []),
        "confidence": "scanner-record-bound",
    }
    assessment = {
        "status": "draft",
        "run_id": context["run_id"],
        "repository": context["repository"],
        "customer_id": context["customer_id"],
        "project_id": context["project_id"],
        "client_name": context["client_name"],
        "project_name": context["project_name"],
        "source_scope": context["repository"],
        "authorization_statement": "Full-run assessment is valid only for the explicitly authorized repository/customer/project scope.",
        "executive_summary": "NICO attached completed same-run scanner evidence and generated a draft evidence-bound assessment package. Final client delivery still requires human review and approval.",
        "maturity_signal": {"level": "Evidence Attached", "score": score, "summary": "Draft score is based only on completed same-run scanner evidence attached to this full-run."},
        "client_delivery_verdict": {"status": "human_review_required", "confidence": "limited", "blockers": ["Final client delivery requires human review and approval."], "unavailable_items": len(section.get("unavailable") or [])},
        "sections": [section],
        "findings": section["findings"] or ["No scanner failure findings were attached from the completed scanner record."],
        "unavailable_data_notes": list(section.get("unavailable") or []),
        "next_steps": [
            "Review the attached scanner evidence and unavailable notes.",
            "Run full repository scoring/report generation after scanner evidence and GitHub metadata are both available.",
            "Request final human review before client delivery.",
        ],
        "truthfulness_rules": ["Completed evidence only", "Pending scanner records are not scored", "Client delivery requires human approval"],
        "human_review_required": True,
    }
    return {
        "status": "complete",
        "message": "Draft assessment scoring was generated from completed same-run scanner evidence.",
        "assessment": assessment,
        "evidence": {"run_id": context["run_id"], "score": score, "sections": 1},
    }


def _reports_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    if not context.get("build_reports"):
        return {"status": "skipped", "message": "Report generation was skipped by request.", "evidence": {"run_id": context["run_id"]}}
    scoring = outputs.get("scoring") or {}
    assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), dict) else {}
    if not assessment:
        return {
            "status": "planned",
            "message": "Report package waits for a draft assessment; no report was generated from missing or pending scoring evidence.",
            "evidence": {"run_id": context["run_id"], "assessment_status": scoring.get("status") or "not_available"},
        }

    from nico.reports import build_report_package

    package = build_report_package(assessment)
    formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
    reports = {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": "",
        "pdf_filename": "nico-assessment.pdf",
        "pdf_error": "PDF export is not produced by this report package path yet; Markdown, HTML, and JSON were generated.",
        "report_id": package.get("report_id") or "",
    }
    return {
        "status": "complete",
        "message": "Draft report package was generated from the evidence-bound assessment.",
        "report_package": package,
        "reports": reports,
        "evidence": {"run_id": context["run_id"], "report_id": package.get("report_id"), "available_formats": [key for key, value in formats.items() if value is not None]},
    }


def default_full_assessment_handlers() -> dict[str, StepHandler]:
    return {
        "repo_evidence": _repo_evidence_handler,
        "scanner_worker": _scanner_worker_handler,
        "evidence_attachment": _evidence_attachment_handler,
        "scoring": _scoring_handler,
        "reports": _reports_handler,
    }


def run_full_assessment_orchestration(
    payload: dict[str, Any],
    handlers: dict[str, StepHandler] | None = None,
) -> dict[str, Any]:
    """Run the one-click full-assessment pipeline.

    Missing handlers are marked ``planned`` rather than completed so NICO never
    claims evidence was collected, scanned, scored, exported, or approved when a
    real worker has not run yet.
    """

    context = _base_context(payload)
    response = _empty_response(context, "planned")
    handlers = handlers or {}

    if not context["repository"]:
        response["status"] = "blocked"
        response["progress"].append(_progress("authorization", "blocked", "A valid GitHub repository target in owner/repo form is required."))
        response["error"] = "valid repository target is required"
        return response

    if not _authorized(payload):
        response["status"] = "blocked"
        response["progress"].append(_progress("authorization", "blocked", "Authorization confirmation is required before assessment."))
        response["error"] = "authorization confirmation is required"
        return response

    response["progress"].append(
        _progress(
            "authorization",
            "complete",
            "Authorization was confirmed by the requester; final delivery still requires human review.",
            {"authorized_by": context["authorized_by"], "repository": context["repository"]},
        )
    )

    step_outputs: dict[str, Any] = {}
    for step in FULL_ASSESSMENT_STEPS[1:]:
        handler = handlers.get(step)
        if handler is None:
            response["progress"].append(_progress(step, "planned", "Step is defined in the orchestrator contract but is not wired in this PR."))
            continue
        try:
            output = handler(context, step_outputs) or {}
        except Exception:  # pragma: no cover - defensive orchestration boundary
            response["status"] = "failed"
            response["progress"].append(_progress(step, "failed", "Step failed; review server logs or authorized diagnostic evidence."))
            response["failed_step"] = step
            return response
        step_outputs[step] = output
        response["progress"].append(_progress(step, output.get("status", "complete"), output.get("message", ""), output.get("evidence") if isinstance(output.get("evidence"), dict) else None))

    if "scanner_worker" in step_outputs:
        response["scanner"] = step_outputs["scanner_worker"].get("scan") or response["scanner"]
    if "evidence_attachment" in step_outputs:
        response["scanner_evidence"] = step_outputs["evidence_attachment"].get("scanner_evidence") or step_outputs["evidence_attachment"].get("evidence") or response["scanner_evidence"]
    if "scoring" in step_outputs:
        response["assessment"] = step_outputs["scoring"].get("assessment") or step_outputs["scoring"].get("result") or {}
    if "reports" in step_outputs:
        response["reports"].update(step_outputs["reports"].get("reports") or {})
    if "approval_request" in step_outputs:
        response["approval"].update(step_outputs["approval_request"].get("approval") or {})

    statuses = [item.get("status") for item in response["progress"]]
    if all(status in {"complete", "skipped"} for status in statuses) and any(status == "complete" for status in statuses):
        response["status"] = "complete"
    elif any(status in {"queued", "running", "pending"} for status in statuses):
        response["status"] = "running"
    elif any(status in {"failed", "blocked"} for status in statuses):
        response["status"] = "failed"
    return response
