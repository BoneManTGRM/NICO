"""Optional, scope-limited observations; never a score or acceptance authority."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
from typing import Any

VERSION = "nico.source-function-measurements.v1"
KEY = "source_function_measurements"
IDENTITY_KEYS = ("run_id", "repository", "customer_id", "project_id", "snapshot_id", "snapshot_commit_sha")
LIMITATIONS = {
    "scope": "enumerated_functions_in_supplied_source_text_only",
    "whole_source_decision_burden": "unavailable",
    "module_and_class_initializer_residual": "unavailable",
    "python_lambdas": "not_enumerated",
    "typescript_anonymous_functions": "included_by_compiler_function_like_enumeration",
    "exclusion_policy": "existing_first_party_source_filter_and_supported_qt_xml_filter",
    "repository_inventory_coverage": "not_established_by_collector",
    "source_identity": "sha256_of_supplied_text_utf8_surrogatepass_not_original_repository_bytes",
    "cross_language_semantics": "different_counting_rules_do_not_imply_equal_quality",
    "authentication": "requires_protected_enclosing_evidence_and_existing_identity_gates",
}
DIMENSIONS = {"cc": ("cyclomatic_complexity", 1, (11, 21)),
              "nesting": ("max_nesting", 0, (5,)), "loc": ("loc", 0, (80,))}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or str(PurePosixPath(value)) != value or value.startswith("/") or ".." in value.split("/"):
        raise ValueError("noncanonical source path")
    return value


def _integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid measurement count")
    return value


def _dimension(histogram: dict[str, int], dimension: str) -> dict[str, Any]:
    if not isinstance(histogram, dict):
        raise ValueError("invalid histogram")
    minimum, thresholds = DIMENSIONS[dimension][1:]
    values = {}
    for key, count in histogram.items():
        if not isinstance(key, str) or not re.fullmatch(r"0|[1-9][0-9]*", key):
            raise ValueError("invalid histogram bin")
        values[_integer(int(key), minimum)] = _integer(count, 1)
    result = {"histogram": histogram, "measured_functions": sum(values.values()),
              "maximum": max(values, default=None),
              "absolute_counts_at_least": {str(t): sum(n for v, n in values.items() if v >= t) for t in thresholds}}
    if dimension == "cc":
        result["sum_cc_minus_1"] = sum((v - 1) * n for v, n in values.items())
    return result


def _metrics(functions: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"function_count": len(functions)}
    for dimension, (field, minimum, _) in DIMENSIONS.items():
        values = [_integer(f[field], minimum) for f in functions if f.get(field) is not None]
        result[dimension] = _dimension(dict(sorted(Counter(str(v) for v in values).items())), dimension)
    if result["cc"]["measured_functions"] != len(functions):
        raise ValueError("missing function CC")
    return result


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"function_count": sum(row["metrics"]["function_count"] for row in rows if row["metrics"] is not None)}
    for dimension in DIMENSIONS:
        histogram: Counter = Counter()
        for row in rows:
            if row["metrics"] is not None:
                histogram.update(row["metrics"][dimension]["histogram"])
        result[dimension] = _dimension(dict(sorted(histogram.items())), dimension)
    return result


def _producer() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in (
        "nico/source_function_measurements_v1.py", "nico/full_assessment_complexity_evidence.py",
        "nico/typescript_ast_complexity_v1.py", "scripts/typescript_ast_metrics.cjs")}


def build_measurements(source_files: dict[str, str], analyses: list[dict[str, Any]], ast_result: dict[str, Any]) -> dict[str, Any]:
    inventory = [{"path": _path(path), "source_text_sha256": _hash(text)} for path, text in sorted(source_files.items())]
    indexed = {}
    for analysis in analyses:
        path = _path(analysis["path"])
        if path in indexed or path not in source_files:
            raise ValueError("duplicate or out-of-scope analysis path")
        indexed[path] = analysis
    rows = []
    for item in inventory:
        analysis = indexed.get(item["path"], {})
        method = analysis.get("method")
        supported = method in {"python_ast", "typescript_compiler_ast"}
        functions = analysis.get("functions", [])
        if supported:
            if "functions" not in analysis or not isinstance(functions, list):
                raise ValueError("missing explicit function population")
            if "declared_function_count" in analysis:
                declared = analysis["declared_function_count"]
                if type(declared) is not int or declared < 0 or declared != len(functions):
                    raise ValueError("contradictory declared function population")
        if not isinstance(functions, list) or any(not isinstance(f, dict) or f.get("path") != item["path"] or f.get("method") != method for f in functions):
            raise ValueError("invalid function provenance")
        status = ("partial" if analysis.get("status") != "analyzed" or analysis.get("parser_diagnostic_count", 0) else "measured") if supported else ("unsupported" if analysis else "missing")
        rows.append({**item, "status": status, "language": analysis.get("language"), "method": method,
                     "parser_version": platform.python_version() if method == "python_ast" else ast_result.get("parser_version") if method == "typescript_compiler_ast" else None,
                     "loc_methods": sorted({f["loc_method"] for f in functions if f.get("loc_method")}),
                     "population": {"enumerated_count": len(functions), "declared_count": analysis.get("declared_function_count")} if supported else None,
                     "metrics": _metrics(functions) if supported else None})
    return {"version": VERSION, "identity": None, "limitations": dict(LIMITATIONS),
            "producer_source_sha256": _producer(), "inventory": inventory,
            "inventory_sha256": _hash(_json(inventory)), "files": rows, "aggregate": _aggregate(rows)}


def _validate_measurements(value: Any, *, expected_identity: dict[str, Any] | None,
                          expected_inventory: list[dict[str, str]]) -> bool:
    """Validate against trusted surrounding identity/inventory, not self-asserted hashes.

    A missing optional object is unavailable, never reconstructed from rounded means.
    This checks consistency and binding, not authenticity or source recomputation.
    """
    if value is None:
        return False
    if isinstance(value, dict) and value.get("status") == "unavailable":
        if set(value) != {"version", "status", "reason", "identity", "limitations"} or value.get("version") != VERSION or value.get("identity") is not None or value.get("limitations") != LIMITATIONS or not isinstance(value.get("reason"), str) or not value["reason"]:
            raise ValueError("malformed unavailable measurement attachment")
        return False
    if not isinstance(value, dict) or value.get("version") != VERSION or value.get("limitations") != LIMITATIONS:
        raise ValueError("unsupported measurement contract")
    if _json(value.get("identity")) != _json(expected_identity):
        raise ValueError("measurement identity mismatch")
    if expected_identity is not None:
        if set(expected_identity) != set(IDENTITY_KEYS) or any(not isinstance(v, str) or not v for v in expected_identity.values()) or not re.fullmatch(r"[0-9a-f]{40}", expected_identity["snapshot_commit_sha"]):
            raise ValueError("incomplete exact-source identity")
    inventory = value.get("inventory")
    if not isinstance(inventory, list) or _json(inventory) != _json(expected_inventory) or value.get("inventory_sha256") != _hash(_json(inventory)):
        raise ValueError("measurement inventory mismatch")
    if inventory != sorted(inventory, key=lambda item: item["path"]):
        raise ValueError("noncanonical inventory order")
    seen = set()
    for item in inventory:
        path = _path(item["path"])
        if path in seen or set(item) != {"path", "source_text_sha256"} or not re.fullmatch(r"[0-9a-f]{64}", item["source_text_sha256"]):
            raise ValueError("invalid or duplicate inventory")
        seen.add(path)
    producer = value.get("producer_source_sha256")
    if not isinstance(producer, dict) or set(producer) != set(_producer()) or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in producer.values()):
        raise ValueError("missing producer provenance")
    rows = value.get("files")
    if not isinstance(rows, list) or len(rows) != len(inventory):
        raise ValueError("missing measurement rows")
    for item, row in zip(inventory, rows):
        if any(row.get(k) != v for k, v in item.items()):
            raise ValueError("file identity mismatch")
        if row.get("status") not in {"measured", "partial", "missing", "unsupported"}:
            raise ValueError("unknown coverage status")
        metrics = row.get("metrics")
        if row["status"] in {"missing", "unsupported"}:
            if metrics is not None:
                raise ValueError("unsupported metrics must be unavailable")
            continue
        if row.get("method") not in {"python_ast", "typescript_compiler_ast"} or not isinstance(row.get("parser_version"), str) or not row["parser_version"]:
            raise ValueError("missing parser provenance")
        expected_language = "python" if row["method"] == "python_ast" else "javascript-typescript"
        if row.get("language") != expected_language or not isinstance(row.get("loc_methods"), list) or any(not isinstance(m, str) or not m for m in row["loc_methods"]):
            raise ValueError("invalid method provenance")
        count = _integer(metrics["function_count"])
        population = row["population"]
        if set(population) != {"enumerated_count", "declared_count"} or _integer(population["enumerated_count"]) != count:
            raise ValueError("function population mismatch")
        if population["declared_count"] is not None and _integer(population["declared_count"]) != count:
            raise ValueError("declared function population mismatch")
        expected = {"function_count": count}
        for dimension in DIMENSIONS:
            expected[dimension] = _dimension(metrics[dimension]["histogram"], dimension)
            n = expected[dimension]["measured_functions"]
            if n > count or (dimension == "cc" and n != count):
                raise ValueError("histogram population mismatch")
        if _json(metrics) != _json(expected):
            raise ValueError("file aggregate mismatch")
    if _json(value.get("aggregate")) != _json(_aggregate(rows)):
        raise ValueError("aggregate reconciliation failed")
    return True


def validate_measurements(value: Any, *, expected_identity: dict[str, Any] | None,
                          expected_inventory: list[dict[str, str]]) -> bool:
    try:
        return _validate_measurements(value, expected_identity=expected_identity, expected_inventory=expected_inventory)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed measurement object") from exc


def bind_measurements(evidence: dict[str, Any]) -> None:
    """Attach snapshot identity immediately before existing JSON evidence persistence."""
    if KEY not in evidence:
        return
    value = deepcopy(evidence[KEY])
    identity = {key: evidence.get(key) for key in IDENTITY_KEYS}
    if not validate_measurements(value, expected_identity=None, expected_inventory=value.get("inventory", [])):
        return
    # Legacy/incomplete envelopes remain unbound observations, without changing
    # existing report acceptance. Consumers must supply a complete expected identity.
    if any(not isinstance(v, str) or not v for v in identity.values()) or not re.fullmatch(r"[0-9a-f]{40}", identity["snapshot_commit_sha"]):
        return
    value["identity"] = identity
    validate_measurements(value, expected_identity=identity, expected_inventory=value["inventory"])
    evidence[KEY] = value


def build_optional_measurements(source_files: dict[str, str], analyses: list[dict[str, Any]], ast_result: dict[str, Any]) -> dict[str, Any]:
    """Only optional retention validation may degrade to unavailable.

    Source acquisition, parsing and legacy metrics execute outside this boundary;
    their errors are not caught here. An unavailable attachment grants no credit.
    """
    try:
        value = build_measurements(source_files, analyses, ast_result)
        validate_measurements(value, expected_identity=None, expected_inventory=value["inventory"])
        return value
    except ValueError as exc:
        return {"version": VERSION, "status": "unavailable", "reason": str(exc),
                "identity": None, "limitations": dict(LIMITATIONS)}
