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
    # Frozen report views can omit their source path inventory. A verified native
    # ESLint target is positive Node source evidence even in that bounded view;
    # absence of a lockfile must not erase it.
    for record in _record_list(canonical):
        provenance = record.get("execution_provenance") or {}
        coverage = provenance.get("coverage") if isinstance(provenance, Mapping) else None
        coverage = coverage if isinstance(coverage, Mapping) else {}
        count = coverage.get("reported_target_count")
        if (
            _scanner_name(record.get("scanner_name") or record.get("tool")) == "eslint"
            and record.get("completed") is True
            and record.get("exact_commit_match") is True
            and coverage.get("status") == "reported_native_targets"
            and type(count) is int and count > 0
        ):
            node_source = True
    python_manifest = any(name in _PYTHON_MANIFEST_NAMES or
        (name.startswith("requirements") and name.endswith((".txt", ".in"))) for name in basenames)
    python_source = any(path.endswith(".py") for path in paths)
    return {
        "node_manifest": node_manifest,
        "node_source": node_source,
        "typescript_source": any(path.endswith((".ts", ".tsx")) for path in paths),
        "typescript_config": any(name.startswith("tsconfig") and name.endswith(".json") for name in basenames),
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


def _normalize_record(
    raw: Mapping[str, Any],
    signals: Mapping[str, bool],
) -> dict[str, Any]:
    """Derive applicability from inputs, independently of execution outcome."""
    from nico.node_scanner_applicability_v1 import justified_inapplicability, valid_input_inventory
    from nico.scanner_package_inventory_v1 import justified_no_packages

    record = deepcopy(dict(raw))
    scanner = _scanner_name(record.get("scanner_name") or record.get("tool") or record.get("scanner"))
    record["scanner_name"] = scanner
    state = _text(record.get("execution_state") or record.get("state") or record.get("status")).casefold().replace("-", "_")
    execution = {"completed": "complete", "completed_with_findings": "complete",
                 "timeout": "timed_out"}.get(state, state or "unavailable")
    legacy_inapplicable = state in {_NOT_APPLICABLE, "not_required", "inapplicable"}
    if legacy_inapplicable:
        execution = "not_requested" if record.get("execution_observed") is False else "unavailable"
    inventory = record.get("applicability_evidence")
    absent = justified_inapplicability(
        inventory, scanner, str(record.get("commit_sha") or record.get("target_commit_sha") or ""),
    )
    if scanner == "osv-scanner":
        absent = justified_no_packages(inventory, str(record.get("commit_sha") or record.get("target_commit_sha") or ""))
    positive = {
        "pip-audit": signals.get("python_manifest") or signals.get("python_source"),
        "bandit": signals.get("python_source"),
        "npm-audit": signals.get("node_manifest"),
        "eslint": signals.get("node_source"),
        "typescript": signals.get("typescript_source") or signals.get("typescript_config"),
        "semgrep": signals.get("python_source") or signals.get("node_source"),
        "osv-scanner": signals.get("python_manifest") or signals.get("node_manifest"),
        # History scanners apply to the exact Git snapshot, independent of language.
        "gitleaks": record.get("exact_commit_match") is True,
        "trufflehog": record.get("exact_commit_match") is True,
    }.get(scanner, False)
    if valid_input_inventory(inventory, str(record.get("commit_sha") or record.get("target_commit_sha") or "")):
        field = {"npm-audit": "node_dependency_paths", "typescript": "typescript_input_paths", "pip-audit": "python_input_paths"}.get(scanner)
        if field and isinstance(inventory.get(field), list) and inventory[field]:
            positive = True
    conflicting = bool(absent and positive)
    if conflicting:
        absent = positive = False
        applicability = "applicability_unproven"
        reason = "Retained supported inputs conflict with the complete-input-absence observation."
    elif absent:
        applicability = "not_applicable"
        reason = _text(record.get("applicability_reason")) or "Complete source-bound inventory contains no inputs supported by this scanner."
        if legacy_inapplicable and record.get("execution_observed_for_this_report") is False:
            execution = "not_requested"
    elif positive:
        applicability = "applicable"
        reason = "Retained repository inputs intersect the configured scanner capability."
    else:
        applicability = "applicability_unproven"
        reason = "Retained input evidence does not establish scanner applicability or complete absence of supported inputs."
    record.update(
        applicability_state=applicability,
        applicability_reason=reason,
        applicable=False if absent else True if positive else None,
        evidence_required=not absent,
        execution_state=execution,
        execution_reason=_text(record.get("execution_reason") or raw.get("failure_reason")
            or raw.get("failure_or_unavailable_reason") or raw.get("reason") or raw.get("error")),
    )
    if absent or legacy_inapplicable:
        # Do not grant execution credit to an inventory observation or an
        # unsupported historical inapplicability assertion.
        record.update(completed=False, verified=False, verified_complete=False,
                      verified_for_this_report=False)
        if legacy_inapplicable and not absent:
            record.setdefault("prior_applicability_reason", _reason(raw))
            record.update(state="unavailable", status="unavailable")
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

    required = [item for item in records if item.get("applicable") is not False]
    applicable = [item for item in records if item.get("applicable") is True]
    unproven = [item for item in records if item.get("applicable") is None]
    not_applicable = [item for item in records if item.get("applicable") is False]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]

    # Required execution includes applicability-unproven scanners. Preserve that
    # unresolved dimension without inventing failed or incomplete execution.
    canonical["requested_scanner_records"] = deepcopy(records)
    canonical["scanner_execution_records"] = deepcopy(required)
    canonical["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    assessment["requested_scanner_records"] = deepcopy(records)
    assessment["scanner_execution_records"] = deepcopy(required)
    assessment["completed_scanner_records"] = deepcopy([r for r in required if r.get("completed") is True])
    assessment["incomplete_scanner_records"] = deepcopy([r for r in required if r.get("completed") is not True])
    assessment["not_applicable_scanner_records"] = deepcopy(not_applicable)
    assessment["scanner_applicability_summary"] = {
        "version": VERSION,
        "repository_signals": dict(signals),
        "requested_scanners": len(records),
        "applicable_scanners": len(applicable),
        "completed_applicable_scanners": len(completed),
        "incomplete_applicable_scanners": len(incomplete),
        "not_applicable_scanners": len(not_applicable),
        "applicability_unproven_scanners": len(unproven),
        "applicability_unproven_tools": [item.get("scanner_name") for item in unproven],
        "not_applicable_tools": [item.get("scanner_name") for item in not_applicable],
        "not_applicable_receives_completion_credit": False,
        "unavailable_reserved_for_applicable_missing_evidence": False,
        "unavailable_does_not_establish_applicability": True,
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


def scanner_execution_summary(records: list[Mapping[str, Any]], *, spanish: bool = False) -> str:
    """Describe the two retained dimensions without renaming unknown inputs applicable."""
    if not records:
        return ("Las poblaciones de aplicabilidad y ejecución de analizadores no están verificadas." if spanish
            else "Scanner applicability and execution populations are unverified.")
    required = [r for r in records if r.get("applicable") is not False]
    complete = sum(r.get("completed") is True for r in required)
    applicable = sum(r.get("applicable") is True for r in required)
    unproven = len(required) - applicable
    excluded = len(records) - len(required)
    if spanish:
        return (f"Se completaron {complete} de {len(required)} ejecuciones requeridas de analizadores. "
            f"Aplicabilidad establecida: {applicable}; aplicabilidad no comprobada: {unproven}; no aplicables: {excluded}.")
    return (f"{complete} of {len(required)} required scanner executions completed. "
        f"Applicability established: {applicable}; applicability unproven: {unproven}; not applicable: {excluded}.")


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
