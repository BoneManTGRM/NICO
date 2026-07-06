from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nico.admin_security import require_admin_write
from nico.approval_queue import list_approvals
from nico.evidence import list_evidence
from nico.storage import STORE, new_id

DEFAULT_CUSTOMER = {"customer_id": "default_customer", "name": "Demo Customer", "source": "default", "demo": True}
DEFAULT_PROJECT = {"project_id": "default_project", "customer_id": "default_customer", "name": "Demo Project", "source": "default", "demo": True}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_customers() -> list[dict[str, Any]]:
    items = STORE.list("customers")
    if not any(item.get("customer_id") == DEFAULT_CUSTOMER["customer_id"] for item in items):
        items.insert(0, dict(DEFAULT_CUSTOMER))
    return items


def create_customer(payload: dict[str, Any], admin_token: str | None = None) -> dict[str, Any]:
    allowed, blocked = require_admin_write(admin_token)
    if not allowed:
        return blocked
    customer_id = payload.get("customer_id") or new_id("customer")
    item = {
        "customer_id": customer_id,
        "name": payload.get("name") or customer_id,
        "source": STORE.status().get("adapter", "memory"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    STORE.put("customers", customer_id, item)
    STORE.audit("customer.created", {"customer_id": customer_id})
    return {"status": "ok", "customer": item}


def get_customer(customer_id: str) -> dict[str, Any]:
    if customer_id == DEFAULT_CUSTOMER["customer_id"]:
        return {"status": "ok", "customer": DEFAULT_CUSTOMER}
    item = STORE.get("customers", customer_id)
    return {"status": "ok", "customer": item} if item else {"status": "not_found", "customer_id": customer_id}


def list_projects(customer_id: str | None = None) -> list[dict[str, Any]]:
    items = STORE.list("projects", customer_id=customer_id)
    if not customer_id or customer_id == DEFAULT_PROJECT["customer_id"]:
        if not any(item.get("project_id") == DEFAULT_PROJECT["project_id"] for item in items):
            items.insert(0, dict(DEFAULT_PROJECT))
    return items


def create_project(payload: dict[str, Any], admin_token: str | None = None) -> dict[str, Any]:
    allowed, blocked = require_admin_write(admin_token)
    if not allowed:
        return blocked
    project_id = payload.get("project_id") or new_id("project")
    customer_id = payload.get("customer_id") or "default_customer"
    item = {
        "project_id": project_id,
        "customer_id": customer_id,
        "name": payload.get("name") or project_id,
        "repository": payload.get("repository", ""),
        "source": STORE.status().get("adapter", "memory"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    STORE.put("projects", project_id, item)
    STORE.audit("project.created", {"project_id": project_id}, customer_id=customer_id, project_id=project_id)
    return {"status": "ok", "project": item}


def get_project(project_id: str) -> dict[str, Any]:
    if project_id == DEFAULT_PROJECT["project_id"]:
        return {"status": "ok", "project": DEFAULT_PROJECT}
    item = STORE.get("projects", project_id)
    return {"status": "ok", "project": item} if item else {"status": "not_found", "project_id": project_id}


def project_runs(project_id: str) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for table, kind in (("assessment_runs", "assessment"), ("scanner_runs", "scanner"), ("reports", "report"), ("approvals", "approval"), ("draft_pr_records", "draft_pr")):
        for item in STORE.list(table, project_id=project_id):
            runs.append({"kind": kind, "table": table, **item})
    runs.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return {"status": "ok", "project_id": project_id, "count": len(runs), "runs": runs}


def project_latest(project_id: str) -> dict[str, Any]:
    runs = project_runs(project_id)["runs"]
    latest: dict[str, Any] = {}
    for item in runs:
        kind = item.get("workflow") or item.get("kind") or "run"
        latest.setdefault(str(kind), item)
    return {"status": "ok", "project_id": project_id, "latest": latest}


def _trend_from_count(count: int) -> str:
    if count == 0:
        return "unavailable"
    if count == 1:
        return "baseline"
    return "tracked"


def project_trends(project_id: str) -> dict[str, Any]:
    runs = project_runs(project_id)["runs"]
    approvals = list_approvals(project_id=project_id)
    evidence = list_evidence(project_id)
    reports = STORE.list("reports", project_id=project_id)
    scanner = STORE.list("scanner_runs", project_id=project_id)
    return {
        "status": "ok",
        "project_id": project_id,
        "source": STORE.status().get("adapter", "memory"),
        "risk_trend": _trend_from_count(len(runs)),
        "dependency_trend": _trend_from_count(len(scanner)),
        "ci_reliability_trend": _trend_from_count(len(scanner)),
        "scanner_coverage_trend": _trend_from_count(len(scanner)),
        "qa_readiness_trend": _trend_from_count(len([run for run in runs if run.get("workflow") == "mid"])),
        "backlog_health_trend": _trend_from_count(len([run for run in runs if run.get("workflow") == "retainer"])),
        "approval_queue_trend": _trend_from_count(len(approvals)),
        "report_readiness_trend": _trend_from_count(len(reports)),
        "counts": {"runs": len(runs), "scanner_runs": len(scanner), "approvals": len(approvals), "reports": len(reports), "evidence": len(evidence)},
        "unavailable_data_notes": ["Trend quality improves after multiple persisted runs."] if len(runs) < 2 else [],
    }


def project_reports(project_id: str) -> dict[str, Any]:
    return {"status": "ok", "project_id": project_id, "reports": STORE.list("reports", project_id=project_id)}


def project_approvals(project_id: str) -> dict[str, Any]:
    return {"status": "ok", "project_id": project_id, "approvals": list_approvals(project_id=project_id)}


def project_evidence(project_id: str) -> dict[str, Any]:
    return {"status": "ok", "project_id": project_id, "evidence": list_evidence(project_id)}
