from __future__ import annotations

from copy import deepcopy
from typing import Any

SERVICE_TIER_WORKFLOWS: dict[str, dict[str, Any]] = {
    "express": {
        "label": "Express Technical Health Assessment",
        "duration": "2 weeks",
        "price_anchor": "$4,500 USD + IVA",
        "one_click_goal": "Run a fast, evidence-bound technical health report from repository, dependency, CI/CD, architecture, and velocity signals.",
        "scope": [
            "Code audit from recent pull requests, commits, and source structure.",
            "Dependency/library ecosystem review with scanner artifacts and OSV/pip/npm evidence.",
            "CI/CD analysis from workflows, build checks, logs, and release signals.",
            "Architecture and technical-debt review from repository structure and risk patterns.",
        ],
        "required_inputs": [
            "Authorized read-only repository access.",
            "CI/CD configuration and workflow logs when available.",
            "Essential technical documentation when available.",
            "Optional 30-60 minute Q&A context after the automated run.",
        ],
        "automation_steps": [
            "Validate authorization and repository target.",
            "Run hosted scanner worker and attach dependency/static/security evidence.",
            "Build the scorecard, score lift plan, Markdown/HTML/PDF, and human-review gate.",
            "Return client-ready draft report only after truth guards and final QA pass.",
        ],
        "deliverables": [
            "Maturity semaphore by area.",
            "Work-vs-expected maturity classification.",
            "Quick wins and medium-term action plan.",
            "Resourcing recommendation.",
        ],
    },
    "mid": {
        "label": "Mid Technical Health Assessment",
        "duration": "6 weeks",
        "price_anchor": "$14,000 USD + IVA",
        "one_click_goal": "Start the same easy assessment flow as Express, then expand it into QA, parity, stakeholder discovery, and a 6-month roadmap.",
        "scope": [
            "All Express technical audit areas.",
            "QA and functional testing review.",
            "Platform parity review for iOS/Android or configured platform targets.",
            "Stakeholder discovery and pain-point capture.",
            "Strategic 6-month roadmap and execution structure.",
        ],
        "required_inputs": [
            "Everything required for Express.",
            "Stakeholder availability for discovery sessions.",
            "Product/platform test access, QA notes, or bug tracker exports.",
            "Business goals, desired outcomes, and roadmap constraints.",
        ],
        "automation_steps": [
            "Run the Express evidence engine as the Week 1-2 baseline.",
            "Create QA/parity checklist tasks and missing-evidence requests.",
            "Capture stakeholder interview notes or uploaded summaries.",
            "Generate roadmap milestones, risk register, resourcing plan, and executive review packet.",
        ],
        "deliverables": [
            "Detailed technical report.",
            "QA and parity findings.",
            "Six-month strategic roadmap.",
            "Formal resourcing plan and retainer transition path.",
        ],
    },
    "retainer": {
        "label": "Ongoing Product Engineering Retainer",
        "duration": "Monthly",
        "price_anchor": "TBD after assessment",
        "one_click_goal": "Turn the assessment into an operating system for continuous engineering visibility, delivery tracking, and monthly executive reporting.",
        "scope": [
            "Roadmap execution tracking.",
            "Backlog, sprint, CI/CD, release, and quality visibility.",
            "Continuous scanner and regression evidence capture.",
            "Monthly strategic sync and risk/blocker reporting.",
        ],
        "required_inputs": [
            "Completed Express or Mid assessment baseline.",
            "Approved roadmap and target outcomes.",
            "Project-management source such as Jira, Linear, or equivalent notes.",
            "Agreed reporting cadence and decision-maker contacts.",
        ],
        "automation_steps": [
            "Convert accepted assessment findings into tracked roadmap items.",
            "Run recurring scanner and CI/CD evidence refreshes.",
            "Generate weekly status and monthly executive reports.",
            "Surface blockers, score drift, and resourcing changes before they become delivery risk.",
        ],
        "deliverables": [
            "Weekly status report.",
            "Monthly executive health report.",
            "Roadmap progress and blocker register.",
            "Continuous score and evidence trend history.",
        ],
    },
}


def build_service_tier_workflows() -> dict[str, Any]:
    return {
        "status": "available",
        "version": "one-click-service-tiers-v1",
        "default_tier": "express",
        "tiers": deepcopy(SERVICE_TIER_WORKFLOWS),
        "upgrade_path": ["express", "mid", "retainer"],
        "principles": [
            "Every tier starts with the same simple authorized project intake.",
            "Higher tiers add evidence channels instead of replacing the Express engine.",
            "Scores only improve from real artifacts, review records, QA/parity evidence, and accepted roadmap context.",
            "No tier claims client-ready delivery without human approval and final acceptance evidence.",
        ],
    }


def recommended_next_tier(result: dict[str, Any]) -> str:
    mode = str(result.get("assessment_mode") or "express").lower()
    if mode == "retainer":
        return "retainer"
    if mode == "mid":
        return "retainer"
    return "mid"


def attach_service_tier_workflows(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    workflow = build_service_tier_workflows()
    next_tier = recommended_next_tier(result)
    workflow["recommended_next_tier"] = next_tier
    result["service_tier_workflows"] = workflow

    quick_wins = list(result.get("quick_wins") or [])
    medium_term = list(result.get("medium_term_plan") or [])
    tier = workflow["tiers"][next_tier]
    quick_win = (
        "Make the next service tier as easy as Express: reuse the same authorized intake, then request only the extra evidence needed for "
        f"{tier['label']} ({', '.join(tier['required_inputs'][:2])})."
    )
    if quick_win not in quick_wins:
        quick_wins.append(quick_win)
    for step in tier["automation_steps"][:3]:
        item = f"One-click {tier['label']} workflow: {step}"
        if item not in medium_term:
            medium_term.append(item)
    result["quick_wins"] = quick_wins
    result["medium_term_plan"] = medium_term
    return result
