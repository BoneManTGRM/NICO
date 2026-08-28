from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from nico.decision_grade_human_evidence_v1 import MODULE_DEFINITIONS

VERSION = "nico.strategic_human_evidence.v2"
_REQUIRED_METADATA = ("reviewer", "observed_at", "source_reference")
_EXACT_ENGAGEMENT_FIELD_LIMITS = {
    "customer_name": 180,
    "project_name": 180,
    "primary_technical_contact": 600,
    "access_method": 1200,
    "authorized_scope": 4000,
}

MODULES: dict[str, dict[str, Any]] = {
    str(definition["module_id"]): {
        "label": str(definition["label"]),
        "description": str(definition["description"]),
        "required_fields": tuple(str(item) for item in definition["required_fields"]),
    }
    for definition in MODULE_DEFINITIONS
}


def _safe(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.strip()[:4000]
    if depth >= 5:
        return str(value)[:4000]
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 120:
                break
            output[str(key)[:160]] = _safe(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth=depth + 1) for item in list(value)[:120]]
    return str(value)[:4000]


def _exact_engagement_value(value: Any, *, limit: int, depth: int = 0) -> Any:
    """Preserve the five engagement literals inside retained human evidence."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > limit:
            raise ValueError(f"engagement_evidence_value_exceeds_{limit}_characters")
        return value
    if depth >= 5:
        rendered = str(value)
        if len(rendered) > limit:
            raise ValueError(f"engagement_evidence_value_exceeds_{limit}_characters")
        return rendered
    if isinstance(value, Mapping):
        return {
            str(key)[:160]: _exact_engagement_value(item, limit=limit, depth=depth + 1)
            for index, (key, item) in enumerate(value.items())
            if index < 120
        }
    if isinstance(value, (list, tuple, set)):
        return [
            _exact_engagement_value(item, limit=limit, depth=depth + 1)
            for item in list(value)[:120]
        ]
    rendered = str(value)
    if len(rendered) > limit:
        raise ValueError(f"engagement_evidence_value_exceeds_{limit}_characters")
    return rendered


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _module_inputs(value: Any) -> dict[str, dict[str, Any]]:
    source = _record(value)
    modules = source.get("modules")
    if isinstance(modules, Mapping):
        return {
            str(module_id): _record(payload)
            for module_id, payload in modules.items()
            if str(module_id) in MODULES
        }
    if isinstance(modules, list):
        output: dict[str, dict[str, Any]] = {}
        for item in modules:
            if not isinstance(item, Mapping):
                continue
            module_id = str(item.get("module_id") or "")
            if module_id in MODULES:
                output[module_id] = dict(item)
        return output
    return {
        str(module_id): _record(payload)
        for module_id, payload in source.items()
        if str(module_id) in MODULES
    }


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _normalize_module(module_id: str, raw: Any) -> dict[str, Any]:
    definition = MODULES[module_id]
    source = _record(raw)
    evidence = _record(source.get("evidence"))
    for field in definition["required_fields"]:
        if field in source and field not in evidence:
            evidence[field] = _safe(source[field])
    evidence = {
        str(key): (
            _exact_engagement_value(
                item,
                limit=_EXACT_ENGAGEMENT_FIELD_LIMITS[str(key)],
            )
            if str(key) in _EXACT_ENGAGEMENT_FIELD_LIMITS
            else _safe(item)
        )
        for key, item in evidence.items()
    }

    reviewer = " ".join(str(source.get("reviewer") or "").split())[:240]
    observed_at = " ".join(
        str(source.get("observed_at") or source.get("captured_at") or "").split()
    )[:120]
    source_reference = " ".join(
        str(
            source.get("source_reference")
            or source.get("attachment_reference")
            or source.get("attachment_ref")
            or ""
        ).split()
    )[:600]
    excluded = source.get("excluded") is True or str(source.get("status") or "").casefold() in {
        "excluded",
        "out_of_scope",
    }
    exclusion_rationale = " ".join(
        str(source.get("exclusion_rationale") or source.get("reason") or "").split()
    )[:1200]

    required_fields = list(definition["required_fields"])
    present_fields = [field for field in required_fields if _present(evidence.get(field))]
    missing_fields = [field for field in required_fields if field not in present_fields]
    metadata = {
        "reviewer": reviewer,
        "observed_at": observed_at,
        "source_reference": source_reference,
    }
    present_metadata = [field for field, item in metadata.items() if _present(item)]
    missing_metadata = [field for field in _REQUIRED_METADATA if field not in present_metadata]
    has_content = bool(evidence or present_metadata or exclusion_rationale or excluded)

    if excluded and exclusion_rationale:
        status = "excluded"
        assurance = "EXCLUDED WITH RATIONALE"
    elif has_content and not missing_fields and not missing_metadata:
        status = "complete"
        assurance = "HUMAN EVIDENCE RETAINED · REVIEW REQUIRED"
    elif has_content:
        status = "partial"
        assurance = "REVIEW LIMITED"
        if excluded and not exclusion_rationale:
            missing_metadata.append("exclusion_rationale")
    else:
        status = "not_assessed"
        assurance = "NOT ASSESSED"

    module = {
        "module_id": module_id,
        "label": definition["label"],
        "description": definition["description"],
        "status": status,
        "assurance": assurance,
        "required_fields": required_fields,
        "present_fields": present_fields,
        "missing_fields": missing_fields,
        "required_metadata": list(_REQUIRED_METADATA),
        "present_metadata": present_metadata,
        "missing_metadata": sorted(set(missing_metadata)),
        "evidence": evidence,
        **metadata,
        "excluded": excluded,
        "exclusion_rationale": exclusion_rationale,
        "human_observation_required": True,
        "repository_inference_allowed": False,
        "directly_scored": False,
    }
    module["module_sha256"] = _canonical_hash(module)
    return module


def _structured_record_count(modules: Mapping[str, Mapping[str, Any]]) -> int:
    count = 0
    for module in modules.values():
        evidence = module.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        for value in evidence.values():
            if isinstance(value, list):
                count += len(value)
            elif isinstance(value, Mapping):
                count += len(value)
            elif _present(value):
                count += 1
    return count


def normalize_strategic_human_evidence(value: Any) -> dict[str, Any]:
    """Normalize the existing decision-grade intake schema for run persistence.

    This is a persistence and transport contract. It does not infer missing facts,
    alter technical scores, or mark incomplete human evidence as complete.
    """

    inputs = _module_inputs(value)
    modules = {
        module_id: _normalize_module(module_id, inputs.get(module_id))
        for module_id in MODULES
    }
    counts = {
        status: sum(module["status"] == status for module in modules.values())
        for status in ("complete", "partial", "not_assessed", "excluded")
    }
    complete = [key for key, module in modules.items() if module["status"] == "complete"]
    partial = [key for key, module in modules.items() if module["status"] == "partial"]
    excluded = [key for key, module in modules.items() if module["status"] == "excluded"]
    not_assessed = [key for key, module in modules.items() if module["status"] == "not_assessed"]
    active = [*complete, *partial, *excluded]
    package = {
        "artifact_schema": VERSION,
        "status": "complete" if not partial and not not_assessed else "review_limited",
        "module_count": len(modules),
        "status_counts": counts,
        "complete_modules": complete,
        "partial_modules": partial,
        "not_assessed_modules": not_assessed,
        "excluded_modules": excluded,
        "provided_module_ids": active,
        "human_statement_count": 0,
        "attachment_reference_count": sum(
            bool(modules[module_id].get("source_reference")) for module_id in active
        ),
        "structured_record_count": _structured_record_count(modules),
        "modules": modules,
        "repository_inference_allowed": False,
        "repository_inference_prohibited": True,
        "directly_scored": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package["human_evidence_sha256"] = _canonical_hash(package)
    return package


def verify_strategic_human_evidence(value: Any) -> bool:
    """Verify the top-level package and every embedded module digest after storage."""

    if not isinstance(value, Mapping):
        return False
    source = dict(value)
    claimed = str(source.pop("human_evidence_sha256", "") or "")
    if not claimed or claimed != _canonical_hash(source):
        return False
    modules = source.get("modules")
    if not isinstance(modules, Mapping) or set(modules) != set(MODULES):
        return False
    for module_id, raw in modules.items():
        if not isinstance(raw, Mapping) or str(raw.get("module_id") or "") != str(module_id):
            return False
        module = dict(raw)
        module_claimed = str(module.pop("module_sha256", "") or "")
        if not module_claimed or module_claimed != _canonical_hash(module):
            return False
    return True


def human_evidence_module(package: Any, module_id: str) -> dict[str, Any]:
    if module_id not in MODULES:
        raise KeyError(f"unknown_human_evidence_module:{module_id}")
    normalized = normalize_strategic_human_evidence(package)
    modules = normalized.get("modules")
    value = modules.get(module_id) if isinstance(modules, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else _normalize_module(module_id, None)


def decision_grade_stage_payload(package: Any, module_ids: tuple[str, ...]) -> dict[str, Any]:
    """Project persisted evidence into the schema consumed by report synthesis."""

    normalized = normalize_strategic_human_evidence(package)
    output: dict[str, Any] = {}
    for module_id in module_ids:
        module = human_evidence_module(normalized, module_id)
        if module["status"] == "not_assessed":
            continue
        output[module_id] = {
            **dict(module.get("evidence") or {}),
            "reviewer": module.get("reviewer") or "",
            "observed_at": module.get("observed_at") or "",
            "source_reference": module.get("source_reference") or "",
            "status": module.get("status") or "partial",
            "excluded": module.get("excluded") is True,
            "exclusion_rationale": module.get("exclusion_rationale") or "",
            "module_sha256": module.get("module_sha256") or "",
        }
    return output


__all__ = [
    "MODULES",
    "VERSION",
    "decision_grade_stage_payload",
    "human_evidence_module",
    "normalize_strategic_human_evidence",
    "verify_strategic_human_evidence",
]
