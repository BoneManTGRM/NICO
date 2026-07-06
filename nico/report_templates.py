from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from nico.admin_security import require_admin_write
from nico.storage import STORE

REQUIRED_DISCLAIMER = "Human review is required before client-facing delivery. Missing evidence must remain visible."

DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "executive_summary": {
        "template_id": "executive_summary",
        "version": 1,
        "title": "Executive Summary",
        "intro": "NICO summarizes technical health using evidence provided by authorized sources.",
        "human_review_disclaimer": REQUIRED_DISCLAIMER,
        "unavailable_data_wording": "Unavailable data is listed explicitly and is not treated as verified.",
        "next_step_wording": "Review findings, validate evidence, and approve next actions before delivery.",
        "footer_disclaimer": "NICO does not modify customer systems automatically.",
    },
    "technical_report": {
        "template_id": "technical_report",
        "version": 1,
        "title": "Technical Health Report",
        "intro": "Code, dependency, CI/CD, architecture, and scanner evidence are grouped by maturity area.",
        "human_review_disclaimer": REQUIRED_DISCLAIMER,
        "unavailable_data_wording": "Unavailable areas require follow-up evidence before firm conclusions.",
        "next_step_wording": "Prioritize high-risk findings and approval-gated repairs.",
        "footer_disclaimer": "Generated recommendations are advisory until reviewed by a human.",
    },
    "risk_register": {
        "template_id": "risk_register",
        "version": 1,
        "title": "Risk Register",
        "intro": "Risks are ranked by severity, confidence, evidence readiness, and reversibility.",
        "human_review_disclaimer": REQUIRED_DISCLAIMER,
        "unavailable_data_wording": "Unknown risk fields remain unknown until evidence is supplied.",
        "next_step_wording": "Assign owners and approval requirements for each repair path.",
        "footer_disclaimer": "Risk labels do not imply exploitation or vulnerability confirmation without evidence.",
    },
    "retainer_weekly": {
        "template_id": "retainer_weekly",
        "version": 1,
        "title": "Retainer Weekly Status",
        "intro": "Weekly status highlights delivery progress, blockers, release readiness, and approval needs.",
        "human_review_disclaimer": REQUIRED_DISCLAIMER,
        "unavailable_data_wording": "Unreported work is not invented or counted as complete.",
        "next_step_wording": "Confirm blockers, approvals, and next sprint priorities.",
        "footer_disclaimer": "Client decisions remain human-owned.",
    },
    "repair_recommendation": {
        "template_id": "repair_recommendation",
        "version": 1,
        "title": "Repair Recommendation Package",
        "intro": "Repair suggestions include evidence, root-cause hypothesis, patch steps, test plan, and rollback plan.",
        "human_review_disclaimer": REQUIRED_DISCLAIMER,
        "unavailable_data_wording": "Missing evidence lowers confidence and must be disclosed.",
        "next_step_wording": "Send to approval queue before branch, PR, CI, or customer merge.",
        "footer_disclaimer": "NICO does not push to main or deploy production changes automatically.",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_template(template: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(template)
    text = " ".join(str(value) for value in item.values()).lower()
    if "human review" not in text:
        item["human_review_disclaimer"] = REQUIRED_DISCLAIMER
    if "unavailable" not in text and "missing" not in text:
        item["unavailable_data_wording"] = "Unavailable or missing evidence must remain visible."
    item["claims_pdf_available"] = False
    item["source"] = item.get("source", "default")
    return item


def list_report_templates() -> dict[str, Any]:
    stored = {item.get("template_id"): item for item in STORE.list("report_templates")}
    items = []
    for template_id, default in DEFAULT_TEMPLATES.items():
        item = deepcopy(default)
        if template_id in stored:
            item.update(stored[template_id])
        items.append(_safe_template(item))
    return {"status": "ok", "source": STORE.status().get("adapter", "memory"), "templates": items}


def get_report_template(template_id: str) -> dict[str, Any]:
    if template_id not in DEFAULT_TEMPLATES:
        return {"status": "not_found", "template_id": template_id}
    stored = STORE.get("report_templates", template_id) or {}
    item = deepcopy(DEFAULT_TEMPLATES[template_id])
    item.update(stored)
    return {"status": "ok", "template": _safe_template(item)}


def update_report_template(template_id: str, payload: dict[str, Any], admin_token: str | None = None) -> dict[str, Any]:
    allowed, blocked = require_admin_write(admin_token)
    if not allowed:
        return blocked
    if template_id not in DEFAULT_TEMPLATES:
        return {"status": "not_found", "template_id": template_id}
    item = deepcopy(DEFAULT_TEMPLATES[template_id])
    item.update(payload)
    item["template_id"] = template_id
    item["version"] = int(item.get("version") or 1) + 1
    item["updated_at"] = now_iso()
    item["source"] = STORE.status().get("adapter", "memory")
    item = _safe_template(item)
    STORE.put("report_templates", template_id, item)
    STORE.audit("report_template.updated", {"template_id": template_id, "version": item["version"]})
    return {"status": "ok", "template": item}
