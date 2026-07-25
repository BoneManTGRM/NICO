from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

VERSION = "nico.strategic_human_evidence.v1"
_ALLOWED_STATUSES = {"provided", "not_assessed", "unavailable", "excluded"}
_ALLOWED_SOURCE_TYPES = {"human_statement", "attached_evidence", "mixed", "none"}

MODULES: dict[str, str] = {
    "stakeholder_context": "Stakeholder objectives, pain points, constraints, and desired state",
    "functional_qa": "Functional QA scenarios and observed results",
    "platform_parity": "Browser, device, platform, and native parity evidence",
    "accessibility_ux": "Accessibility and user-experience observations",
    "incident_history": "Production incidents, support events, and recovery evidence",
    "release_goals": "Product goals, release deadlines, and acceptance criteria",
    "requirements_compliance": "Regulatory, contractual, and requirements evidence",
    "budget_staffing_constraints": "Budget, staffing, capacity, and operating constraints",
    "architecture_decisions": "Known architecture decisions and decision rationale",
    "accepted_risks": "Explicitly accepted risks and approval boundaries",
    "support_pain_points": "Customer-support themes and recurring user pain points",
}


def _safe(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[:4000]
    if depth >= 4:
        return str(value)[:4000]
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 100:
                break
            output[str(key)[:160]] = _safe(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth=depth + 1) for item in list(value)[:100]]
    return str(value)[:4000]


def _strings(value: Any, *, limit: int = 100) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = " ".join(str(item or "").split())[:4000]
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_module(module_id: str, raw: Any) -> dict[str, Any]:
    source = dict(raw) if isinstance(raw, Mapping) else {}
    statements = _strings(source.get("statements") or source.get("notes"))
    attachment_refs = _strings(
        source.get("attachment_refs") or source.get("evidence_refs")
    )
    records_raw = source.get("records")
    records = (
        [_safe(item) for item in list(records_raw)[:100]]
        if isinstance(records_raw, (list, tuple))
        else []
    )
    supplied_by = " ".join(str(source.get("supplied_by") or "").split())[:240]
    captured_at = " ".join(str(source.get("captured_at") or "").split())[:120]
    requested_status = str(source.get("status") or "").strip().casefold()
    has_content = bool(statements or attachment_refs or records)
    status = requested_status if requested_status in _ALLOWED_STATUSES else (
        "provided" if has_content else "not_assessed"
    )
    if status == "provided" and not has_content:
        status = "not_assessed"

    requested_source_type = str(source.get("source_type") or "").strip().casefold()
    if requested_source_type in _ALLOWED_SOURCE_TYPES:
        source_type = requested_source_type
    elif statements and (attachment_refs or records):
        source_type = "mixed"
    elif attachment_refs or records:
        source_type = "attached_evidence"
    elif statements:
        source_type = "human_statement"
    else:
        source_type = "none"

    module = {
        "module_id": module_id,
        "label": MODULES[module_id],
        "status": status,
        "source_type": source_type,
        "statements": statements,
        "records": records,
        "attachment_refs": attachment_refs,
        "supplied_by": supplied_by,
        "captured_at": captured_at,
        "directly_scored": False,
        "requires_human_review": True,
    }
    module["module_sha256"] = _canonical_hash(module)
    return module


def normalize_strategic_human_evidence(value: Any) -> dict[str, Any]:
    """Normalize explicit human evidence without inferring missing facts from code."""

    source = dict(value) if isinstance(value, Mapping) else {}
    if source.get("artifact_schema") == VERSION and isinstance(
        source.get("modules"), Mapping
    ):
        source = dict(source["modules"])
    modules = {
        module_id: _normalize_module(module_id, source.get(module_id))
        for module_id in MODULES
    }
    status_counts = {
        status: sum(module["status"] == status for module in modules.values())
        for status in sorted(_ALLOWED_STATUSES)
    }
    provided_ids = [
        module_id
        for module_id, module in modules.items()
        if module["status"] == "provided"
    ]
    package = {
        "artifact_schema": VERSION,
        "status": "provided" if provided_ids else "not_assessed",
        "modules": modules,
        "provided_module_ids": provided_ids,
        "status_counts": status_counts,
        "human_statement_count": sum(
            len(module["statements"]) for module in modules.values()
        ),
        "attachment_reference_count": sum(
            len(module["attachment_refs"]) for module in modules.values()
        ),
        "structured_record_count": sum(
            len(module["records"]) for module in modules.values()
        ),
        "repository_inference_prohibited": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package["human_evidence_sha256"] = _canonical_hash(package)
    return package


def human_evidence_module(package: Any, module_id: str) -> dict[str, Any]:
    if module_id not in MODULES:
        raise KeyError(f"unknown_human_evidence_module:{module_id}")
    normalized = normalize_strategic_human_evidence(package)
    modules = normalized.get("modules")
    value = modules.get(module_id) if isinstance(modules, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else _normalize_module(module_id, None)


__all__ = [
    "MODULES",
    "VERSION",
    "human_evidence_module",
    "normalize_strategic_human_evidence",
]
