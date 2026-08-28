from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping, Pattern

from nico import comprehensive_report_truth_stabilization_v52 as legacy_truth

VERSION = "nico.comprehensive_client_readiness.v59"
_MARKER = "_nico_comprehensive_client_readiness_v59"
_COMPLETED = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}
_COVERAGE_KEY_RE = re.compile(
    r"(?:analy[sz]er|scanner).*(?:coverage|completion)|"
    r"(?:coverage|completion).*(?:analy[sz]er|scanner)",
    re.I,
)
_COVERAGE_TEXT_RE = re.compile(
    r"(?P<label>(?:analy[sz]er|scanner)(?:\s+execution)?\s+"
    r"(?:coverage|completion)\s*)(?P<join>is\s+|[:=]\s*)"
    r"\d{1,3}(?P<pct>\s*%)?",
    re.I,
)
_COVERAGE_PREFIX_RE = re.compile(
    r"\b\d{1,3}(?P<pct>\s*%)"
    r"(?P<tail>\s+(?:accepted\s+)?(?:applicable[- ]?)?"
    r"(?:analy[sz]er|scanner)(?:\s+execution)?\s+"
    r"(?:coverage|completion))",
    re.I,
)
_KNOWN_IDENTIFIER_REPAIRS = {
    "appy_ l scanner_artifact_scoring": "apply_scanner_artifact_scoring",
    "appy_l scanner_artifact_scoring": "apply_scanner_artifact_scoring",
    " span ish_pdf": "_spanish_pdf",
    "span ish_pdf": "_spanish_pdf",
    "_ span ish_pdf": "_spanish_pdf",
    " span ish_markdown": "_spanish_markdown",
    "span ish_markdown": "_spanish_markdown",
    "_ span ish_markdown": "_spanish_markdown",
    "co llect_complexity_evidence": "collect_complexity_evidence",
    "co llect_snapshot_repository_evidence": "collect_snapshot_repository_evidence",
    "eva luate_report_payload": "evaluate_report_payload",
    "mar kdown_report": "markdown_report",
    "reso lve_repository_commit": "resolve_repository_commit",
    "install_comprehensive_on_production_ app": "install_comprehensive_on_production_app",
    "production_ app": "production_app",
}
_REGEX_CASEFOLD_TRANSLATION = str.maketrans(
    {
        "\u0131": "i",  # U+0131 matches ASCII i under re.IGNORECASE.
        "\u017f": "s",  # U+017F matches ASCII s under re.IGNORECASE.
        "\u0307": "",  # U+0130 casefolds to i + COMBINING DOT ABOVE.
    }
)
_WHITESPACE_RE = re.compile(r"\s+")
_KNOWN_IDENTIFIER_REPAIR_PLAN: tuple[tuple[str, Pattern[str], str], ...] = tuple(
    (
        broken.casefold().translate(_REGEX_CASEFOLD_TRANSLATION),
        re.compile(re.escape(broken), re.IGNORECASE),
        canonical,
    )
    for broken, canonical in _KNOWN_IDENTIFIER_REPAIRS.items()
)

# Each item retains the exact historical sequential substitution order. The folded
# literal is only a no-false-negative precheck; the compiled regular expression still
# owns matching and replacement semantics.
_SymbolRepairPlan = tuple[tuple[str, Pattern[str], str], ...]


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _tool(value: Any) -> str:
    if isinstance(value, Mapping):
        value = (
            value.get("scanner_name")
            or value.get("scanner")
            or value.get("tool")
            or value.get("analyzer")
            or value.get("name")
        )
    normalized = _text(value).casefold().replace("_", "-")
    aliases = {
        "npm audit": "npm-audit",
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "pip audit": "pip-audit",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }
    return aliases.get(normalized, normalized)


def _truthy(value: Any) -> bool:
    return value is True or _text(value).casefold() in {
        "1",
        "exact",
        "matched",
        "retained",
        "true",
        "verified",
        "yes",
    }


