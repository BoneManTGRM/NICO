from __future__ import annotations

from typing import Any

MAX_TARGETS = {
    "express": 95,
    "mid": 85,
    "retainer": 70,
    "client_ready": 85,
}

REQUIRED_GATES = {
    "express": [
        "repository_access",
        "code_audit",
        "dependency_review",
        "ci_cd_review",
        "architecture_debt",
        "maturity_semaphore",
        "work_vs_expected",
        "action_plan",
        "resourcing_plan",
        "final_review_target",
        "report_package",
        "human_review",
    ],
    "mid": [
        "technical_audit",
        "qa_review",
        "platform_parity",
        "stakeholder_inputs",
        "risk_register",
        "six_month_roadmap",
        "resourcing_plan",
        "executive_review",
    ],
    "retainer": [
        "roadmap_backlog",
        "sprint_cadence",
        "release_readiness",
        "blocker_tracking",
        "approval_queue",
        "weekly_status",
        "quality_traceability",
        "client_communication",
    ],
    "client_ready": [
        "persistent_storage",
        "stable_run_id",
        "final_review_url",
        "final_review_requested",
        "final_review_approved",
        "assessment_rerun_after_approval",
        "client_acceptance_green",
        "report_exports",
        "delivery_notes",
    ],
}

NEXT_ACTIONS = {
    "repository_access": "Confirm read-only repository access and authorization scope.",
    "code_audit": "Run Express code audit with commit and PR evidence.",
    "dependency_review": "Attach dependency/library evidence and known-risk review.",
    "ci_cd_review": "Attach CI/CD configuration, logs, and release reliability evidence.",
    "architecture_debt": "Generate architecture and technical-debt findings.",
    "maturity_semaphore": "Generate red/yellow/green maturity semaphore by assessment area.",
    "work_vs_expected": "Generate Work vs Expected maturity classification.",
    "action_plan": "Generate quick wins and medium-term recommendations.",
    "resourcing_plan": "Generate Product Engineering Architect, Product Engineer, and Product Quality resourcing recommendation.",
    "final_review_target": "Attach run-scoped final-review URL.",
    "report_package": "Build final Markdown/HTML/PDF or JSON report package.",
    "human_review": "Keep final delivery blocked until a human reviewer approves.",
    "technical_audit": "Reuse Express technical audit as the Mid technical foundation.",
    "qa_review": "Collect QA evidence for iOS/Android behavior, critical bugs, and friction points.",
    "platform_parity": "Generate iOS/Android parity checklist and findings.",
    "stakeholder_inputs": "Collect stakeholder interview notes, pain points, goals, and desired states.",
    "risk_register": "Build product and technical risk register from QA, parity, and stakeholder inputs.",
    "six_month_roadmap": "Generate six-month roadmap with milestones, priorities, and execution recommendations.",
    "executive_review": "Prepare executive strategy review packet for human presentation.",
    "roadmap_backlog": "Create backlog health and roadmap traceability summary.",
    "sprint_cadence": "Create sprint cadence and delivery status evidence.",
    "release_readiness": "Track release readiness, blockers, approvals, and rollback status.",
    "blocker_tracking": "Track blockers, owners, aging, and next decisions.",
    "approval_queue": "Route risky actions through approval queue before execution.",
    "weekly_status": "Generate weekly status report with progress, risks, and next actions.",
    "quality_traceability": "Connect requirements, tickets, QA findings, and releases.",
    "client_communication": "Prepare client communication drafts while keeping send/approval human-controlled.",
    "persistent_storage": "Configure DATABASE_URL and confirm persistent storage is active.",
    "stable_run_id": "Rerun Express and confirm stable run_id is present.",
    "final_review_url": "Use the generated final-review URL for the exact run/customer/project scope.",
    "final_review_requested": "Request final review from the final-review page.",
    "final_review_approved": "Approve only after human evidence review.",
    "assessment_rerun_after_approval": "Rerun Express after approval so acceptance evidence can apply.",
    "client_acceptance_green": "Confirm Client / Human Acceptance is green in the rerun report.",
    "report_exports": "Export final client package in supported formats.",
    "delivery_notes": "Attach delivery notes, unavailable-data disclosure, and remaining human assumptions.",
}


def _text(payload: Any) -> str:
    if isinstance(payload, dict):
        return "\n".join(f"{key}: {_text(value)}" for key, value in payload.items())
    if isinstance(payload, list):
        return "\n".join(_text(item) for item in payload)
    return str(payload or "")


def _section(payload: dict[str, Any], section_id: str) -> dict[str, Any]:
    for item in payload.get("sections", []) or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return {}


