from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from nico.qa_parity_intake import build_qa_parity_intake
from nico.retainer_modules import build_retainer_modules
from nico.roadmap_generator import build_six_month_roadmap
from nico.stakeholder_discovery import build_stakeholder_discovery


COVERAGE_TARGETS = {
    "express": "90-95%",
    "mid": "75-85%",
    "retainer": "55-70%",
    "client_ready_with_human_review": "75-85%",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def status(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def section(section_id: str, label: str, score: int, summary: str, evidence: list[str], findings: list[str] | None = None, unavailable: list[str] | None = None) -> dict[str, Any]:
    score = max(0, min(100, int(score)))
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": status(score),
        "summary": summary,
        "evidence": evidence,
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def require_authorized(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("authorized"):
        return None
    return {
        "status": "blocked",
        "error": "Explicit authorization is required before NICO runs this workflow.",
        "safety_boundary": "Defensive-only, authorized systems only, read-only by default, human approval for production-impacting actions.",
    }


def maturity(sections: list[dict[str, Any]]) -> dict[str, Any]:
    score = round(sum(item["score"] for item in sections) / len(sections)) if sections else 0
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    return {"level": level, "score": score, "summary": "Evidence-bound maturity estimate. Final client-facing conclusions require human review."}


def evidence_gap_score(sections: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(sections)
    complete = sum(1 for item in sections if item.get("evidence") and not item.get("unavailable"))
    partial = sum(1 for item in sections if item.get("evidence") and item.get("unavailable"))
    missing = sum(1 for item in sections if not item.get("evidence") or item.get("unavailable"))
    readiness = round(((complete + partial * 0.5) / max(1, total)) * 100)
    return {
        "readiness_score": readiness,
        "complete_sections": complete,
        "partial_sections": partial,
        "missing_or_blocked_sections": missing,
        "summary": "Evidence readiness measures whether NICO has enough supplied proof to support the workflow without inventing facts.",
    }


def build_markdown_report(result: dict[str, Any]) -> str:
    title = result.get("workflow", "nico_workflow").replace("_", " ").title()
    lines_out = [
        f"# NICO {title}",
        "",
        f"Generated: {result.get('generated_at', '')}",
        f"Client: {result.get('client_name') or 'Not specified'}",
        f"Project: {result.get('project_name') or 'Not specified'}",
        f"Target coverage: {result.get('target_coverage') or 'Not specified'}",
        "",
        "## Human Review Requirement",
        "NICO drafts evidence-bound workflow output. Final client-facing delivery, roadmap commitments, and resourcing decisions require human review.",
        "",
        "## Maturity Signal",
        f"{result.get('maturity_signal', {}).get('level', 'Unknown')} - {result.get('maturity_signal', {}).get('score', 0)}/100",
        "",
        "## Evidence Readiness",
        f"{result.get('evidence_readiness', {}).get('readiness_score', 0)}/100",
        "",
        "## Sections",
    ]
    for item in result.get("sections", []):
        lines_out += [
            f"### {item['label']} - {item['status'].upper()} ({item['score']}/100)",
            item["summary"],
            "Evidence:",
        ]
        lines_out.extend([f"- {entry}" for entry in item.get("evidence", [])])
        if item.get("findings"):
            lines_out.append("Findings:")
            lines_out.extend([f"- {entry}" for entry in item.get("findings", [])])
        if item.get("unavailable"):
            lines_out.append("Unavailable:")
            lines_out.extend([f"- {entry}" for entry in item.get("unavailable", [])])
        lines_out.append("")
    for key, label in [
        ("qa_checklist", "QA Checklist"),
        ("parity_checklist", "Parity Checklist"),
        ("six_month_roadmap", "Six-Month Roadmap"),
        ("weekly_status_report", "Weekly Status Report"),
        ("monthly_strategy_report", "Monthly Strategy Report"),
        ("release_checklist", "Release Checklist"),
        ("human_approval_queue", "Human Approval Queue"),
    ]:
        values = result.get(key)
        if values:
            lines_out += [f"## {label}"]
            lines_out.extend([f"- {entry}" for entry in values])
            lines_out.append("")
    return "\n".join(lines_out).strip() + "\n"


def build_html_report(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>NICO Workflow Report</title><style>body{{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;line-height:1.55;color:#111827}}pre{{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;padding:24px}}</style></head>
<body><pre>{safe}</pre></body>
</html>"""


def attach_reports(result: dict[str, Any]) -> dict[str, Any]:
    markdown = build_markdown_report(result)
    result["reports"] = {"markdown": markdown, "html": build_html_report(markdown)}
    return result


def build_mid_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = require_authorized(payload)
    if blocked:
        return blocked

    qa = lines(payload.get("qa_evidence"))
    parity = lines(payload.get("parity_notes"))
    stakeholders = lines(payload.get("stakeholder_notes"))
    roadmap = lines(payload.get("roadmap_notes"))
    risks = lines(payload.get("known_risks"))
    qa_parity_intake = build_qa_parity_intake(payload)
    stakeholder_discovery = build_stakeholder_discovery(payload)
    roadmap_artifact = build_six_month_roadmap(payload, stakeholder_discovery=stakeholder_discovery, qa_parity_intake=qa_parity_intake)

    qa_score = 35 + min(40, len(qa) * 5)
    parity_score = 30 + min(45, len(parity) * 6)
    stakeholder_score = max(30 + min(45, len(stakeholders) * 5), int(stakeholder_discovery.get("readiness_score") or 0))
    roadmap_score = max(35 + min(40, len(roadmap) * 6), int(roadmap_artifact.get("readiness_score") or 0))
    risk_score = 78 if risks else 45

    sections = [
        section("qa_functional", "QA / Functional Review", qa_score, "QA score is based on supplied functional evidence, reproduction notes, pass/fail signals, and bug descriptions.", [f"QA evidence items supplied: {len(qa)}.", f"Structured QA intake status: {qa_parity_intake['status']} score={qa_parity_intake['readiness_score']}/100."] + qa[:12], [] if qa else ["No QA evidence supplied yet."], [] if qa else ["Screenshots, videos, test results, or reproduction steps are needed for stronger Mid coverage."]),
        section("platform_parity", "Platform Parity", parity_score, "Parity score is based on supplied iOS/Android or web/mobile comparison evidence.", [f"Parity evidence items supplied: {len(parity)}.", f"Platforms covered by structured intake: {qa_parity_intake['platforms_covered']}."] + parity[:12], [] if parity else ["No parity comparison evidence supplied yet."], [] if parity else ["Feature-by-feature platform walkthrough evidence is missing."]),
        section("stakeholder_discovery", "Stakeholder Discovery", stakeholder_score, "Discovery score is based on supplied business goals, pain points, desired outcomes, and constraints.", [f"Stakeholder evidence items supplied: {len(stakeholders)}.", f"Structured stakeholder discovery status: {stakeholder_discovery['status']} score={stakeholder_discovery['readiness_score']}/100."] + stakeholder_discovery.get("roadmap_inputs", []) + stakeholders[:12], [] if stakeholder_discovery.get("status") != "needs_more_discovery" else ["Stakeholder discovery is incomplete."], stakeholder_discovery.get("unavailable", [])),
        section("roadmap_planning", "Six-Month Roadmap Planning", roadmap_score, "Roadmap score is based on supplied milestones, priorities, dependencies, constraints, QA/parity state, and stakeholder discovery inputs.", [f"Roadmap evidence items supplied: {len(roadmap)}.", f"Generated roadmap status: {roadmap_artifact['status']} score={roadmap_artifact['readiness_score']}/100."] + roadmap_artifact.get("roadmap_summary", []) + roadmap[:8], [] if roadmap_artifact.get("status") != "needs_more_evidence" else ["Roadmap evidence is incomplete."], roadmap_artifact.get("unavailable", [])),
        section("risk_register", "Mid Risk Register", risk_score, "Risk score is based on explicit known-risk inputs and whether they are available for planning.", [f"Known risks supplied: {len(risks)}."] + risks[:12], [] if risks else ["Known product, technical, timeline, or team risks have not been supplied."]),
    ]
    mat = maturity(sections)
    result = {
        "status": "complete",
        "workflow": "mid_technical_health_assessment",
        "target_coverage": COVERAGE_TARGETS["mid"],
        "generated_at": now_iso(),
        "client_name": payload.get("client_name") or "",
        "project_name": payload.get("project_name") or "",
        "maturity_signal": mat,
        "evidence_readiness": evidence_gap_score(sections),
        "maturity_semaphore": {item["label"]: item["status"] for item in sections},
        "sections": sections,
        "qa_parity_intake": qa_parity_intake,
        "stakeholder_discovery": stakeholder_discovery,
        "six_month_roadmap_artifact": roadmap_artifact,
        "qa_checklist": [
            "Critical user flows tested",
            "Authentication/login/logout tested",
            "Error states tested",
            "Payment or subscription behavior tested if applicable",
            "Notifications tested if applicable",
            "Analytics and tracking expectations reviewed if applicable",
            "Regression-risk areas identified",
        ],
        "parity_checklist": [
            "Feature exists on each platform",
            "Same copy and labels",
            "Same permissions behavior",
            "Same error handling",
            "Same onboarding/account behavior",
            "Same payment or subscription behavior if applicable",
            "Same analytics or tracking expectations",
        ],
        "six_month_roadmap": roadmap_artifact.get("roadmap_summary", []),
        "human_review_required": True,
        "safety_boundary": "Defensive-only and evidence-bound. NICO does not replace stakeholder judgment or final consultant review.",
    }
    return attach_reports(result)


def build_retainer_ops(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = require_authorized(payload)
    if blocked:
        return blocked

    commits = lines(payload.get("commit_summary"))
    prs = lines(payload.get("pr_summary"))
    issues = lines(payload.get("issue_summary"))
    blockers = lines(payload.get("blockers"))
    releases = lines(payload.get("release_notes"))
    roadmap = lines(payload.get("roadmap_notes"))
    retainer = build_retainer_modules(payload)

    delivery_score = max(40 + min(40, (len(commits) + len(prs)) * 4), int(retainer["weekly_health"].get("score") or 0))
    backlog_score = 35 + min(40, len(issues) * 5)
    release_score = max(35 + min(40, len(releases) * 6), int(retainer["release_readiness"].get("score") or 0))
    strategy_score = max(35 + min(40, len(roadmap) * 5), int(retainer["monthly_strategy"].get("score") or 0))
    blocker_score = int(retainer["blocker_escalation"].get("score") or (88 if not blockers else max(45, 78 - len(blockers) * 5)))

    sections = [
        section("weekly_delivery", "Weekly Delivery Status", delivery_score, "Delivery status uses supplied commit and PR summaries plus structured retainer weekly-health evidence.", [f"Commit items: {len(commits)}.", f"PR items: {len(prs)}.", f"Retainer weekly health status: {retainer['weekly_health']['status']} score={retainer['weekly_health']['score']}/100."] + commits[:8] + prs[:8], [] if commits or prs else ["No delivery evidence supplied."], [] if commits or prs else ["Commit or PR evidence is needed for stronger delivery status."]),
        section("backlog_health", "Backlog Health", backlog_score, "Backlog health uses supplied issue, bug, and task evidence.", [f"Backlog/issue items: {len(issues)}."] + issues[:12], [] if issues else ["No backlog evidence supplied."], [] if issues else ["Issue or bug evidence is needed for stronger backlog scoring."]),
        section("release_readiness", "Release Readiness", release_score, "Release readiness uses supplied release notes plus structured release gates and blocker evidence.", [f"Release evidence items: {len(releases)}.", f"Retainer release readiness status: {retainer['release_readiness']['status']} score={retainer['release_readiness']['score']}/100."] + releases[:12], [] if releases else ["No release evidence supplied."], retainer.get("unavailable", [])),
        section("monthly_strategy", "Monthly Strategy", strategy_score, "Strategy score uses roadmap progress, metrics, client-update evidence, and business-context notes.", [f"Roadmap evidence items: {len(roadmap)}.", f"Retainer monthly strategy status: {retainer['monthly_strategy']['status']} score={retainer['monthly_strategy']['score']}/100."] + roadmap[:12], [] if roadmap else ["No roadmap progress evidence supplied."], [] if roadmap else ["Roadmap progress notes are needed for stronger strategy scoring."]),
        section("blockers", "Blockers / Approval Needs", blocker_score, "Blocker score reflects unresolved blockers, escalation needs, and approval gates.", [f"Blocker items: {len(blockers)}.", f"Retainer blocker escalation status: {retainer['blocker_escalation']['status']} score={retainer['blocker_escalation']['score']}/100."] + blockers[:12], blockers[:12]),
    ]
    mat = maturity(sections)
    approval_queue = [f"{item['gate']}: {item['reason']}" for item in retainer.get("approval_gates", [])]
    if blockers:
        approval_queue.extend(blockers[:8])

    result = {
        "status": "complete",
        "workflow": "ongoing_product_engineering_retainer",
        "target_coverage": COVERAGE_TARGETS["retainer"],
        "generated_at": now_iso(),
        "client_name": payload.get("client_name") or "",
        "project_name": payload.get("project_name") or "",
        "maturity_signal": mat,
        "evidence_readiness": evidence_gap_score(sections),
        "maturity_semaphore": {item["label"]: item["status"] for item in sections},
        "sections": sections,
        "retainer_modules": retainer,
        "weekly_status_report": retainer["weekly_health"].get("next_actions", []) + ["What changed: summarize commits, PRs, issues, releases, and bugs from supplied evidence.", "What is blocked: escalate blockers and approval needs.", "What is next: prioritize highest-risk repair and delivery tasks."],
        "monthly_strategy_report": retainer["monthly_strategy"].get("next_focus", []) + ["Roadmap progress", "Technical debt trend", "Release reliability", "Team velocity signal", "Next-month focus"],
        "release_checklist": retainer["release_readiness"].get("required_checks", []),
        "human_approval_queue": approval_queue,
        "human_review_required": True,
        "safety_boundary": "Retainer Ops is advisory by default. Production-impacting changes require human approval.",
    }
    return attach_reports(result)