def _direct_scanner_records(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select the exact-run scanner population without walking stale projections."""

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    candidates = (
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
        canonical.get("live_scanner_evidence"),
        assessment.get("live_scanner_evidence"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            records = [deepcopy(dict(item)) for item in candidate if isinstance(item, Mapping)]
            if records:
                return records
        if isinstance(candidate, Mapping):
            nested = candidate.get("records") or candidate.get("scanners") or candidate.get("tools")
            if isinstance(nested, list):
                records = [deepcopy(dict(item)) for item in nested if isinstance(item, Mapping)]
                if records:
                    return records
            if isinstance(nested, Mapping):
                records = []
                for name, item in nested.items():
                    if not isinstance(item, Mapping):
                        continue
                    record = deepcopy(dict(item))
                    record.setdefault("scanner_name", name)
                    records.append(record)
                if records:
                    return records
    return []


def _scanner_state(record: Mapping[str, Any]) -> dict[str, Any] | None:
    name = _tool(record)
    if not name:
        return None
    status = _text(
        record.get("status") or record.get("state") or record.get("execution_status")
    ).casefold().replace("-", "_")
    exact = any(
        _truthy(record.get(key))
        for key in (
            "exact_commit_match",
            "exact_sha",
            "exact_commit",
            "snapshot_match",
            "commit_match",
        )
    )
    explicit_completed = record.get("completed")
    completed = (
        explicit_completed is True
        if isinstance(explicit_completed, bool)
        else status in _COMPLETED
    )
    verified_values = (
        record.get("verified"),
        record.get("verified_complete"),
        record.get("verified_for_this_report"),
    )
    verification_declared = any(value is not None for value in verified_values)
    verified = any(_truthy(value) for value in verified_values)
    completed = bool(completed and exact and (verified or not verification_declared))
    findings = record.get("findings")
    if isinstance(findings, list):
        finding_count = len(findings)
    else:
        try:
            finding_count = int(record.get("finding_count", record.get("findings_count", 0)) or 0)
        except (TypeError, ValueError):
            finding_count = 0
    canonical_status = (
        "completed_with_findings"
        if completed and finding_count > 0
        else "completed"
        if completed
        else status or "failed"
    )
    reason = _text(
        record.get("failure_reason")
        or record.get("failure_or_unavailable_reason")
        or record.get("reason")
    )
    return {
        "scanner_name": name,
        "status": canonical_status,
        "completed": completed,
        "verified": bool(completed and (verified or not verification_declared)),
        "exact_commit_match": exact,
        "artifact_retained": bool(
            record.get("artifact_retained")
            or record.get("artifact_hash")
            or record.get("raw_artifact")
            or record.get("raw_artifact_sha256")
        ),
        "finding_count": finding_count,
        "failure_reason": "" if completed else reason,
    }


def _authoritative_scanner_truth(
    canonical: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    for record in _direct_scanner_records(canonical):
        state = _scanner_state(record)
        if state is not None:
            truth[state["scanner_name"]] = state
    return truth


def _requested_analyzer_count(node: Any) -> int:
    candidates: list[int] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            normalized = str(key).casefold()
            if normalized in {
                "requested_analyzers",
                "applicable_analyzers",
                "requested_scanners",
                "applicable_scanners",
                "applicable_analyzer_count",
                "requested_analyzer_count",
                "applicable_scanner_count",
                "requested_scanner_count",
            }:
                if isinstance(value, int) and not isinstance(value, bool):
                    candidates.append(value)
                elif isinstance(value, list):
                    candidates.append(len(value))
            candidates.append(_requested_analyzer_count(value))
    elif isinstance(node, list):
        for value in node:
            candidates.append(_requested_analyzer_count(value))
    return max(candidates, default=0)


def _maturity_label(score: Any) -> str:
    try:
        value = int(round(float(score)))
    except (TypeError, ValueError):
        return "Not scored"
    if value >= 90:
        return "Exceptional"
    if value >= 80:
        return "Strong"
    if value >= 70:
        return "Moderate"
    if value >= 60:
        return "Developing"
    return "High risk"


def _symbols(node: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(node, Mapping):
        for key in ("symbol", "function", "component", "function_name"):
            value = node.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,}", value):
                output.add(value)
        for value in node.values():
            output.update(_symbols(value))
    elif isinstance(node, list):
        for value in node:
            output.update(_symbols(value))
    return output


def _regex_casefold(value: str) -> str:
    """Match Python's ASCII-letter ``re.IGNORECASE`` equivalence for probes."""

    return str(value or "").casefold().translate(_REGEX_CASEFOLD_TRANSLATION)


def _compile_symbol_repair_plan(symbols: set[str]) -> _SymbolRepairPlan:
    """Compile the existing flexible-identifier regexes once per tree traversal."""

    return tuple(
        (
            _regex_casefold(symbol),
            re.compile(
                r"(?<![A-Za-z0-9_])"
                + r"\s*".join(map(re.escape, symbol))
                + r"(?![A-Za-z0-9_])",
                re.IGNORECASE,
            ),
            symbol,
        )
        for symbol in sorted(symbols, key=len, reverse=True)
    )


def _repair_symbols(
    text: str,
    symbols: set[str],
    coverage: int,
    *,
    symbol_repair_plan: _SymbolRepairPlan | None = None,
) -> str:
    has_whitespace = _WHITESPACE_RE.search(text) is not None
    repaired = (
        legacy_truth._repair_text(text)
        if has_whitespace and hasattr(legacy_truth, "_repair_text")
        else text
    )
    if has_whitespace:
        known_probe = _regex_casefold(repaired)
        for broken_probe, pattern, canonical in _KNOWN_IDENTIFIER_REPAIR_PLAN:
            if broken_probe in known_probe:
                updated = pattern.sub(canonical, repaired)
                if updated != repaired:
                    repaired = updated
                    # Preserve the historical sequential/cascading replacement
                    # contract.
                    known_probe = _regex_casefold(repaired)

    plan = (
        symbol_repair_plan
        if symbol_repair_plan is not None
        else _compile_symbol_repair_plan(symbols)
    )
    # A flexible symbol match can differ from its canonical literal only by whitespace
    # and re.IGNORECASE equivalence. Removing whitespace therefore gives a necessary
    # (not sufficient) match condition and safely avoids nearly all regex scans in raw
    # candidate payloads. The compiled expression remains authoritative when the probe
    # succeeds, preserving boundaries, overlap behavior, casing, and replacement order.
    symbol_probe = _regex_casefold(_WHITESPACE_RE.sub("", repaired))
    for canonical_probe, pattern, canonical in plan:
        if canonical_probe in symbol_probe:
            repaired = pattern.sub(canonical, repaired)
    repaired = re.sub(r"\bS\s+p\s+ecific correction\b", "Specific correction", repaired)
    repaired = _COVERAGE_TEXT_RE.sub(
        lambda match: (
            f"{match.group('label')}{match.group('join')}{coverage}"
            f"{match.group('pct') or ''}"
        ),
        repaired,
    )
    repaired = _COVERAGE_PREFIX_RE.sub(
        lambda match: f"{coverage}{match.group('pct')}{match.group('tail')}",
        repaired,
    )
    return repaired


def _filter_scanner_entries(
    values: list[Any],
    *,
    allowed: set[str],
) -> list[Any]:
    output: list[Any] = []
    for value in values:
        name = _tool(value)
        if not name or name in allowed:
            output.append(value)
    return output


def _synchronize_scanner_row(
    output: dict[str, Any],
    truth: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    name = _tool(output)
    if not name or name not in truth:
        return output
    state = truth[name]
    for key in ("status", "state", "execution_status"):
        if key in output:
            output[key] = state["status"]
    for key in ("completed", "execution_complete"):
        if key in output:
            output[key] = state["completed"]
    for key in ("verified", "verified_complete", "verified_for_this_report"):
        if key in output:
            output[key] = state["verified"]
    if "exact_commit_match" in output:
        output["exact_commit_match"] = state["exact_commit_match"]
    if state["completed"]:
        for key in (
            "failure_reason",
            "failure_or_unavailable_reason",
            "reason",
        ):
            if key in output:
                output[key] = ""
    elif state["failure_reason"]:
        for key in ("failure_reason", "failure_or_unavailable_reason", "reason"):
            if key in output:
                output[key] = state["failure_reason"]
    return output


def _normalize_tree(
    node: Any,
    *,
    truth: Mapping[str, Mapping[str, Any]],
    completed: set[str],
    incomplete: set[str],
    requested: int,
    symbols: set[str],
    technical_score: int | None,
    symbol_repair_plan: _SymbolRepairPlan | None = None,
) -> Any:
    if symbol_repair_plan is None:
        symbol_repair_plan = _compile_symbol_repair_plan(symbols)
    coverage = round(100 * len(completed) / requested) if requested else 0
    if isinstance(node, list):
        return [
            _normalize_tree(
                value,
                truth=truth,
                completed=completed,
                incomplete=incomplete,
                requested=requested,
                symbols=symbols,
                technical_score=technical_score,
                symbol_repair_plan=symbol_repair_plan,
            )
            for value in node
        ]
    if isinstance(node, str):
        return _repair_symbols(
            node,
            symbols,
            coverage,
            symbol_repair_plan=symbol_repair_plan,
        )
    if not isinstance(node, Mapping):
        return node

    output = {
        key: _normalize_tree(
            value,
            truth=truth,
            completed=completed,
            incomplete=incomplete,
            requested=requested,
            symbols=symbols,
            technical_score=technical_score,
            symbol_repair_plan=symbol_repair_plan,
        )
        for key, value in node.items()
    }
    output = _synchronize_scanner_row(output, truth)

    for field in (
        "incomplete_analyzers",
        "incomplete_scanners",
        "failed_analyzers",
        "failed_scanners",
        "analyzer_evidence_blockers",
        "scanner_evidence_blockers",
    ):
        value = output.get(field)
        if isinstance(value, list):
            output[field] = _filter_scanner_entries(value, allowed=incomplete)

    if requested > 0:
        for key in list(output):
            value = output.get(key)
            if (
                _COVERAGE_KEY_RE.search(str(key))
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                output[key] = coverage
        if "completed_applicable_analyzers" in output:
            output["completed_applicable_analyzers"] = len(completed)
        if "completed_applicable_scanners" in output:
            output["completed_applicable_scanners"] = len(completed)
        if "incomplete_applicable_analyzers" in output:
            output["incomplete_applicable_analyzers"] = max(0, requested - len(completed))
        if "incomplete_applicable_scanners" in output:
            output["incomplete_applicable_scanners"] = max(0, requested - len(completed))

    if technical_score is not None:
        label = _maturity_label(technical_score)
        for key in ("maturity", "maturity_level", "maturity_label"):
            if key in output and isinstance(output.get(key), str):
                output[key] = label

    status = _text(output.get("status")).casefold()
    human_status = _text(output.get("human_evidence_status")).casefold()
    if status in {"complete", "completed"} and human_status in {
        "not_assessed",
        "missing",
        "unavailable",
    }:
        output["execution_status"] = "complete"
        output["evidence_status"] = "limited"
        output["requires_human_review"] = True

    return output


def reconcile_client_readiness(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(canonical))
    truth = _authoritative_scanner_truth(output)
    completed = {name for name, state in truth.items() if state["completed"]}
    known_incomplete = {name for name, state in truth.items() if not state["completed"]}
    requested = max(_requested_analyzer_count(output), len(truth))

    assessment = output.get("assessment") if isinstance(output.get("assessment"), Mapping) else {}
    technical = assessment.get("technical_score") or output.get("technical_score")
    try:
        technical_score = int(round(float(technical)))
    except (TypeError, ValueError):
        technical_score = None

    symbols = _symbols(output)
    output = _normalize_tree(
        output,
        truth=truth,
        completed=completed,
        incomplete=known_incomplete,
        requested=requested,
        symbols=symbols,
        technical_score=technical_score,
    )

    coverage = round(100 * len(completed) / requested) if requested else 0
    output["analyzer_execution_coverage"] = coverage
    output["scanner_execution_coverage"] = coverage
    output["completed_applicable_analyzers"] = len(completed)
    output["incomplete_applicable_analyzers"] = max(0, requested - len(completed))
    output["client_readiness_contract"] = {
        "version": VERSION,
        "scanner_execution_completion": coverage,
        "analyzer_execution_coverage": coverage,
        "coverage_numerator": len(completed),
        "coverage_denominator": requested,
        "authoritative_scanner_record_count": len(truth),
        "completed_exact_commit_scanners": sorted(completed),
        "incomplete_analyzers": sorted(known_incomplete),
        "scanner_states": {
            name: {
                "status": state["status"],
                "completed": state["completed"],
                "verified": state["verified"],
                "finding_count": state["finding_count"],
                "failure_reason": state["failure_reason"],
            }
            for name, state in sorted(truth.items())
        },
        "maturity_label": _maturity_label(technical_score),
        "technical_maturity_is_not_operational_readiness": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "approval_required_for_client_delivery": True,
        "cross_format_truth_required": True,
        "identifier_integrity_required": True,
        "duplicate_detailed_finding_sections_allowed": False,
    }
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def install_comprehensive_client_readiness_v59() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current: Callable[[dict[str, Any]], dict[str, Any]] = completion._install_register
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def install_register(canonical: dict[str, Any]) -> dict[str, Any]:
        registered = current(canonical)
        return reconcile_client_readiness(registered)

    setattr(install_register, _MARKER, True)
    setattr(install_register, "_nico_previous", current)
    completion._install_register = install_register
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion._install_register is install_register,
        "scanner_state_canonicalized": True,
        "authoritative_scanner_records_only": True,
        "coverage_denominator_explicit": True,
        "all_coverage_aliases_synchronized": True,
        "maturity_terminology_unified": True,
        "identifier_integrity_repaired_before_render": True,
        "limited_evidence_status_separated_from_execution_status": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_readiness_v59",
    "reconcile_client_readiness",
]
