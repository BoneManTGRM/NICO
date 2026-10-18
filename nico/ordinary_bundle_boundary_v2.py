"""Reject bundle downgrades at legacy single-PDF authority/transport boundaries."""
from collections.abc import Mapping
import json
from typing import Any

ERROR = "report_bundle_requires_v2_boundary"
_SCHEMA_PREFIXES = ("nico.ordinary-review-bundle.", "nico.ordinary-report-files.")
_CONTAINERS = ("json", "report_package", "reports", "report", "artifacts", "manifest",
               "accepted_edition", "operator_approved_edition", "operator_delivery_edition")
_REPORT_STAGES = ("final_comprehensive_report_generation", "risk_reduction_and_executive_briefing",
                  "decision_report_generation")


def has_report_bundle(value: Any) -> bool:
    """Inspect only report-owned containers, never quoted assessment evidence."""
    pending = [value]
    visited = set()
    while pending:
        item = pending.pop()
        if not isinstance(item, Mapping) or id(item) in visited:
            continue
        visited.add(id(item))
        schema = item.get("artifact_schema")
        if ("report_bundle" in item or "report_bundle_schema" in item
                or isinstance(schema, str) and schema.startswith(_SCHEMA_PREFIXES)):
            return True
        for key in _CONTAINERS:
            child = item.get(key)
            # The accepted-edition helper also accepts serialized canonical JSON.
            # Parse only the report-owned JSON slot, never quoted evidence strings.
            if key == "json" and isinstance(child, str) and any(
                marker in child for marker in (*_SCHEMA_PREFIXES, '"report_bundle"', '"report_bundle_schema"')
            ):
                try:
                    child = json.loads(child)
                except (ValueError, RecursionError):
                    continue
            pending.append(child)
        stages = item.get("stage_results")
        if isinstance(stages, Mapping):
            pending.extend(stages.get(stage) for stage in _REPORT_STAGES)
    return False


def require_legacy_single_pdf(*values: Any) -> None:
    if any(has_report_bundle(value) for value in values):
        raise ValueError(ERROR)
