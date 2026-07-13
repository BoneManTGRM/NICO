from __future__ import annotations

import hashlib
import re
from typing import Any

from nico.production_smoke_config import (
    FULL_TOOLS,
    SmokeConfig,
    SmokeFailure,
    _CLIENT_READY_KEYS,
    _FAILURE_STATUSES,
    _REPORT_ID_KEYS,
    _REVIEW_ID_KEYS,
    _REVIEW_KEYS,
    _SAFE_IDENTITY,
    _UNAVAILABLE_KEYS,
)

def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)

def _first_string(value: Any, keys: tuple[str, ...]) -> str:
    for item in _walk(value):
        for key in keys:
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()[:200]
    return ""

def _explicit_boolean_boundary(value: Any, keys: set[str], *, expected: bool) -> bool:
    observed: list[bool] = []
    for item in _walk(value):
        for key in keys:
            candidate = item.get(key)
            if isinstance(candidate, bool):
                observed.append(candidate)
    return bool(observed) and expected in observed and (not expected) not in observed

def _safe_identity(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    if _SAFE_IDENTITY.fullmatch(candidate):
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"redacted_identity_sha256:{digest}"

def _unavailable_evidence(value: Any) -> list[str]:
    notes: list[str] = []
    for item in _walk(value):
        for key in _UNAVAILABLE_KEYS:
            candidate = item.get(key)
            if isinstance(candidate, list):
                for entry in candidate:
                    if isinstance(entry, str) and entry.strip():
                        digest = hashlib.sha256(entry.strip().encode("utf-8", errors="replace")).hexdigest()[:20]
                        notes.append(f"unavailable_note_sha256:{digest}")
        status = str(item.get("status") or "").lower()
        if status in {"unavailable", "failed", "timed_out", "blocked"}:
            raw_label = str(item.get("step") or item.get("id") or item.get("tool") or "evidence")
            label = re.sub(r"[^A-Za-z0-9_.-]", "_", raw_label)[:80] or "evidence"
            notes.append(f"{label}:{status}")
    unique: list[str] = []
    for note in notes:
        if note not in unique:
            unique.append(note)
        if len(unique) == 30:
            break
    return unique

def _report_present(tier: str, value: dict[str, Any]) -> bool:
    if _first_string(value, _REPORT_ID_KEYS):
        return True
    reports = value.get("reports") if isinstance(value.get("reports"), dict) else {}
    if tier == "mid":
        mid_report = value.get("mid_report") if isinstance(value.get("mid_report"), dict) else {}
        return bool(mid_report.get("report_id") or reports.get("markdown") or reports.get("pdf_sha256"))
    return bool(reports.get("markdown") or reports.get("pdf_sha256") or reports.get("pdf_base64"))

def _tier_is_stable(tier: str, value: dict[str, Any]) -> bool:
    status = str(value.get("status") or "").lower()
    if status in _FAILURE_STATUSES:
        raise SmokeFailure("assessment_failed", f"{tier.title()} assessment reached terminal status {status}.")
    human_review = _explicit_boolean_boundary(value, _REVIEW_KEYS, expected=True)
    client_not_ready = _explicit_boolean_boundary(value, _CLIENT_READY_KEYS, expected=False)
    if tier == "express":
        return status in {"complete", "ok", "passed", "review_required", "human_review_required"} and _report_present(tier, value) and human_review and client_not_ready
    if status != "complete":
        return False
    report_ready = _report_present(tier, value)
    review_ready = bool(_first_string(value, _REVIEW_ID_KEYS))
    if tier == "mid" and str(value.get("report_generation_status") or "").lower() != "complete":
        return False
    return report_ready and review_ready and human_review and client_not_ready

def _common_payload(config: SmokeConfig) -> dict[str, Any]:
    return {
        "repository": config.repository,
        "customer_id": config.customer_id,
        "project_id": config.project_id,
        "client_name": "NICO authorized production demonstration",
        "project_name": "Production assessment smoke proof",
        "authorized_by": "github_actions_production_smoke",
        "authorization_scope": "authorized defensive repository assessment",
        "authorization_confirmed": True,
        "authorized": True,
        "timeframe_days": 180,
        "refresh_full_evidence": True,
    }

def _tier_payload(config: SmokeConfig, tier: str, current: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _common_payload(config)
    if tier == "express":
        payload["assessment_mode"] = "express"
        return payload
    payload.update({"run_scanners": True, "auto_continue": True})
    if current:
        payload["scan_id"] = _first_string(current, ("scan_id",))
    if tier == "full":
        payload.update(
            {
                "mode": "full",
                "build_reports": True,
                "create_final_review_request": True,
                "tools": list(FULL_TOOLS),
            }
        )
    return payload

