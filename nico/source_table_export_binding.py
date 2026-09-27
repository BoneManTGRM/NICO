"""Bind concise PDF source-table references to complete pre-render evidence.

Commitments are captured before presentation and checked against both retained
canonical surfaces after exact-artifact finalization. This verifies preservation;
it confers no report approval, delivery authorization or target qualification.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from nico.comprehensive_source_table_presentation_v1 import (
    MAX_INLINE_SOURCE_TABLE_ROWS,
    _require_json_value,
)
from nico.report_pdf_text import extract_pdf_page_texts


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def capture_source_table_evidence(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Capture all valid structured table instances without copying their rows."""
    output = []
    for stage in canonical.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        for table in stage.get("structured_tables") or []:
            if not isinstance(table, Mapping):
                continue
            rows = table.get("rows")
            if not isinstance(rows, list) or not table.get("columns"):
                continue
            payload = {key: table.get(key) for key in ("title", "columns", "rows")}
            _require_json_value(payload)
            output.append({
                "stage_id": stage.get("stage_id"),
                "sha256": hashlib.sha256(_encoded(payload)).hexdigest(),
                "row_count": len(rows),
            })
    return output


def _population(evidence: list[dict[str, Any]]) -> Counter[bytes]:
    # Preserve duplicate occurrences and JSON types; Python equality alone
    # conflates booleans with integers. Stage/table order is not a row mutation.
    return Counter(_encoded(item) for item in evidence)


def _bound_json(package: Mapping[str, Any], value_key: str, hash_key: str) -> tuple[Any, bytes]:
    value = package.get(value_key)
    if type(value) is not str:
        raise ValueError(f"source_table_export_missing:{value_key}")
    encoded = value.encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != package.get(hash_key):
        raise ValueError(f"source_table_export_hash_mismatch:{value_key}")
    return json.loads(value), encoded


def validate_source_table_evidence(
    expected: list[dict[str, Any]], package: Mapping[str, Any]
) -> dict[str, Any]:
    """Reject row loss/substitution or unbound large-table PDF summaries."""
    canonical = package.get("json")
    if not isinstance(canonical, Mapping):
        if expected:
            raise ValueError("source_table_canonical_missing")
        canonical = {}
    population = _population(expected)
    if _population(capture_source_table_evidence(canonical)) != population:
        raise ValueError("source_table_canonical_population_changed")
    large = [item for item in expected if item["row_count"] > MAX_INLINE_SOURCE_TABLE_ROWS]
    if not large and not any(key in package for key in (
        "canonical_json", "canonical_json_sha256", "artifact_manifest",
        "evidence_manifest_json", "evidence_manifest_sha256",
    )):
        return {"table_instances": len(expected), "summarized_tables": 0}

    exported, encoded = _bound_json(package, "canonical_json", "canonical_json_sha256")
    if not isinstance(exported, Mapping) or _population(capture_source_table_evidence(exported)) != population:
        raise ValueError("source_table_export_population_changed")
    manifest, _ = _bound_json(package, "evidence_manifest_json", "evidence_manifest_sha256")
    if not isinstance(manifest, Mapping) or _encoded(manifest) != _encoded(package.get("artifact_manifest")):
        raise ValueError("source_table_detached_manifest_mismatch")
    entries = [item for item in manifest.get("artifacts", [])
               if isinstance(item, Mapping) and item.get("artifact_type") == "canonical_json"]
    if len(entries) != 1:
        raise ValueError("source_table_canonical_manifest_entry_missing_or_ambiguous")
    entry = entries[0]
    if (entry.get("sha256") != hashlib.sha256(encoded).hexdigest()
            or type(entry.get("size_bytes")) is not int
            or entry["size_bytes"] != len(encoded)):
        raise ValueError("source_table_canonical_manifest_binding_mismatch")

    if not large:
        return {"table_instances": len(expected), "summarized_tables": 0,
                "canonical_json_sha256": hashlib.sha256(encoded).hexdigest()}

    try:
        pdf = base64.b64decode(package["pdf_base64"], validate=True)
        if hashlib.sha256(pdf).hexdigest() != package.get("pdf_sha256"):
            raise ValueError("source_table_pdf_hash_mismatch")
        text = "\n".join(extract_pdf_page_texts(pdf))
    except (KeyError, TypeError) as error:
        raise ValueError("source_table_pdf_missing") from error
    # The renderer emits each token on one line. Its final count must have a
    # real boundary: 49 cannot be satisfied by a reference to 490 rows.
    tokens = set(re.findall(r"(?<![A-Za-z0-9_-])NICO-TABLE-([a-f0-9]{64})-([0-9]+)(?![A-Za-z0-9_-])", text))
    required = {(item["sha256"], str(item["row_count"])) for item in large}
    if not required.issubset(tokens):
        raise ValueError("source_table_pdf_reference_missing_or_changed")
    return {"table_instances": len(expected), "summarized_tables": len(required),
            "canonical_json_sha256": hashlib.sha256(encoded).hexdigest()}


__all__ = ["capture_source_table_evidence", "validate_source_table_evidence"]
