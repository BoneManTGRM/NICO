from __future__ import annotations

import re
import sys
import time
from functools import wraps
from typing import Any, Mapping

from nico import comprehensive_client_readiness_v59 as v59

VERSION = "nico.comprehensive_pre_render_scanner_truth.v65"
_INSTALL_MARKER = "_nico_pre_render_scanner_truth_v65"
_MANIFEST_KEY = "pre_render_scanner_truth"
_DROP = object()

_STRICT_INCOMPLETE_LIST_FIELDS = frozenset(
    {"incomplete_analyzers", "incomplete_scanners", "failed_analyzers", "failed_scanners"}
)
_BLOCKER_LIST_FIELDS = frozenset(
    {"analyzer_evidence_blockers", "scanner_evidence_blockers"}
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
_HEAVY_FIELDS = frozenset(
    {
        "pdf_base64",
        "html",
        "markdown",
        "report_package",
        "reports",
        "raw_output",
        "stdout",
        "stderr",
        "file_contents",
        "source_contents",
        "scanner_results",
    }
)
_RELEVANT_STAGE_IDS = frozenset(
    {
        "dependency_security_static_analysis",
        "evidence_reconciliation_and_scoring",
        "decision_report_generation",
        "deep_scanner_triage",
        "risk_reduction_and_executive_briefing",
    }
)
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
_MAX_DISCOVERY_VISITS = 12_000
_MAX_SANITIZE_VISITS = 40_000
_MAX_GENERIC_LIST_SCAN = 1_000


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


def _existing_manifest(stage_results: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = stage_results.get(_MANIFEST_KEY)
    if isinstance(direct, Mapping) and direct.get("pre_flatten_truth_enforced") is True:
        return direct
    for stage_id in (
        "evidence_reconciliation_and_scoring",
        "dependency_security_static_analysis",
    ):
        stage = _mapping(stage_results.get(stage_id))
        evidence = _mapping(stage.get("evidence"))
        manifest = evidence.get(_MANIFEST_KEY)
        if isinstance(manifest, Mapping) and manifest.get("pre_flatten_truth_enforced") is True:
            return manifest
    return {}


def _relevant_roots(stage_results: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    roots: list[Mapping[str, Any]] = []
    for stage_id in _RELEVANT_STAGE_IDS:
        stage = stage_results.get(stage_id)
        if isinstance(stage, Mapping):
            roots.append(stage)
    return roots


def _discover_mappings(
    roots: list[Mapping[str, Any]],
    key_name: str,
) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    stack: list[Any] = list(reversed(roots))
    visits = 0
    while stack and visits < _MAX_DISCOVERY_VISITS:
        node = stack.pop()
        visits += 1
        if isinstance(node, Mapping):
            for raw_key, value in node.items():
                key = str(raw_key)
                if key == key_name and isinstance(value, Mapping):
                    output.append(value)
                if key.casefold() in _HEAVY_FIELDS:
                    continue
                if isinstance(value, Mapping):
                    stack.append(value)
                elif isinstance(value, list) and len(value) <= 250:
                    stack.extend(reversed(value))
        elif isinstance(node, list) and len(node) <= 250:
            stack.extend(reversed(node))
    return output


def _direct_contract_candidates(
    stage_results: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    for stage_id in (
        "evidence_reconciliation_and_scoring",
        "decision_report_generation",
    ):
        stage = _mapping(stage_results.get(stage_id))
        for container in (
            stage,
            _mapping(stage.get("assessment")),
            _mapping(stage.get("evidence")),
        ):
            value = container.get("client_readiness_contract")
            if isinstance(value, Mapping):
                candidates.append(value)
    return candidates


def _best_contract(stage_results: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = _direct_contract_candidates(stage_results)
    if not candidates:
        candidates = _discover_mappings(
            _relevant_roots(stage_results),
            "client_readiness_contract",
        )
    if not candidates:
        return {}

    def quality(contract: Mapping[str, Any]) -> tuple[int, int, int]:
        return (
            1 if _text(contract.get("authoritative_source")) else 0,
            _safe_int(contract.get("coverage_denominator")),
            len(_names(contract.get("requested_exact_run_scanners"))),
        )

    return max(candidates, key=quality)


def _live_manifest(stage_results: Mapping[str, Any]) -> Mapping[str, Any]:
    dependency = _mapping(stage_results.get("dependency_security_static_analysis"))
    for candidate in (
        dependency.get("scanner"),
        _mapping(dependency.get("evidence")).get("scanner"),
        _mapping(stage_results.get("deep_scanner_triage")).get("scanner_triage"),
    ):
        if isinstance(candidate, Mapping) and any(
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
    for key in ("live_scanner_evidence", "scanner_run_summary", "scanner"):
        candidates = _discover_mappings(_relevant_roots(stage_results), key)
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


def _scanner_records(stage_results: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[list[Mapping[str, Any]]] = []
    for root in _relevant_roots(stage_results):
        direct = root.get("scanner_execution_records")
        if isinstance(direct, list):
            records = [item for item in direct if isinstance(item, Mapping)]
            if records:
                candidates.append(records)
    if not candidates:
        stack: list[Any] = _relevant_roots(stage_results)
        visits = 0
        while stack and visits < _MAX_DISCOVERY_VISITS:
            node = stack.pop()
            visits += 1
            if not isinstance(node, Mapping):
                continue
            for raw_key, value in node.items():
                key = str(raw_key)
                if key == "scanner_execution_records" and isinstance(value, list):
                    records = [item for item in value if isinstance(item, Mapping)]
                    if records:
                        candidates.append(records)
                if key.casefold() in _HEAVY_FIELDS:
                    continue
                if isinstance(value, Mapping):
                    stack.append(value)
                elif isinstance(value, list) and len(value) <= 250:
                    stack.extend(item for item in value if isinstance(item, Mapping))
    return max(candidates, key=len) if candidates else []


def derive_authoritative_scanner_truth(
    stage_results: Mapping[str, Any],
) -> dict[str, Any]:
    requested: set[str] = set()
    completed: set[str] = set()
    hard_incomplete: set[str] = set()
    soft_incomplete: set[str] = set()
    sources: list[str] = []

    records = _scanner_records(stage_results)
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
    visits: list[int],
    path: str,
    key_hint: str = "",
    depth: int = 0,
) -> tuple[Any, bool]:
    visits[0] += 1
    if visits[0] > _MAX_SANITIZE_VISITS or depth > 10:
        return node, False
    if isinstance(node, str):
        sanitized = _sanitize_text(
            node,
            requested=requested,
            incomplete=incomplete,
            removed=removed,
            path=path,
        )
        return sanitized, sanitized is not node
    if isinstance(node, list):
        if len(node) > _MAX_GENERIC_LIST_SCAN and key_hint not in (
            _STRICT_INCOMPLETE_LIST_FIELDS | _BLOCKER_LIST_FIELDS
        ):
            return node, False
        output: list[Any] | None = None
        for index, item in enumerate(node):
            sanitized, changed = _sanitize_node(
                item,
                requested=requested,
                completed=completed,
                incomplete=incomplete,
                coverage=coverage,
                removed=removed,
                visits=visits,
                path=f"{path}[{index}]",
                key_hint=key_hint,
                depth=depth + 1,
            )
            if changed and output is None:
                output = list(node[:index])
            if output is not None and sanitized is not _DROP:
                output.append(sanitized)
        return (output if output is not None else node), output is not None
    if not isinstance(node, Mapping):
        return node, False

    output: dict[str, Any] | None = None
    items = list(node.items())
    for index, (raw_key, raw_value) in enumerate(items):
        key = str(raw_key)
        normalized = key.casefold()
        current_path = f"{path}.{key}"
        replacement: Any = raw_value
        changed = False

        if normalized in _HEAVY_FIELDS:
            pass
        elif (
            normalized in _STRICT_INCOMPLETE_LIST_FIELDS
            and isinstance(raw_value, list)
            and requested
        ):
            retained: list[Any] = []
            for item_index, item in enumerate(raw_value):
                name = _entry_tool(item, requested)
                if name and name not in incomplete:
                    removed.append(f"{current_path}[{item_index}]")
                    changed = True
                    continue
                retained.append(item)
            replacement = retained if changed else raw_value
        elif normalized in _BLOCKER_LIST_FIELDS and isinstance(raw_value, list) and requested:
            retained = []
            for item_index, item in enumerate(raw_value):
                name = _entry_tool(item, requested)
                if name and name not in incomplete:
                    removed.append(f"{current_path}[{item_index}]")
                    changed = True
                    continue
                retained.append(item)
            replacement = retained if changed else raw_value
        elif normalized in _INCOMPLETE_COUNT_FIELDS and requested:
            replacement = len(incomplete)
            changed = replacement != raw_value
        elif normalized in _COMPLETED_COUNT_FIELDS and requested:
            replacement = len(completed)
            changed = replacement != raw_value
        elif (
            requested
            and _COVERAGE_KEY_RE.search(key)
            and isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
        ):
            replacement = coverage
            changed = replacement != raw_value
        else:
            replacement, changed = _sanitize_node(
                raw_value,
                requested=requested,
                completed=completed,
                incomplete=incomplete,
                coverage=coverage,
                removed=removed,
                visits=visits,
                path=current_path,
                key_hint=normalized,
                depth=depth + 1,
            )

        if changed and output is None:
            output = {str(k): v for k, v in items[:index]}
        if output is not None and replacement is not _DROP:
            output[key] = replacement
    return (output if output is not None else node), output is not None


def _embed_manifest(
    stage_results: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(stage_results)
    stage_id = (
        "evidence_reconciliation_and_scoring"
        if isinstance(stage_results.get("evidence_reconciliation_and_scoring"), Mapping)
        else "dependency_security_static_analysis"
    )
    stage = _mapping(stage_results.get(stage_id))
    stage_copy = dict(stage)
    evidence = _mapping(stage.get("evidence"))
    evidence_copy = dict(evidence)
    evidence_copy[_MANIFEST_KEY] = dict(manifest)
    stage_copy["evidence"] = evidence_copy
    output[stage_id] = stage_copy
    return output


def canonicalize_stage_results_before_render(
    stage_results: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    existing = _existing_manifest(stage_results)
    if existing:
        manifest = dict(existing)
        manifest.update(
            {
                "status": "already_applied",
                "duplicate_canonicalization_skipped": True,
                "canonicalization_elapsed_ms": round(
                    (time.perf_counter() - started) * 1000,
                    3,
                ),
            }
        )
        return dict(stage_results), manifest

    truth = derive_authoritative_scanner_truth(stage_results)
    if truth["truth_available"] is not True:
        return dict(stage_results), {
            **truth,
            "status": "not_applied_no_authoritative_scanner_population",
            "removed_stale_alias_count": 0,
            "removed_stale_alias_paths": [],
            "canonicalization_elapsed_ms": round(
                (time.perf_counter() - started) * 1000,
                3,
            ),
        }

    requested = set(truth["requested"])
    completed = set(truth["completed"])
    incomplete = set(truth["incomplete"])
    removed: list[str] = []
    visits = [0]
    output = dict(stage_results)
    changed_stages = 0
    for stage_id, stage in stage_results.items():
        if stage_id not in _RELEVANT_STAGE_IDS or not isinstance(stage, Mapping):
            continue
        sanitized, changed = _sanitize_node(
            stage,
            requested=requested,
            completed=completed,
            incomplete=incomplete,
            coverage=int(truth["coverage"]),
            removed=removed,
            visits=visits,
            path=f"stage_results.{stage_id}",
            key_hint=stage_id,
        )
        if changed:
            output[stage_id] = sanitized
            changed_stages += 1

    manifest = {
        **truth,
        "status": "applied",
        "removed_stale_alias_count": len(removed),
        "removed_stale_alias_paths": removed[:100],
        "pre_flatten_truth_enforced": True,
        "duplicate_canonicalization_skipped": False,
        "copy_on_write": True,
        "changed_stage_count": changed_stages,
        "nodes_visited": visits[0],
        "traversal_bounded": visits[0] <= _MAX_SANITIZE_VISITS,
        "canonicalization_elapsed_ms": round(
            (time.perf_counter() - started) * 1000,
            3,
        ),
        "unknown_evidence_preserved_fail_closed": True,
        "large_artifacts_not_copied_or_scanned": True,
        "raw_stage_evidence_mutated": False,
        "report_design_changed": False,
        "scores_changed": False,
        "scanner_results_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return _embed_manifest(output, manifest), manifest


def _attach_manifest(
    result: dict[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_copy = dict(manifest)
    output = dict(result)
    output[_MANIFEST_KEY] = manifest_copy
    package = output.get("report_package")
    if isinstance(package, Mapping):
        package_copy = dict(package)
        package_copy[_MANIFEST_KEY] = dict(manifest_copy)
        canonical = package_copy.get("json")
        if isinstance(canonical, Mapping):
            canonical_copy = dict(canonical)
            canonical_copy[_MANIFEST_KEY] = dict(manifest_copy)
            package_copy["json"] = canonical_copy
        output["report_package"] = package_copy
    assessment = output.get("assessment")
    if isinstance(assessment, Mapping):
        assessment_copy = dict(assessment)
        assessment_copy[_MANIFEST_KEY] = dict(manifest_copy)
        output["assessment"] = assessment_copy
    return output


def install_pre_render_authoritative_scanner_truth() -> bool:
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
