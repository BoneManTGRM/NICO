from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.scanner-applicability.v1"
_NOT_APPLICABLE = "not_applicable"
_NODE_MANIFEST_MARKERS = (
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }.get(normalized, normalized)


def _walk_strings(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    if isinstance(value, Mapping):
        output: list[str] = []
        for item in value.values():
            output.extend(_walk_strings(item, depth=depth + 1))
        return output
    if isinstance(value, (list, tuple, set)):
        output = []
        for item in value:
            output.extend(_walk_strings(item, depth=depth + 1))
        return output
    if isinstance(value, str):
        return [_text(value)]
    return []


def _repository_signals(canonical: Mapping[str, Any]) -> dict[str, bool]:
    values = [item.casefold().replace("\\", "/") for item in _walk_strings(canonical)]
    node_manifest = any(
        marker in value
        for value in values
        for marker in _NODE_MANIFEST_MARKERS
    )
    node_source = any(
        value.endswith((".js", ".jsx", ".ts", ".tsx"))
        or any(suffix in value for suffix in (".js:", ".jsx:", ".ts:", ".tsx:"))
        for value in values
    )
    python_manifest = any(
        marker in value
        for value in values
        for marker in ("requirements.txt", "pyproject.toml", "poetry.lock", "pipfile")
    )
    return {
        "node_manifest": node_manifest,
        "node_source": node_source,
        "python_manifest": python_manifest,
    }


def _reason(record: Mapping[str, Any]) -> str:
    return _text(
        record.get("applicability_reason")
        or record.get("failure_reason")
        or record.get("failure_or_unavailable_reason")
        or record.get("reason")
        or record.get("error")
        or record.get("stderr")
    )


def _explicitly_not_applicable(
    scanner: str,
    reason: str,
    signals: Mapping[str, bool],
) -> tuple[bool, str]:
    lowered = reason.casefold()

    if scanner == "npm-audit":
        missing_lock = "package-lock.json not found" in lowered or "no javascript lockfile" in lowered
        if missing_lock or (not signals.get("node_manifest") and "package-lock" in lowered):
            return True, "No supported JavaScript lockfile exists at the assessed commit; npm-audit is not applicable to this repository snapshot."

    if scanner == "eslint":
        missing_project = any(
            marker in lowered
            for marker in (
                "apps/web/package.json not found",
                "no eslint configuration or lint script",
                "eslint configuration or lint script was found",
                "eslint was not installed by the exact package-lock",
                "project dependencies were not prepared",
            )
        )
        if missing_project and not (signals.get("node_manifest") or signals.get("node_source")):
            return True, "No configured JavaScript/TypeScript project or ESLint contract exists at the assessed commit; ESLint is not applicable."

    if scanner == "typescript":
        missing_project = any(
            marker in lowered
            for marker in (
                "apps/web/package.json not found",
                "tsconfig.json not found",
                "typescript evidence",
                "tsc was not installed by the exact package-lock",
                "project dependencies were not prepared",
            )
        )
        if missing_project and not (signals.get("node_manifest") or signals.get("node_source")):
            return True, "No configured TypeScript project or tsconfig exists at the assessed commit; TypeScript compilation is not applicable."

    return False, ""


def _normalize_record(
    raw: Mapping[str, Any],
    signals: Mapping[str, bool],
) -> dict[str, Any]:
    record = deepcopy(dict(raw))
    scanner = _scanner_name(record.get("scanner_name") or record.get("tool") or record.get("scanner"))
    record["scanner_name"] = scanner
    state = _text(record.get("state") or record.get("status")).casefold().replace("-", "_")
    reason = _reason(record)

    already_not_applicable = state in {_NOT_APPLICABLE, "not_required", "inapplicable"} or record.get("applicable") is False
    inferred, inferred_reason = _explicitly_not_applicable(scanner, reason, signals)
    if already_not_applicable or (state in {"unavailable", "missing", "not_installed", "not_available"} and inferred):
        record.update(
            {
                "raw_state": record.get("raw_state") or state or "unavailable",
                "state": _NOT_APPLICABLE,
                "status": _NOT_APPLICABLE,
                "completed": False,
                "verified": False,
                "verified_complete": False,
                "verified_for_this_report": False,
                "applicable": False,
                "evidence_required": False,
                "applicability_reason": _text(record.get("applicability_reason")) or inferred_reason or reason or "The analyzer does not apply to the repository technology detected at the assessed commit.",
                "failure_reason": "",
                "failure_or_unavailable_reason": "",
            }
        )
        return record

    record.setdefault("applicable", True)
    record.setdefault("evidence_required", True)
    return record


def _record_list(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    for candidate in (
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    ):
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def normalize_scanner_applicability_canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    """Separate technology-inapplicable analyzers from missing execution evidence.

    This projection never grants completion or verification credit. It only converts
    an explicit repository-mismatch reason into a machine-readable not-applicable
    state. Missing binaries, timeouts, malformed output, and applicable-tool failures
    remain unavailable or failed.
    """

    canonical = deepcopy(dict(value))
    signals = _repository_signals(canonical)
    records = [_normalize_record(item, signals) for item in _record_list(canonical)]

    applicable = [item for item in records if item.get("applicable") is not False]
    not_applicable = [item for item in records if item.get("applicable") is False]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]

    canonical["scanner_execution_records"] = deepcopy(records)
    canonical["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    assessment["scanner_execution_records"] = deepcopy(records)
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    assessment["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment["scanner_applicability_summary"] = {
        "version": VERSION,
        "requested_scanners": len(records),
        "applicable_scanners": len(applicable),
        "completed_applicable_scanners": len(completed),
        "incomplete_applicable_scanners": len(incomplete),
        "not_applicable_scanners": len(not_applicable),
        "not_applicable_tools": [item.get("scanner_name") for item in not_applicable],
        "not_applicable_receives_completion_credit": False,
        "unavailable_reserved_for_applicable_missing_evidence": True,
    }
    canonical["assessment"] = assessment

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "scanner_applicability_version": VERSION,
            "not_applicable_separate_from_unavailable": True,
            "not_applicable_separate_from_completed": True,
            "applicable_missing_evidence_remains_fail_closed": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


def normalize_scanner_applicability_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    canonical = normalize_scanner_applicability_canonical(canonical)
    result["json"] = canonical
    result["scanner_applicability"] = deepcopy(
        (canonical.get("assessment") or {}).get("scanner_applicability_summary") or {}
    )
    return result


__all__ = [
    "VERSION",
    "normalize_scanner_applicability_canonical",
    "normalize_scanner_applicability_package",
]
