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
    from nico.full_assessment_complexity_repository import collect_repository_complexity_evidence
    from nico.full_assessment_repository_evidence import collect_repository_evidence

    evidence_context = dict(context)
    evidence_context["timeframe_days"] = max(30, min(int(timeframe_days or 180), 365))
    bundle = dict(collect_repository_evidence(evidence_context))
    complexity = collect_repository_complexity_evidence(evidence_context)
    bundle["complexity_evidence"] = complexity
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
        "complexity_evidence_id": complexity.get("evidence_id") or "",
        "complexity_status": complexity.get("status") or "unavailable",
        "complexity_files_analyzed": complexity.get("files_analyzed", 0),
        "unavailable_data_notes": bundle.get("unavailable_data_notes") or [],
        "repository_evidence": bundle,
    }
    if not attached:
        return {
            "status": "unavailable",
            "message": "GitHub repository evidence could not be attached from the authorized read-only API scope; unavailable-data notes were preserved.",
            "repository_evidence": bundle,
            "complexity_evidence": complexity,
            "evidence": evidence,
        }
    return {
        "status": "complete",
        "message": "Read-only GitHub repository metadata, activity, workflow, dependency, architecture, file-profile, and bounded complexity evidence were attached to this full-run.",
        "repository_evidence": bundle,
        "complexity_evidence": complexity,
        "evidence": evidence,
    }


def _scanner_evidence(outputs: dict[str, Any]) -> dict[str, Any]:
    attachment = outputs.get("evidence_attachment") if isinstance(outputs.get("evidence_attachment"), dict) else {}
    return attachment.get("scanner_evidence") if isinstance(attachment.get("scanner_evidence"), dict) else {}


def _scanner_id(outputs: dict[str, Any]) -> str:
    return str(_scanner_evidence(outputs).get("scan_id") or "")


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

    from nico.full_assessment_trust_pipeline import (
        finalize_full_assessment_exports,
        prepare_full_assessment_trust,
    )
    from nico.reports import build_report_package

    scan_id = _scanner_id(outputs)
    trusted_assessment = prepare_full_assessment_trust(assessment, _scanner_evidence(outputs))
    identity = full_run_report_identity(context["run_id"], scan_id)
    package = build_report_package(
        trusted_assessment,
        report_id=identity["report_id"],
        idempotency_key=identity["idempotency_key"],
    )
    package["scan_id"] = scan_id
    finalized = finalize_full_assessment_exports(trusted_assessment, package)
    scoring["assessment"] = finalized["assessment"]
    package = finalized["package"]
    reports = finalized["reports"]
    reused = bool(package.get("idempotent_reuse"))
    gate = reports.get("export_truth_gate") if isinstance(reports.get("export_truth_gate"), dict) else {}
    return {
        "status": "complete",
        "message": "Existing same-run report package was reused and revalidated by trust gates." if reused else "Draft report package was generated and validated by the evidence ledger, strict trust engine, and Export Truth Gate.",
        "report_package": package,
        "reports": reports,
        "evidence": {
            "run_id": context["run_id"],
            "scan_id": scan_id,
            "report_id": package.get("report_id"),
            "idempotency_key": package.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
            "available_formats": [key for key, value in (package.get("formats") or {}).items() if value is not None],
            "trust_level": reports.get("trust_level") or "Review-limited",
            "evidence_ledger_status": reports.get("evidence_ledger_status") or "missing",
            "export_truth_gate_status": gate.get("status") or "pending",
            "client_delivery_allowed": False,
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
                "Evidence ledger, strict trust engine, and Export Truth Gate were applied before review request creation.",
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
        "message": "Existing same-report final-review request was reused; no duplicate approval was created." if reused else "Final human-review approval request was created for the trust-gated report package.",
        "approval": {
            "approval_id": approval.get("approval_id") or identity["approval_id"],
            "status": approval.get("status") or review.get("status") or "pending_review",
            "requested_action": approval.get("requested_action") or "final_report_approval",
            "run_id": approval.get("run_id") or context["run_id"],
            "report_id": approval.get("report_id") or report_id,
            "idempotency_key": approval.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
            "approver": approval.get("approver") or "",
            "review_validation": approval.get("review_validation") or {},
            "review_decision": approval.get("review_decision") or {},
        },
        "review": review.get("review") or {},
        "evidence": {
            "run_id": context["run_id"],
            "report_id": report_id,
            "approval_id": approval.get("approval_id") or identity["approval_id"],
            "idempotency_key": approval.get("idempotency_key") or identity["idempotency_key"],
            "idempotent_reuse": reused,
            "review_validation_status": str((approval.get("review_validation") or {}).get("status") or "missing"),
        },
    }


def idempotent_full_assessment_handlers(*, timeframe_days: int = 180) -> dict[str, Any]:
    from nico.full_assessment_scanner_contract import (
        full_assessment_evidence_attachment_handler,
        full_assessment_scanner_handler,
        full_assessment_scoring_with_scanner_truth_handler,
    )

    handlers = default_full_assessment_handlers()
    handlers["repo_evidence"] = lambda context, outputs: _repository_evidence_handler(
        context,
        outputs,
        timeframe_days=timeframe_days,
    )
    handlers["scanner_worker"] = full_assessment_scanner_handler
    handlers["evidence_attachment"] = full_assessment_evidence_attachment_handler
    handlers["scoring"] = full_assessment_scoring_with_scanner_truth_handler
    handlers["reports"] = _reports_handler
    handlers["approval_request"] = _approval_request_handler
    return handlers
