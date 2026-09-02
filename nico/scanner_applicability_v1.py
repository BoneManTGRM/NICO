from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.scanner-applicability.v2"
_NOT_APPLICABLE = "not_applicable"
_NODE_MANIFEST_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
}
_PYTHON_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
}
_PATH_TOKEN = re.compile(
    r"(?P<path>[A-Za-z0-9_@.+\-/]+\.(?:json|ya?ml|toml|txt|lock|py|js|jsx|ts|tsx))",
    re.IGNORECASE,
)
_SKIP_SIGNAL_KEYS = {
    "scanner_execution_records",
    "completed_scanner_records",
    "incomplete_scanner_records",
    "not_applicable_scanner_records",
    "requested_scanner_records",
    "findings",
    "unavailable",
    "unavailable_data_notes",
    "failure_reason",
    "failure_or_unavailable_reason",
    "reason",
    "error",
    "stderr",
    "stdout",
    "markdown",
    "html",
    "pdf_base64",
}
_NEGATIVE_PATH_CONTEXT = (
    "not found",
    "not present",
    "does not exist",
    "did not exist",
    "unavailable",
    "missing",
    "no readable",
    "could not be read",
    "was not installed",
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


def _repository_path_strings(value: Any, *, key: str = "", depth: int = 0) -> list[str]:
    """Collect positive repository path evidence without reading scanner errors as files."""

    if depth > 7:
        return []
    normalized_key = str(key or "").casefold()
    if normalized_key in _SKIP_SIGNAL_KEYS:
        return []
    if isinstance(value, Mapping):
        output: list[str] = []
        for child_key, item in value.items():
            output.extend(_repository_path_strings(item, key=str(child_key), depth=depth + 1))
        return output
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(_repository_path_strings(item, key=key, depth=depth + 1))
        return output
    if not isinstance(value, str):
        return []

    text = _text(value).replace("\\", "/")
    lowered = text.casefold()
    if any(marker in lowered for marker in _NEGATIVE_PATH_CONTEXT):
        return []

    path_like_key = any(
        marker in normalized_key
        for marker in (
            "path",
            "file",
            "manifest",
            "lockfile",
            "tree",
            "source",
            "root_item",
            "deployment",
            "location",
        )
    )
    tokens = [match.group("path") for match in _PATH_TOKEN.finditer(text)]
    if path_like_key:
        tokens.append(text)
    return [token.strip("`'\" ,.;:()[]{}") for token in tokens if token.strip()]


def _repository_signals(canonical: Mapping[str, Any]) -> dict[str, bool]:
    paths = [item.casefold().replace("\\", "/") for item in _repository_path_strings(canonical)]
    basenames = [path.rsplit("/", 1)[-1] for path in paths]
    node_manifest = any(name in _NODE_MANIFEST_NAMES for name in basenames)
    node_source = any(path.endswith((".js", ".jsx", ".ts", ".tsx")) for path in paths)
    python_manifest = any(name in _PYTHON_MANIFEST_NAMES for name in basenames)
    python_source = any(path.endswith(".py") for path in paths)
    return {
        "node_manifest": node_manifest,
        "node_source": node_source,
        "python_manifest": python_manifest,
        "python_source": python_source,
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
    has_node_project = bool(signals.get("node_manifest") or signals.get("node_source"))
    has_python_project = bool(signals.get("python_manifest") or signals.get("python_source"))

    if scanner == "pip-audit":
        missing_python_manifest = any(
            marker in lowered
            for marker in (
                "requirements.txt not found",
                "no supported python dependency manifest",
                "python dependency manifest is missing",
            )
        )
        if missing_python_manifest and not has_python_project:
            return True, (
                "No supported Python dependency manifest or source tree exists at the assessed commit; "
                "pip-audit is not applicable to this repository snapshot."
            )

    if scanner == "npm-audit":
        missing_lock = any(
            marker in lowered
            for marker in (
                "package-lock.json not found",
                "no javascript lockfile",
                "no package-lock.json with an adjacent package.json was found",
            )
        )
        if missing_lock and not has_node_project:
            return True, (
                "No supported JavaScript package manifest, lockfile, or source tree exists at the assessed commit; "
                "npm-audit is not applicable to this repository snapshot."
            )

    if scanner == "eslint":
        missing_project = any(
            marker in lowered
            for marker in (
                "apps/web/package.json not found",
                "package.json not found",
                "no eslint configuration or lint script",
                "eslint configuration or lint script was found",
                "eslint was not installed by the exact package-lock",
                "no supported javascript or typescript source files were found",
                "project dependencies were not prepared",
            )
        )
        if missing_project and not has_node_project:
            return True, (
                "No JavaScript/TypeScript project or source tree exists at the assessed commit; "
                "ESLint is not applicable to this repository snapshot."
            )

    if scanner == "typescript":
        missing_project = any(
            marker in lowered
            for marker in (
                "apps/web/package.json not found",
                "package.json not found",
                "tsconfig.json not found",
                "typescript evidence",
                "tsc was not installed by the exact package-lock",
                "project dependencies were not prepared",
            )
        )
        if missing_project and not has_node_project:
            return True, (
                "No TypeScript project, source tree, or tsconfig exists at the assessed commit; "
                "TypeScript compilation is not applicable to this repository snapshot."
            )

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

    already_not_applicable = (
        state in {_NOT_APPLICABLE, "not_required", "inapplicable"}
        or record.get("applicable") is False
    )
    inferred, inferred_reason = _explicitly_not_applicable(scanner, reason, signals)
    if already_not_applicable or (
        state
        in {
            "unavailable",
            "missing",
            "not_installed",
            "not_available",
            # Older frozen reports projected explicit technology-mismatch
            # unavailability into ``failed`` before retaining the exact reason.
            # The repository-signal guard above keeps real Node-project failures
            # applicable and fail-closed.
            "failed",
        }
        and inferred
    ):
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
                "applicability_reason": _text(record.get("applicability_reason"))
                or inferred_reason
                or reason
                or "The analyzer does not apply to the repository technology detected at the assessed commit.",
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
    candidates = (
        canonical.get("requested_scanner_records"),
        canonical.get("scanner_execution_records"),
        assessment.get("requested_scanner_records"),
        assessment.get("scanner_execution_records"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def normalize_scanner_applicability_canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    """Separate technology-inapplicable analyzers from missing execution evidence.

    This projection never grants completion or verification credit. It converts only
    an explicit repository-technology mismatch into a machine-readable
    ``not_applicable`` state. Missing binaries, timeouts, malformed output, missing
    configuration in an otherwise applicable project, and applicable-tool failures
    remain unavailable or failed.
    """

    canonical = deepcopy(dict(value))
    signals = _repository_signals(canonical)
    records = [_normalize_record(item, signals) for item in _record_list(canonical)]

    applicable = [item for item in records if item.get("applicable") is not False]
    not_applicable = [item for item in records if item.get("applicable") is False]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]

    # The authoritative execution population contains only analyzers that apply to
    # this repository. Requested and not-applicable records remain separately
    # retained so no analyzer disappears and no not-applicable tool receives credit.
    canonical["requested_scanner_records"] = deepcopy(records)
    canonical["scanner_execution_records"] = deepcopy(applicable)
    canonical["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    assessment["requested_scanner_records"] = deepcopy(records)
    assessment["scanner_execution_records"] = deepcopy(applicable)
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    assessment["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment["scanner_applicability_summary"] = {
        "version": VERSION,
        "repository_signals": dict(signals),
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
            "requested_scanner_population_retained": True,
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
