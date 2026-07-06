from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from nico.admin_security import require_admin_write
from nico.storage import STORE, new_id

DANGEROUS_KEYS = {
    "authorization_required",
    "approval_required",
    "disable_authorization",
    "disable_approval_gate",
    "enable_project_code_execution",
    "shell",
    "database_url",
    "api_key",
    "token",
    "secret",
    "password",
}

DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "version": 1,
    "source": "default",
    "site_title": "NICO",
    "hero_eyebrow": "NICO",
    "hero_powered_by": "Powered by Reparodynamics",
    "hero_headline": "Repair intelligence for authorized systems",
    "hero_lead": "Evidence-bound technical assessments, scanner workflows, client-ready reports, and approval-gated repair planning.",
    "default_repository_example": "your-org/your-repo",
    "primary_cta": "Run Assessment",
    "secondary_cta": "Scanner Worker",
    "human_review_required": "Human review is required before client-facing delivery.",
    "pdf_unavailable": "PDF export is unavailable for this report package until the report worker is enabled.",
    "maintenance_banner": "",
    "demo_mode": False,
    "feature_flags": {
        "show_scanner_worker": True,
        "show_repair_intelligence": True,
        "show_approval_queue": True,
        "show_reports": True,
        "show_mid_assessment": True,
        "show_retainer_ops": True,
        "show_admin_config": True,
        "show_diagnostics": True,
        "show_trends": True,
    },
    "section_help": {
        "scanner_worker": "Use only on authorized repositories. Unavailable tools mean missing evidence, not a clean result.",
        "reports": "Report packages remain evidence-bound and require human review before client delivery.",
        "admin_config": "Runtime settings are for harmless copy and display controls only, not backend security boundaries.",
    },
    "safety_disclaimer": "NICO is defensive-only, authorized-only, evidence-bound, and human-reviewed for code changes.",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contains_secret_like_key(payload: dict[str, Any]) -> bool:
    keys: list[str] = []
    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = str(key).lower()
                keys.append(lowered)
                walk(nested, f"{prefix}.{lowered}" if prefix else lowered)
        elif isinstance(value, list):
            for nested in value:
                walk(nested, prefix)
    walk(payload)
    return any(any(bad in key for bad in DANGEROUS_KEYS) for key in keys)


def validate_runtime_config(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if _contains_secret_like_key(payload):
        errors.append("Runtime config contains a blocked security-sensitive key.")
    flags = payload.get("feature_flags", {})
    if isinstance(flags, dict):
        for key in ("disable_authorization", "disable_approval_gate", "enable_project_code_execution"):
            if flags.get(key):
                errors.append(f"Feature flag {key} is not allowed in runtime config.")
    if payload.get("human_review_required") == "":
        errors.append("human_review_required cannot be blank.")
    return not errors, errors


def runtime_config() -> dict[str, Any]:
    current = STORE.get("runtime_config", "active")
    config = deepcopy(DEFAULT_RUNTIME_CONFIG)
    if current:
        config.update(current.get("config", {}))
        config["source"] = current.get("source", STORE.status().get("adapter", "memory"))
        config["version"] = current.get("version", config.get("version", 1))
        config["updated_at"] = current.get("updated_at")
        config["updated_by"] = current.get("updated_by", "")
    else:
        config["source"] = "default"
        config["updated_at"] = ""
        config["updated_by"] = ""
    config["admin"] = {"writes_publicly_enabled": False, "writes_require_server_token": True}
    return config


def runtime_config_history() -> dict[str, Any]:
    items = STORE.list("runtime_config_history")
    return {"status": "ok", "items": items, "source": STORE.status().get("adapter", "memory")}


def preview_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    ok, errors = validate_runtime_config(payload)
    merged = runtime_config()
    merged.update(payload)
    merged["source"] = "preview"
    return {"status": "ok" if ok else "blocked", "valid": ok, "errors": errors, "preview": merged}


def update_runtime_config(payload: dict[str, Any], admin_token: str | None = None) -> dict[str, Any]:
    allowed, blocked = require_admin_write(admin_token)
    if not allowed:
        return blocked
    ok, errors = validate_runtime_config(payload)
    if not ok:
        return {"status": "blocked", "errors": errors}
    current = runtime_config()
    clean = deepcopy(payload)
    version = int(current.get("version") or 1) + 1
    record = {
        "config_id": "active",
        "version": version,
        "config": clean,
        "source": STORE.status().get("adapter", "memory"),
        "updated_at": now_iso(),
        "updated_by": payload.get("updated_by", "admin"),
        "change_reason": payload.get("change_reason", "runtime config update"),
    }
    STORE.put("runtime_config", "active", record)
    history_id = new_id("configver")
    STORE.put("runtime_config_history", history_id, {**record, "history_id": history_id})
    STORE.audit("runtime_config.updated", {"version": version, "change_reason": record["change_reason"]})
    return {"status": "ok", "config": runtime_config()}
