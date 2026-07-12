from __future__ import annotations

import html
from typing import Any

from nico.retainer_modules import build_retainer_modules
from nico.service_workflows import COVERAGE_TARGETS, now_iso, require_authorized


def _section(
    section_id: str,
    label: str,
    module: dict[str, Any],
    *,
    detail_items: list[str] | None = None,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    calculated = bool(module.get("score_calculated"))
    score = int(module.get("score") or 0) if calculated else 0
    return {
        "id": section_id,
        "label": label,
        "score": max(0, min(100, score)),
        "score_calculated": calculated,
        "status": str(module.get("status") or "unverified"),
        "summary": str(module.get("summary") or ""),
        "evidence": [str(item) for item in module.get("evidence") or []]
        + [str(item) for item in detail_items or []],
        "findings": [str(item) for item in findings or []],
        "unavailable": [str(item) for item in module.get("unavailable") or []],
    }


def _maturity(sections: list[dict[str, Any]]) -> dict[str, Any]:
    calculated = [item for item in sections if item.get("score_calculated")]
    if not calculated:
        return {
            "level": "Unverified",
            "score": 0,
            "calculated": False,
            "summary": "No source-bound Retainer sections were available for a maturity calculation.",
        }
    score = round(sum(int(item.get("score") or 0) for item in calculated) / len(calculated))
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    return {
        "level": level,
        "score": score,
        "calculated": True,
        "calculated_section_count": len(calculated),
        "summary": "Evidence-bound Retainer maturity estimate across calculated sections only. Human review remains required.",
    }


def _evidence_readiness(sections: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(sections)
    calculated = sum(1 for item in sections if item.get("score_calculated"))
    source_complete = sum(
        1
        for item in sections
        if item.get("score_calculated") and not item.get("unavailable")
    )
    readiness = round((calculated / max(1, total)) * 100)
    return {
        "readiness_score": readiness,
        "calculated": calculated > 0,
        "calculated_sections": calculated,
        "source_complete_sections": source_complete,
        "total_sections": total,
        "missing_or_unverified_sections": total - calculated,
        "summary": "Retainer evidence readiness measures source-bound sections. Unverified sections do not receive placeholder scores.",
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# NICO Ongoing Product Engineering Retainer",
        "",
        f"Generated: {result.get('generated_at') or ''}",
        f"Repository: {result.get('repository') or 'Not bound'}",
        f"Observed commit: {result.get('source_binding', {}).get('observed_commit_sha') or 'Unavailable'}",
        f"Baseline run: {result.get('source_binding', {}).get('baseline', {}).get('run_id') or 'Not available'}",
        f"Target coverage: {result.get('target_coverage') or 'Not specified'}",
        "",
        "## Truth Boundary",
        "Scores appear only for sections with a bound evidence source. Empty fields do not prove a clean result. Final client delivery and business commitments require human review.",
        "",
        "## Sections",
    ]
    for item in result.get("sections") or []:
        score_text = f"{item.get('score')}/100" if item.get("score_calculated") else "score unavailable"
        lines.extend(
            [
                f"### {item.get('label')} - {str(item.get('status') or 'unverified').upper()} ({score_text})",
                str(item.get("summary") or ""),
                "Evidence:",
            ]
        )
        lines.extend(f"- {entry}" for entry in item.get("evidence") or [])
        if item.get("findings"):
            lines.append("Findings:")
            lines.extend(f"- {entry}" for entry in item.get("findings") or [])
        if item.get("unavailable"):
            lines.append("Unavailable:")
            lines.extend(f"- {entry}" for entry in item.get("unavailable") or [])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _attach_reports(result: dict[str, Any]) -> dict[str, Any]:
    markdown = _markdown(result)
    result["reports"] = {
        "markdown": markdown,
        "html": (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>NICO Retainer Report</title></head><body><pre>"
            + html.escape(markdown)
            + "</pre></body></html>"
        ),
    }
    return result


def build_truth_bound_retainer_ops(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = require_authorized(payload)
    if blocked:
        return blocked

    modules = build_retainer_modules(payload)
    weekly = modules["weekly_health"]
    backlog = modules["backlog_health"]
    release = modules["release_readiness"]
    monthly = modules["monthly_strategy"]
    blocker = modules["blocker_escalation"]

    weekly_details = list(weekly.get("what_changed") or [])[:30]
    backlog_details = list(backlog.get("issue_items") or [])[:30]
    release_details = (
        list(release.get("release_notes") or [])
        + list(release.get("deployment_evidence") or [])
    )[:30]
    monthly_details = (
        list(monthly.get("roadmap_progress") or [])
        + list(monthly.get("metrics") or [])
        + list(monthly.get("client_update_inputs") or [])
        + list(monthly.get("budget_priorities") or [])
    )[:30]
    blocker_details = list(blocker.get("blockers") or [])[:30]

    sections = [
        _section(
            "weekly_delivery",
            "Weekly Delivery Status",
            weekly,
            detail_items=[
                f"Reconciled weekly module score: {weekly.get('score')}/100."
                if weekly.get("score_calculated")
                else "Reconciled weekly module score: unavailable."
            ]
            + weekly_details,
            findings=list(weekly.get("what_needs_attention") or [])[:20],
        ),
        _section(
            "backlog_health",
            "Backlog Health",
            backlog,
            detail_items=[
                f"Reconciled backlog module score: {backlog.get('score')}/100."
                if backlog.get("score_calculated")
                else "Reconciled backlog module score: unavailable."
            ]
            + backlog_details,
        ),
        _section(
            "release_readiness",
            "Release Readiness",
            release,
            detail_items=[
                f"Reconciled release module score: {release.get('score')}/100."
                if release.get("score_calculated")
                else "Reconciled release module score: unavailable."
            ]
            + release_details,
            findings=blocker_details,
        ),
        _section(
            "monthly_strategy",
            "Monthly Strategy",
            monthly,
            detail_items=[
                f"Reconciled strategy module score: {monthly.get('score')}/100."
                if monthly.get("score_calculated")
                else "Reconciled strategy module score: unavailable."
            ]
            + monthly_details,
        ),
        _section(
            "blockers",
            "Blockers / Approval Needs",
            blocker,
            detail_items=[
                f"Reconciled blocker module score: {blocker.get('score')}/100."
                if blocker.get("score_calculated")
                else "Reconciled blocker module score: unavailable."
            ],
            findings=blocker_details,
        ),
    ]

    maturity = _maturity(sections)
    approval_queue = [
        f"{item['gate']}: {item['reason']}"
        for item in modules.get("approval_gates") or []
        if isinstance(item, dict)
    ]
    approval_queue.extend(blocker_details[:8])
    source_binding = payload.get("source_binding") if isinstance(payload.get("source_binding"), dict) else {}
    ingestion = payload.get("retainer_evidence_ingestion") if isinstance(payload.get("retainer_evidence_ingestion"), dict) else {}

    result = {
        "status": modules.get("status") or "needs_more_retainer_evidence",
        "workflow": "ongoing_product_engineering_retainer",
        "target_coverage": COVERAGE_TARGETS["retainer"],
        "generated_at": now_iso(),
        "repository": payload.get("repository") or source_binding.get("repository") or "",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "client_name": payload.get("client_name") or "",
        "project_name": payload.get("project_name") or "",
        "maturity_signal": maturity,
        "evidence_readiness": _evidence_readiness(sections),
        "maturity_semaphore": {item["label"]: item["status"] for item in sections},
        "sections": sections,
        "retainer_modules": modules,
        "retainer_evidence_ingestion": ingestion,
        "source_binding": source_binding,
        "source_ledger": modules.get("source_ledger") or {},
        "weekly_status_report": list(weekly.get("next_actions") or [])
        + [
            "What changed: use only the verified commit, pull-request, issue, workflow, release, and deployment ledger.",
            "What is blocked: escalate verified blocker evidence and keep unavailable sources disclosed.",
            "What is next: combine repository evidence with the operator-approved roadmap and business priorities.",
        ],
        "monthly_strategy_report": list(monthly.get("next_focus") or []),
        "release_checklist": list(release.get("required_checks") or []),
        "human_approval_queue": approval_queue,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "safety_boundary": "Retainer Ops is evidence-bound and advisory. Production actions, client communication, roadmap commitments, and material scope, budget, or timeline changes require human approval.",
    }
    return _attach_reports(result)


__all__ = ["build_truth_bound_retainer_ops"]
