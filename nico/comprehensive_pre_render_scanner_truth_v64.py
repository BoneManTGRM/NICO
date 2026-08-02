from __future__ import annotations

import re
import sys
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from nico import comprehensive_client_readiness_v59 as v59

VERSION = "nico.comprehensive_pre_render_scanner_truth.v64"
_INSTALL_MARKER = "_nico_pre_render_scanner_truth_v64"

_STRICT_INCOMPLETE_LIST_FIELDS = frozenset(
    {
        "incomplete_analyzers",
        "incomplete_scanners",
        "failed_analyzers",
        "failed_scanners",
    }
)
_BLOCKER_LIST_FIELDS = frozenset(
    {
        "analyzer_evidence_blockers",
        "scanner_evidence_blockers",
    }
)
_INCOMPLETE_COUNT_FIELDS = frozenset(
    {
        "incomplete_applicable_analyzers",
        "incomplete_applicable_scanners",
        "incomplete_analyzer_count",
        "incomplete_scanner_count",
    }
)
_COMPLETED_COUNT_FIELDS = frozenset(
    {
        "completed_applicable_analyzers",
        "completed_applicable_scanners",
        "completed_analyzer_count",
        "completed_scanner_count",
    }
)
_HEAVY_TEXT_FIELDS = frozenset({"pdf_base64", "html", "markdown"})
_PASSTHROUGH_FIELDS = frozenset({"report_package", "reports"})
_COVERAGE_KEY_RE = re.compile(
    r"(?:analy[sz]er|scanner).*(?:coverage|completion)|"
    r"(?:coverage|completion).*(?:analy[sz]er|scanner)",
    re.I,
)
_STALE_FLATTENED_PATH_RE = re.compile(
    r"(?P<label>(?:^|[.\s]))incomplete_(?:analyzers|scanners)"
    r"\[\d+\]\s*[:=]\s*(?P<value>[^\n]+)",
    re.I,
)
_REQUIRED_TOOLS = frozenset(
    {
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    }
)
_DROP = object()


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _names(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    output: set[str] = set()
    for item in value:
        name = v59._tool(item)
        if name:
            output.add(name)
    return output


def _nested_mappings(node: Any, key_name: str) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            normalized = str(key)
            if normalized == key_name and isinstance(value, Mapping):
                output.append(value)
            if normalized in _HEAVY_TEXT_FIELDS:
                continue
            output.extend(_nested_mappings(value, key_name))
    elif isinstance(node, list):
        for value in node:
            output.extend(_nested_mappings(value, key_name))
    return output


def _scanner_record_lists(node: Any) -> list[list[Mapping[str, Any]]]:
    output: list[list[Mapping[str, Any]]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            normalized = str(key)
            if normalized == "scanner_execution_records" and isinstance(value, list):
                records = [item for item in value if isinstance(item, Mapping)]
                if records:
                    output.append(records)
            if normalized in _HEAVY_TEXT_FIELDS:
                continue
            output.extend(_scanner_record_lists(value))
    elif isinstance(node, list):
        for value in node:
            output.extend(_scanner_record_lists(value))
    return output


def _best_contract(stage_results: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = _nested_mappings(stage_results, "client_readiness_contract")
    if not candidates:
        return {}

    def quality(contract: Mapping[str, Any]) -> tuple[int, int, int]:
        source = _text(contract.get("authoritative_source"))
        denominator = _safe_int(contract.get("coverage_denominator"))
        named = len(_names(contract.get("requested_exact_run_scanners")))
        return (1 if source else 0, denominator, named)

    return max(candidates, key=quality)


def _live_manifest(stage_results: Mapping[str, Any]) -> Mapping[str, Any]:
    dependency = _mapping(stage_results.get("dependency_security_static_analysis"))
    direct = dependency.get("scanner")
    if isinstance(direct, Mapping):
        return direct

    triage = _mapping(stage_results.get("deep_scanner_triage"))
    direct = triage.get("scanner_triage")
    if isinstance(direct, Mapping):
        return direct

    candidates: list[Mapping[str, Any]] = []
    for key in ("live_scanner_evidence", "scanner_run_summary", "scanner"):
        candidates.extend(_nested_mappings(stage_results, key))
    for candidate in candidates:
        if any(
            field in candidate
            for field in (
                "tools_requested",
                "tools_run",
                "failed_tools",
                "unavailable_tools",
                "timed_out_tools",
            )
        ):
            return candidate
    return {}


def derive_authoritative_scanner_truth(
    stage_results: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive one exact-run scanner population before report text is flattened.

    Direct exact-commit records and the current scanner manifest outrank historical or
    recursively projected report aliases. A completed current-run scanner cannot remain
    in a stale incomplete list merely because an earlier report stage copied that list.
    """

    requested: set[str] = set()
    completed: set[str] = set()
    hard_incomplete: set[str] = set()
    soft_incomplete: set[str] = set()
    sources: list[str] = []

    record_sets = _scanner_record_lists(stage_results)
    records = max(record_sets, key=len) if record_sets else []
    if records:
        sources.append("direct_scanner_execution_records")
    for record in records:
        state = v59._scanner_state(record)
        if state is None:
            continue
        name = str(state["scanner_name"])
        requested.add(name)
        if state.get("completed") is True:
            completed.add(name)
        else:
            hard_incomplete.add(name)

    live = _live_manifest(stage_results)
    if live:
        sources.append("live_scanner_manifest")
    live_requested = _names(live.get("tools_requested"))
    live_run = _names(live.get("tools_run"))
    live_failed = (
        _names(live.get("failed_tools"))
        | _names(live.get("unavailable_tools"))
        | _names(live.get("timed_out_tools"))
    )
    requested |= live_requested | live_run | live_failed
    completed |= live_run - live_failed
    hard_incomplete |= live_failed

    contract = _best_contract(stage_results)
    if contract:
        sources.append("client_readiness_contract")
    contract_requested = _names(contract.get("requested_exact_run_scanners"))
    contract_completed = _names(contract.get("completed_exact_commit_scanners"))
    contract_incomplete = _names(contract.get("incomplete_analyzers"))
    requested |= contract_requested | contract_completed | contract_incomplete
    completed |= contract_completed
    soft_incomplete |= contract_incomplete

    # A current explicit failure wins. Otherwise current exact completion wins over a
    # copied historical incomplete alias.
    completed -= hard_incomplete
    incomplete = hard_incomplete | (soft_incomplete - completed) | (requested - completed)

    if requested == _REQUIRED_TOOLS:
        requested = set(_REQUIRED_TOOLS)

    coverage = round(100 * len(completed & requested) / len(requested)) if requested else 0
    return {
        "version": VERSION,
        "requested": sorted(requested),
        "completed": sorted(completed & requested),
        "incomplete": sorted(incomplete & requested),
        "coverage": coverage,
        "authoritative_sources": sources,
        "truth_available": bool(requested),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _entry_tool(value: Any, requested: set[str]) -> str:
    name = v59._tool(value)
    if name in requested:
        return name
    text = _text(value).casefold().replace("_", "-")
    for candidate in sorted(requested, key=len, reverse=True):
        if re.search(
            rf"(?<![a-z0-9-]){re.escape(candidate)}(?![a-z0-9-])",
            text,
        ):
            return candidate
    return ""


def _sanitize_text(
    value: str,
    *,
    requested: set[str],
    incomplete: set[str],
    removed: list[str],
    path: str,
) -> Any:
    match = _STALE_FLATTENED_PATH_RE.search(value)
    if not match or not requested:
        return value
    name = _entry_tool(match.group("value"), requested)
    if not name or name in incomplete:
        return value
    removed.append(path or "<flattened-text>")
    return _DROP


def _sanitize_node(
    node: Any,
    *,
    requested: set[str],
    completed: set[str],
    incomplete: set[str],
    coverage: int,
    removed: list[str],
    path: str = "stage_results",
) -> Any:
    if isinstance(node, str):
        return _sanitize_text(
            node,
            requested=requested,
            incomplete=incomplete,
            removed=removed,
            path=path,
        )
    if isinstance(node, list):
        output: list[Any] = []
        for index, item in enumerate(node):
            sanitized = _sanitize_node(
                item,
                requested=requested,
                completed=completed,
                incomplete=incomplete,
                coverage=coverage,
                removed=removed,
                path=f"{path}[{index}]",
            )
            if sanitized is not _DROP:
                output.append(sanitized)
        return output
    if not isinstance(node, Mapping):
        return deepcopy(node)

    output: dict[str, Any] = {}
    for raw_key, raw_value in node.items():
        key = str(raw_key)
        normalized = key.casefold()
        current_path = f"{path}.{key}"

        # Large prior report artifacts are ignored by the native stage flattener. Keep
        # them by reference rather than copying or scanning megabytes of base64/text.
        if normalized in _HEAVY_TEXT_FIELDS or normalized in _PASSTHROUGH_FIELDS:
            output[key] = raw_value
            continue

        if (
            normalized in _STRICT_INCOMPLETE_LIST_FIELDS
            and isinstance(raw_value, list)
            and requested
        ):
            retained: list[Any] = []
            for index, item in enumerate(raw_value):
                name = _entry_tool(item, requested)
                if not name or name in incomplete:
                    sanitized = _sanitize_node(
                        item,
                        requested=requested,
                        completed=completed,
                        incomplete=incomplete,
                        coverage=coverage,
                        removed=removed,
                        path=f"{current_path}[{index}]",
                    )
                    if sanitized is not _DROP:
                        retained.append(sanitized)
                else:
                    removed.append(f"{current_path}[{index}]")
            output[key] = retained
            continue

        if normalized in _BLOCKER_LIST_FIELDS and isinstance(raw_value, list) and requested:
            retained = []
            for index, item in enumerate(raw_value):
                name = _entry_tool(item, requested)
                if name and name not in incomplete:
                    removed.append(f"{current_path}[{index}]")
                    continue
                sanitized = _sanitize_node(
                    item,
                    requested=requested,
                    completed=completed,
                    incomplete=incomplete,
                    coverage=coverage,
                    removed=removed,
                    path=f"{current_path}[{index}]",
                )
                if sanitized is not _DROP:
                    retained.append(sanitized)
            output[key] = retained
            continue

        if normalized in _INCOMPLETE_COUNT_FIELDS and requested:
            output[key] = len(incomplete)
            continue

        if normalized in _COMPLETED_COUNT_FIELDS and requested:
            output[key] = len(completed)
            continue

        if (
            requested
            and _COVERAGE_KEY_RE.search(key)
            and isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
        ):
            output[key] = coverage
            continue

        sanitized = _sanitize_node(
            raw_value,
            requested=requested,
            completed=completed,
            incomplete=incomplete,
            coverage=coverage,
            removed=removed,
            path=current_path,
        )
        if sanitized is not _DROP:
            output[key] = sanitized
    return output


def canonicalize_stage_results_before_render(
    stage_results: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    truth = derive_authoritative_scanner_truth(stage_results)
    if truth["truth_available"] is not True:
        return dict(stage_results), {
            **truth,
            "status": "not_applied_no_authoritative_scanner_population",
            "removed_stale_alias_count": 0,
            "removed_stale_alias_paths": [],
        }

    requested = set(truth["requested"])
    completed = set(truth["completed"])
    incomplete = set(truth["incomplete"])
    removed: list[str] = []
    sanitized = _sanitize_node(
        stage_results,
        requested=requested,
        completed=completed,
        incomplete=incomplete,
        coverage=int(truth["coverage"]),
        removed=removed,
    )
    if not isinstance(sanitized, dict):
        raise TypeError("canonicalized_stage_results_must_be_mapping")
    manifest = {
        **truth,
        "status": "applied",
        "removed_stale_alias_count": len(removed),
        "removed_stale_alias_paths": removed[:100],
        "pre_flatten_truth_enforced": True,
        "unknown_evidence_preserved_fail_closed": True,
        "large_artifacts_not_copied_or_scanned": True,
        "raw_stage_evidence_mutated": False,
        "report_design_changed": False,
        "scores_changed": False,
        "scanner_results_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return sanitized, manifest


def _attach_manifest(result: dict[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    manifest_copy = deepcopy(dict(manifest))
    output = dict(result)
    output["pre_render_scanner_truth"] = manifest_copy

    package = output.get("report_package")
    if isinstance(package, Mapping):
        package_copy = dict(package)
        package_copy["pre_render_scanner_truth"] = deepcopy(manifest_copy)
        canonical = package_copy.get("json")
        if isinstance(canonical, Mapping):
            canonical_copy = dict(canonical)
            canonical_copy["pre_render_scanner_truth"] = deepcopy(manifest_copy)
            package_copy["json"] = canonical_copy
        output["report_package"] = package_copy

    assessment = output.get("assessment")
    if isinstance(assessment, Mapping):
        assessment_copy = dict(assessment)
        assessment_copy["pre_render_scanner_truth"] = deepcopy(manifest_copy)
        output["assessment"] = assessment_copy
    return output


def install_pre_render_authoritative_scanner_truth() -> bool:
    """Patch the native report builder before any stage evidence is flattened."""

    from nico import comprehensive_report_package as report_module

    current = report_module.build_comprehensive_report_package
    if getattr(current, _INSTALL_MARKER, False):
        return False

    @wraps(current)
    def build(
        *,
        identity: dict[str, Any],
        stage_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        sanitized, manifest = canonicalize_stage_results_before_render(stage_results)
        result = current(identity=identity, stage_results=sanitized)
        return _attach_manifest(result, manifest)

    setattr(build, _INSTALL_MARKER, True)
    setattr(build, "_nico_original_builder", current)
    report_module.build_comprehensive_report_package = build

    # comprehensive_native_providers imports the builder by value. Patch an already
    # imported module; if it is imported later it will receive the patched symbol.
    native = sys.modules.get("nico.comprehensive_native_providers")
    if native is not None:
        setattr(native, "build_comprehensive_report_package", build)
    return True


__all__ = [
    "VERSION",
    "canonicalize_stage_results_before_render",
    "derive_authoritative_scanner_truth",
    "install_pre_render_authoritative_scanner_truth",
]
