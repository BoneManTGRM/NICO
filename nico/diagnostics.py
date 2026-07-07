from __future__ import annotations

import os
from typing import Any

from nico.admin_security import safe_public_admin_status
from nico.approval_queue import list_approvals
from nico.github_diagnostics import github_auth_diagnostics
from nico.runtime_config import runtime_config
from nico.scanner_artifact_scoring import scanner_artifact_access_status
from nico.storage import STORE

REDACTED = "[REDACTED]"


def safe_env_flag(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def storage_diagnostics() -> dict[str, Any]:
    status = STORE.status()
    warnings = []
    if not status.get("persistence_available"):
        warnings.append(status.get("durability_warning") or "Storage persistence is unavailable; retained evidence may not survive restart.")
    if status.get("database_url_configured") and status.get("adapter") != "postgres":
        warnings.append("DATABASE_URL is configured but Postgres is not active. Check driver availability, connectivity, and NICO_DISABLE_POSTGRES.")
    return {
        "status": "ok",
        "storage": status,
        "database_configured": bool(status.get("database_url_configured")),
        "persistence_available": bool(status.get("persistence_available")),
        "database_url": REDACTED if status.get("database_url_configured") else "not_configured",
        "warnings": warnings,
    }


def feature_diagnostics() -> dict[str, Any]:
    config = runtime_config()
    return {
        "status": "ok",
        "runtime_config_source": config.get("source"),
        "feature_flags": config.get("feature_flags", {}),
        "scanner_execution_enabled": os.getenv("NICO_ENABLE_SCANNER_EXECUTION", "true").lower() == "true",
        "project_commands_allowed": os.getenv("NICO_ALLOW_PROJECT_COMMANDS", "false").lower() == "true",
        "admin": safe_public_admin_status(),
    }


def latest_runs_diagnostics() -> dict[str, Any]:
    assessment_runs = STORE.list("assessment_runs")
    scanner_runs = STORE.list("scanner_runs")
    reports = STORE.list("reports")
    approvals = list_approvals()
    return {
        "status": "ok",
        "last_assessment_run_status": assessment_runs[-1].get("status") if assessment_runs else "empty",
        "last_scanner_run_status": scanner_runs[-1].get("status") if scanner_runs else "empty",
        "latest_approval_count": len(approvals),
        "latest_report_count": len(reports),
        "counts": {
            "assessment_runs": len(assessment_runs),
            "scanner_runs": len(scanner_runs),
            "approvals": len(approvals),
            "reports": len(reports),
        },
    }


def diagnostics() -> dict[str, Any]:
    config = runtime_config()
    default_repo = os.getenv("NICO_DEFAULT_REPOSITORY") or "BoneManTGRM/NICO"
    return {
        "status": "ok",
        "app": "NICO",
        "version": "0.8.0-accuracy-hardening",
        "git_commit": os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("VERCEL_GIT_COMMIT_SHA") or "unavailable",
        "backend_mode": "accuracy-hardening-hosted",
        "storage": storage_diagnostics(),
        "runtime_config": {"source": config.get("source"), "version": config.get("version")},
        "github": github_auth_diagnostics(),
        "scanner_artifacts": scanner_artifact_access_status(default_repo),
        "features": feature_diagnostics(),
        "latest_runs": latest_runs_diagnostics(),
        "redaction": "Private values and raw provider error JSON are not returned by diagnostics.",
    }
