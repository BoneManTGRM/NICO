from __future__ import annotations

import csv
import io
from typing import Any

from nico.comprehensive_decision_grade_model_v5 import _text

VERSION = "nico.comprehensive_decision_grade_csv.v6"


def _csv_value(value: Any, limit: int = 6000) -> str:
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_text(item, limit) for item in value if _text(item, limit))
    if isinstance(value, dict):
        return "; ".join(
            f"{_text(key, 300)}={_text(item, limit)}"
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    return _text(value, limit)


def _findings_csv(findings: list[dict[str, Any]]) -> str:
    """Export the canonical finding model without rebuilding finding identity."""

    fields = [
        "id",
        "finding_id",
        "priority",
        "status",
        "category",
        "executive_title",
        "technical_summary",
        "analyzer_message",
        "tool",
        "rule_id",
        "canonical_path",
        "canonical_line",
        "canonical_location",
        "original_analyzer_location",
        "related_locations",
        "fact",
        "evidence",
        "business_impact",
        "impact",
        "confidence",
        "owner_role",
        "effort",
        "recommendation",
        "acceptance_criteria",
        "cost_of_inaction",
        "residual_risk",
        "roadmap_mappings",
        "backlog_mappings",
        "backlog_issue_mapping",
        "source_evidence_fingerprint",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for item in findings:
        if not isinstance(item, dict):
            continue
        writer.writerow({field: _csv_value(item.get(field)) for field in fields})
    return stream.getvalue()


def _evidence_csv(stages: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["stage_id", "stage_title", "stage_status", "record_type", "record"])
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        for record_type in ("evidence", "findings", "unavailable"):
            for item in stage.get(record_type) or []:
                writer.writerow(
                    [
                        _text(stage.get("stage_id"), 500),
                        _text(stage.get("title"), 500),
                        _text(stage.get("status"), 100),
                        record_type,
                        _csv_value(item, 4000),
                    ]
                )
    return stream.getvalue()


__all__ = ["VERSION", "_findings_csv", "_evidence_csv"]
