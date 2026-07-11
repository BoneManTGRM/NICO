from __future__ import annotations

from typing import Any

from nico.full_assessment_idempotency import (
    full_run_approval_identity,
    full_run_report_identity,
)
from nico.full_assessment_orchestrator import default_full_assessment_handlers


def _repository_evidence_handler(
    context: dict[str, Any],
    _outputs: dict[str, Any],
    *,
    timeframe_days: int = 180,
) -> dict[str, Any]:
    from nico.full_assessment_repository_evidence import collect_repository_evidence

    evidence_context = dict(context)
    evidence_context["timeframe_days"] = max(30, min(int(timeframe_days or 180), 365))
    bundle = collect_repository_evidence(evidence_context)
    attached = bundle.get("status") == "attached"
    metadata = bundle.get("repository_metadata") if isinstance(bundle.get("repository_metadata"), dict) else {}
    activity = bundle.get("activity_evidence") if isinstance(bundle.get("activity_evidence"), dict) else {}
    workflows = bundle.get("workflow_evidence") if isinstance(bundle.get("workflow_evidence"), dict) else {}
    dependencies = bundle.get("dependency_evidence") if isinstance(bundle.get("dependency_evidence"), dict) else {}
    file_evidence = bundle.get("file_evidence") if isinstance(bundle.get("file_evidence"), dict) else {}
    evidence = {
        "run_id": context["run_id"],
        "repository": context["repository"],
        "customer_id": context["customer_id"],
        "project_id": context["project_id"],
        "evidence_id": bundle.get("evidence_id") or "",
        "source": bundle.get("source") or "github_api_read_only",
        "status": bundle.get("status") or "unavailable",
        "timeframe_days": bundle.get("timeframe_days") or evidence_context["timeframe_days"],
        "idempotent_reuse": bool(bundle.get("idempotent_reuse")),
        "default_branch": metadata.get("default_branch") or "",
        "files_profiled": file_evidence.get("files_profiled", 0),
        "commits_returned": activity.get("commits_returned", 0),
        "pull_requests_returned": activity.get("pull_requests_returned", 0),
        "workflow_file_count": workflows.get("workflow_file_count", 0),
        "workflow_run_count": workflows.get("workflow_run_count", 0),
        "dependency_entries": dependencies.get("dependency_entries", 0),
        "unavailable_data_notes": bundle.get("unavailable_data_notes") or [],
        "repository_evidence": bundle,
    }
    if not attached:
        return {
            "status": "unavailable",
            "message": "GitHub repository evidence could not be attached from the authorized read-only API scope; unavailable-data notes were preserved.",
            "repository_evidence": bundle,
            "evidence": evidence,
        }
    return {
        "status": "complete",
        "message": "Read-only GitHub repository metadata, activity, workflow, dependency, architecture, and file-profile evidence were attached to this full-run.",
        "repository_evidence": bundle,
        "evidence": evidence,
    }


def _scanner_id(outputs: dict[str, Any]) -> str:
    attachment = outputs.get("evidence_attachment") if isinstance(outputs.get("evidence_attachment"), dict) else {}
    scanner_evidence = attachment.get("scanner_evidence") if isinstance(attachment.get("scanner_evidence"), dict) else attachment.get("evidence") or {}
    return str(scanner_evidence.get("scan_id") or "")


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

    scan_id = _scanner_id(outputs)
    identity = full_run_report_identity(context["run_id"], scan_id)
    package = build_report_package(
        assessment,
        report_id=identity["report_id"],
        idempotency_key=identity["idempotency_key"],
    )
    formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
    reused = bool(package.get("idempotent_reuse"))
    reports = {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": "",
        "pdf_filename": "nico-assessment.pdf",
        "pdf_error": "PDF export is not produced by this report package path; Markdown, HTML, and JSON were generated.",
        "report_id": package.get("report_id") or "",
        "idempotency_key": package.get("idempotency_key") or identity["idempotency_key"],
        "idempotent_reuse": reused,
        "scan_id": scan_id,
    }
    return {
        "status": "complete",
        "message": "Existing same-run report package was reused; no duplicate report was created." if reused else "Draft report package was generated from the evidence-bound assessment.",
        "report_package": package,
        "reports": reports,
        "evidence": {
            "run_id": context["run_id"],
            "scan_id": scan_id,
            "report_id": package.get("report_id"),
            "idempotency_key": package.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
            "available_formats": [key for key, value in formats.items() if value is not None],
        },
    }


def _approval_request_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    if not context.get("create_final_review_request"):
        return {"status": "skipped", "message": "Final review request was skipped by request.", "evidence": {"run_id": context["run_id"]}}

    reports = outputs.get("reports") or {}
    report_package = reports.get("report_package") if isinstance(reports.get("report_package"), dict) else {}
    report_id = str(report_package.get("report_id") or "")
    if not report_id:
        return {
            "status": "planned",
            "message": "Final review request waits for a generated report package.",
            "evidence": {"run_id": context["run_id"], "report_id": "", "report_status": reports.get("status") or "not_available"},
        }

    from nico.final_review_workflow import request_final_review

    identity = full_run_approval_identity(context["run_id"], report_id)
    review = request_final_review(
        {
            "approval_id": identity["approval_id"],
            "idempotency_key": identity["idempotency_key"],
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "run_id": context["run_id"],
            "report_id": report_id,
            "repository": context["repository"],
            "requester": "nico-full-run",
            "risk_level": "delivery_review",
            "evidence": [
                f"Full-run report package generated for run_id={context['run_id']}.",
                f"Report package id={report_id}.",
                "Client delivery remains blocked until a human reviewer approves the final report.",
            ],
        }
    )
    approval = review.get("approval") if isinstance(review.get("approval"), dict) else {}
    if review.get("status") == "blocked":
        return {
            "status": "blocked",
            "message": "Final review request was blocked; human investigation is required.",
            "approval": approval,
            "evidence": {"run_id": context["run_id"], "report_id": report_id},
        }

    reused = bool(review.get("idempotent_reuse") or approval.get("idempotent_reuse"))
    return {
        "status": "complete",
        "message": "Existing same-report final-review request was reused; no duplicate approval was created." if reused else "Final human-review approval request was created for the generated report package.",
        "approval": {
            "approval_id": approval.get("approval_id") or identity["approval_id"],
            "status": approval.get("status") or review.get("status") or "pending_review",
            "requested_action": approval.get("requested_action") or "final_report_approval",
            "run_id": approval.get("run_id") or context["run_id"],
            "report_id": approval.get("report_id") or report_id,
            "idempotency_key": approval.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
        },
        "review": review.get("review") or {},
        "evidence": {
            "run_id": context["run_id"],
            "report_id": report_id,
            "approval_id": approval.get("approval_id") or identity["approval_id"],
            "idempotency_key": approval.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
        },
    }


def idempotent_full_assessment_handlers(*, timeframe_days: int = 180) -> dict[str, Any]:
    handlers = default_full_assessment_handlers()
    handlers["repo_evidence"] = lambda context, outputs: _repository_evidence_handler(
        context,
        outputs,
        timeframe_days=timeframe_days,
    )
    handlers["reports"] = _reports_handler
    handlers["approval_request"] = _approval_request_handler
    return handlers
