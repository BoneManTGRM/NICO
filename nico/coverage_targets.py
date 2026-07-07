from __future__ import annotations

from typing import Any

COVERAGE_TARGETS = {
    "express": "95%",
    "mid": "85%",
    "retainer": "70%",
    "client_ready_with_human_review": "85%",
}

COVERAGE_RANGES = {
    "express": "90-95%",
    "mid": "75-85%",
    "retainer": "55-70%",
    "client_ready_with_human_review": "75-85%",
}

COVERAGE_TARGET_DETAILS = {
    "express": {
        "label": "Express Technical Health Assessment",
        "range": COVERAGE_RANGES["express"],
        "max_target": COVERAGE_TARGETS["express"],
        "automation_scope": "Technical audit, report generation, evidence review, action plan, resourcing plan, and final-review workflow.",
        "remaining_human_gate": "Human review and client acceptance remain required before delivery.",
    },
    "mid": {
        "label": "Mid Technical Health Assessment",
        "range": COVERAGE_RANGES["mid"],
        "max_target": COVERAGE_TARGETS["mid"],
        "automation_scope": "QA evidence organization, parity checklist, stakeholder notes, risk register, and six-month roadmap draft.",
        "remaining_human_gate": "Stakeholder interviews, product judgment, and final roadmap commitments remain human-reviewed.",
    },
    "retainer": {
        "label": "Ongoing Product Engineering Retainer",
        "range": COVERAGE_RANGES["retainer"],
        "max_target": COVERAGE_TARGETS["retainer"],
        "automation_scope": "Weekly delivery status, backlog health, release readiness, blocker tracking, and approval queue support.",
        "remaining_human_gate": "Production decisions, client communication, and prioritization remain human-approved.",
    },
    "client_ready_with_human_review": {
        "label": "Full client-ready replacement",
        "range": COVERAGE_RANGES["client_ready_with_human_review"],
        "max_target": COVERAGE_TARGETS["client_ready_with_human_review"],
        "automation_scope": "End-to-end assessment packaging, report export, final-review target, acceptance tracking, and evidence disclosure.",
        "remaining_human_gate": "Client-facing delivery still requires a human reviewer and accepted approval record.",
    },
}


def max_coverage_targets() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "upper_end_goals",
        "targets": COVERAGE_TARGETS,
        "ranges": COVERAGE_RANGES,
        "details": COVERAGE_TARGET_DETAILS,
        "rule": "Targets are upper-end service-automation goals. Human review and client acceptance are not automatically completed.",
    }
