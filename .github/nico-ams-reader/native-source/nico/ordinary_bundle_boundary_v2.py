"""Reject bundle downgrades at legacy single-PDF authority/transport boundaries."""
from collections.abc import Mapping
import json
from typing import Any

ERROR = "report_bundle_requires_v2_boundary"
# Match the existing 8 MiB safe in-memory JSON serialization envelope. This
# bounds inspection; it does not change the retained bytes or their digest.
MAX_REPORT_JSON_BYTES = 8 * 1024 * 1024
_SCHEMA_PREFIXES = ("nico.ordinary-review-bundle.", "nico.ordinary-report-files.")
_CONTAINERS = ("json", "report_package", "reports", "report", "artifacts", "manifest",
               "accepted_edition", "operator_approved_edition", "operator_delivery_edition")
_REPORT_STAGES = ("final_comprehensive_report_generation", "risk_reduction_and_executive_briefing",
                  "decision_report_generation")


def _report_json(value: str | bytes | bytearray) -> Mapping[str, Any]:
    if len(value) > MAX_REPORT_JSON_BYTES:
        raise ValueError("report_json_size_limit_at_legacy_boundary")
    try:
        data = value.encode("utf-8") if isinstance(value, str) else value
        if len(data) > MAX_REPORT_JSON_BYTES:
            raise ValueError("report_json_size_limit_at_legacy_boundary")

        def object_pairs(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("report_json_duplicate_key_at_legacy_boundary")
                result[key] = item
            return result

        def invalid_constant(_value):
            raise ValueError("report_json_invalid_at_legacy_boundary")

        parsed = json.loads(data, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("report_json_invalid_at_legacy_boundary") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError("report_json_object_required_at_legacy_boundary")
    return parsed


def has_report_bundle(value: Any) -> bool:
    """Inspect only report-owned containers, never quoted assessment evidence."""
    pending = [value]
    # Retain parsed mappings during traversal so recycled object IDs cannot
    # cause a later report-owned JSON object to be mistaken for a visited one.
    visited = {}
    while pending:
        item = pending.pop()
        if not isinstance(item, Mapping) or id(item) in visited:
            continue
        visited[id(item)] = item
        schema = item.get("artifact_schema")
        if ("report_bundle" in item or "report_bundle_schema" in item
                or isinstance(schema, str) and schema.startswith(_SCHEMA_PREFIXES)):
            return True
        for key in _CONTAINERS:
            child = item.get(key)
            # The accepted-edition helper also accepts serialized canonical JSON.
            # Parse only the report-owned JSON slot, never quoted evidence strings.
            if key == "json" and isinstance(child, (str, bytes, bytearray)) and child:
                child = _report_json(child)
            pending.append(child)
        stages = item.get("stage_results")
        if isinstance(stages, Mapping):
            pending.extend(stages.get(stage) for stage in _REPORT_STAGES)
    return False


def require_legacy_single_pdf(*values: Any) -> None:
    if any(has_report_bundle(value) for value in values):
        raise ValueError(ERROR)