def _has(payload: dict[str, Any], gate: str) -> bool:
    all_text = _text(payload).lower()
    acceptance = payload.get("client_acceptance") or {}
    final_review = payload.get("final_review") or {}
    storage = payload.get("storage") or {}
    reports = payload.get("reports") or {}
    express = payload.get("express_service_completion") or {}

    gate_rules = {
        "repository_access": bool(payload.get("repository") or payload.get("source_scope")),
        "code_audit": (_section(payload, "code_audit").get("score") or 0) >= 75,
        "dependency_review": (_section(payload, "dependency_health").get("score") or 0) >= 75,
        "ci_cd_review": (_section(payload, "ci_cd").get("score") or 0) >= 75,
        "architecture_debt": (_section(payload, "architecture_debt").get("score") or 0) >= 75,
        "maturity_semaphore": bool(payload.get("maturity_semaphore") or payload.get("maturity_signal")),
        "work_vs_expected": (_section(payload, "velocity_complexity").get("score") or 0) >= 75,
        "action_plan": bool(payload.get("next_steps")) or "quick win" in all_text or "action plan" in all_text,
        "resourcing_plan": bool(payload.get("resourcing_plan")) or "resourcing" in all_text or "product engineering" in all_text,
        "final_review_target": bool(final_review.get("run_id") and final_review.get("url")),
        "report_package": bool(reports.get("markdown") or reports.get("html") or reports.get("pdf_base64") or payload.get("report_id")),
        "human_review": acceptance.get("status") == "accepted" or payload.get("final_review_status") == "approved",
        "technical_audit": bool(payload.get("technical_audit")) or (_section(payload, "code_audit").get("score") or 0) >= 75,
        "qa_review": bool(payload.get("qa_checklist")) or "qa" in all_text,
        "platform_parity": bool(payload.get("parity_checklist")) or "parity" in all_text or "platform parity" in all_text,
        "stakeholder_inputs": "stakeholder" in all_text or bool(payload.get("stakeholder_notes")),
        "risk_register": "risk" in all_text or bool(payload.get("risk_register")),
        "six_month_roadmap": bool(payload.get("six_month_roadmap")) or "roadmap" in all_text,
        "executive_review": "executive" in all_text or "strategy review" in all_text,
        "roadmap_backlog": "backlog" in all_text or "roadmap" in all_text,
        "sprint_cadence": "sprint" in all_text,
        "release_readiness": bool(payload.get("release_readiness")) or "release" in all_text,
        "blocker_tracking": "blocker" in all_text,
        "approval_queue": "approval" in all_text or bool(payload.get("approval_queue")),
        "weekly_status": bool(payload.get("weekly_status_report")) or "weekly" in all_text,
        "quality_traceability": "traceability" in all_text or "quality" in all_text,
        "client_communication": "client" in all_text or "communication" in all_text,
        "persistent_storage": bool(storage.get("persistence_available")),
        "stable_run_id": bool(payload.get("run_id") or final_review.get("run_id")),
        "final_review_url": bool(final_review.get("url")),
        "final_review_requested": payload.get("final_review_status") in {"pending", "approved", "needs_more_evidence", "rejected"},
        "final_review_approved": payload.get("final_review_status") == "approved" or acceptance.get("status") == "accepted",
        "assessment_rerun_after_approval": acceptance.get("status") == "accepted",
        "client_acceptance_green": acceptance.get("status") == "accepted",
        "report_exports": bool(reports) or bool(payload.get("formats")),
        "delivery_notes": bool(payload.get("delivery_notes")) or bool(payload.get("unavailable_data_notes")) or express.get("rule"),
    }
    return bool(gate_rules.get(gate))


def service_coverage_gap(payload: dict[str, Any], service: str) -> dict[str, Any]:
    gates = REQUIRED_GATES[service]
    complete = [gate for gate in gates if _has(payload, gate)]
    missing = [gate for gate in gates if gate not in complete]
    target = MAX_TARGETS[service]
    current = round(len(complete) / len(gates) * target) if gates else 0
    return {
        "service": service,
        "target": target,
        "current": current,
        "gap": max(target - current, 0),
        "complete_count": len(complete),
        "total_count": len(gates),
        "complete": complete,
        "missing": missing,
        "next_actions": [{"gate": gate, "action": NEXT_ACTIONS[gate]} for gate in missing],
        "ready_for_max": current >= target and not missing,
        "rule": "Coverage gap uses evidence gates and max service targets. It does not auto-complete human review, stakeholder input, or client acceptance.",
    }


def service_coverage_gaps(payload: dict[str, Any]) -> dict[str, Any]:
    results = {service: service_coverage_gap(payload, service) for service in MAX_TARGETS}
    total_current = round(sum(item["current"] for item in results.values()) / len(results))
    total_target = round(sum(item["target"] for item in results.values()) / len(results))
    ordered_actions = []
    for service, item in results.items():
        for action in item["next_actions"]:
            ordered_actions.append({"service": service, **action})
    return {
        "status": "green" if total_current >= total_target else "yellow" if total_current >= 60 else "red",
        "overall_current": total_current,
        "overall_target": total_target,
        "overall_gap": max(total_target - total_current, 0),
        "services": results,
        "next_actions": ordered_actions,
        "rule": "Use this as the control system for reaching max coverage honestly across Express, Mid, Retainer, and client-ready delivery.",
    }
