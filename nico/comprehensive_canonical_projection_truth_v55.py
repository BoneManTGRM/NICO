from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable, Mapping

VERSION = "nico.comprehensive_canonical_projection_truth.v57"
_NORMALIZER_MARKER = "_nico_comprehensive_canonical_projection_truth_v55"
_VALIDATOR_MARKER = "_nico_comprehensive_final_artifact_projection_truth_v55"

_COUNT_KEYS = {
    "unique_finding_count",
    "decision_finding_count",
    "finding_register_count",
    "canonical_finding_count",
}
_EXACT_COUNT_KEYS = {
    "exact_source_code_finding_count",
    "exact_source_finding_count",
}
_OPERATIONAL_COUNT_KEYS = {
    "operational_or_context_finding_count",
    "operational_finding_count",
}
_FINDING_SURFACES = (
    "canonical_findings",
    "findings_register",
    "findings",
    "decision_grade_findings_register",
)
_SYNC_SURFACES = (
    "executive_findings",
    "finding_cards",
    "roadmap",
    "backlog",
    "work_packages",
    "remediation_plan",
    "recommendations",
    "assessment",
    "stage_summaries",
)
_COMPLETED_STATES = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}
_SOURCE_RE = re.compile(
    r"([A-Za-z0-9_.\-/]+\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|java|kt|swift|go|rs|rb|php|cs|c|cc|cpp|h|hpp|sh|yml|yaml|toml|json))",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "osv scanner": "osv-scanner",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }.get(normalized, normalized)


def _authoritative_scanner_applicability(
    canonical: Mapping[str, Any],
) -> tuple[set[str], set[str]] | None:
    """Read the bounded exact-run applicability contract when it is self-consistent.

    Late client-safe projections may retain the complete requested scanner record list
    while dropping per-record applicability flags. The authoritative exact-run contract
    remains the denominator source in that shape. Any incomplete or contradictory
    contract is ignored so unknown scanners continue to fail closed as applicable.
    """

    contract = canonical.get("client_readiness_contract")
    if not isinstance(contract, Mapping):
        return None
    if (
        contract.get(
            "technology_inapplicable_scanners_excluded_from_coverage_denominator"
        )
        is not True
        or contract.get("not_applicable_scanners_receive_completion_credit")
        is not False
    ):
        return None

    requested_values = contract.get("requested_exact_run_scanners")
    applicable_values = contract.get("applicable_exact_run_scanners")
    not_applicable_values = contract.get("not_applicable_exact_run_scanners")
    if not all(
        isinstance(values, list)
        for values in (
            requested_values,
            applicable_values,
            not_applicable_values,
        )
    ):
        return None

    requested = {_scanner_name(value) for value in requested_values}
    applicable = {_scanner_name(value) for value in applicable_values}
    not_applicable = {
        _scanner_name(value) for value in not_applicable_values
    }
    if (
        "" in requested
        or "" in applicable
        or "" in not_applicable
        or not requested
        or applicable.intersection(not_applicable)
        or requested != applicable.union(not_applicable)
        or len(requested) != len(requested_values)
        or len(applicable) != len(applicable_values)
        or len(not_applicable) != len(not_applicable_values)
    ):
        return None

    expected_counts = (
        ("authoritative_scanner_record_count", len(requested)),
        ("applicable_scanner_record_count", len(applicable)),
        ("not_applicable_scanner_record_count", len(not_applicable)),
        ("coverage_denominator", len(applicable)),
    )
    for key, expected in expected_counts:
        value = contract.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value != expected
        ):
            return None
    return requested, applicable


def _scanner_population(
    canonical: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    source = canonical.get("scanner_execution_records")
    if not isinstance(source, list):
        source = assessment.get("scanner_execution_records")
    records = [
        deepcopy(dict(item))
        for item in source or []
        if isinstance(item, Mapping)
    ]
    authoritative_applicability = _authoritative_scanner_applicability(canonical)

    not_applicable_names: set[str] = set()
    for container in (canonical, assessment):
        excluded = container.get("not_applicable_scanner_records")
        if not isinstance(excluded, list):
            continue
        for item in excluded:
            if not isinstance(item, Mapping):
                continue
            name = _scanner_name(
                item.get("scanner_name") or item.get("scanner") or item.get("tool")
            )
            if name:
                not_applicable_names.add(name)

    by_name: dict[str, dict[str, Any]] = {}
    for item in records:
        name = _scanner_name(
            item.get("scanner_name") or item.get("scanner") or item.get("tool")
        )
        if not name:
            continue
        item["scanner_name"] = name
        status = _text(item.get("status") or item.get("state")).casefold().replace(
            "-", "_"
        )
        item["status"] = status
        completed = item.get("completed") is True or status in _COMPLETED_STATES
        exact = item.get("exact_commit_match") is not False
        artifact = bool(
            item.get("artifact_hash")
            or item.get("raw_artifact_sha256")
            or item.get("artifact_sha256")
            or item.get("sha256")
        )
        item["completed"] = bool(completed and exact and artifact)
        by_name[name] = item

    ordered = [by_name[name] for name in sorted(by_name)]
    applicable = [
        item
        for item in ordered
        if item.get("applicable") is not False
        and _text(item.get("status")).casefold().replace("-", "_")
        not in {"not_applicable", "not_required", "inapplicable"}
        and _scanner_name(item.get("scanner_name")) not in not_applicable_names
        and (
            authoritative_applicability is None
            or _scanner_name(item.get("scanner_name"))
            not in authoritative_applicability[0]
            or _scanner_name(item.get("scanner_name"))
            in authoritative_applicability[1]
        )
    ]
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]
    coverage = round(100 * len(completed) / len(applicable)) if applicable else 0
    return ordered, completed, incomplete, coverage


def _sync_scanner_projection(
    value: Any,
    *,
    records: list[dict[str, Any]],
    completed: list[dict[str, Any]],
    incomplete: list[dict[str, Any]],
    coverage: int,
) -> Any:
    if isinstance(value, list):
        return [
            _sync_scanner_projection(
                item,
                records=records,
                completed=completed,
                incomplete=incomplete,
                coverage=coverage,
            )
            for item in value
        ]
    if not isinstance(value, Mapping):
        return value

    original = dict(value)
    output = {
        key: _sync_scanner_projection(
            child,
            records=records,
            completed=completed,
            incomplete=incomplete,
            coverage=coverage,
        )
        for key, child in original.items()
    }
    completed_names = [
        _scanner_name(item.get("scanner_name")) for item in completed
    ]
    incomplete_names = [
        _scanner_name(item.get("scanner_name")) for item in incomplete
    ]

    if "incomplete_analyzers" in output:
        prior = original.get("incomplete_analyzers")
        output["incomplete_analyzers"] = (
            deepcopy(incomplete)
            if isinstance(prior, list)
            and any(isinstance(item, Mapping) for item in prior)
            else incomplete_names
        )
    if "analyzer_execution_coverage" in output:
        output["analyzer_execution_coverage"] = coverage
    if "completed_scanner_count" in output:
        output["completed_scanner_count"] = len(completed)
    if "incomplete_scanner_count" in output:
        output["incomplete_scanner_count"] = len(incomplete)
    if "completed_scanners" in output and isinstance(
        original.get("completed_scanners"), list
    ):
        output["completed_scanners"] = completed_names
    if "incomplete_scanners" in output and isinstance(
        original.get("incomplete_scanners"), list
    ):
        output["incomplete_scanners"] = incomplete_names
    if "scanner_execution_records" in output:
        output["scanner_execution_records"] = deepcopy(records)
    if "completed_scanner_records" in output:
        output["completed_scanner_records"] = deepcopy(completed)
    if "incomplete_scanner_records" in output:
        output["incomplete_scanner_records"] = deepcopy(incomplete)
    return output


def _source_path(value: Any) -> str:
    match = _SOURCE_RE.search(_text(value).replace("\\", "/"))
    return match.group(1).casefold() if match else ""


def _symbol(item: Mapping[str, Any]) -> str:
    for key in ("symbol", "function", "function_name", "component", "name"):
        value = _text(item.get(key)).casefold()
        if value:
            return value
    title = _text(
        item.get("title") or item.get("decision_title") or item.get("summary")
    )
    match = re.search(r"reduce\s+complexity\s+in\s+([^·\n]+)", title, re.I)
    return _text(match.group(1).strip(" `.:")).casefold() if match else ""


def _rule_family(item: Mapping[str, Any]) -> str:
    for key in (
        "finding_family",
        "rule_id",
        "rule",
        "finding_type",
        "analyzer_rule",
        "category",
    ):
        value = _text(item.get(key)).casefold()
        if value:
            return value
    title = _text(item.get("title") or item.get("summary")).casefold()
    return "complexity_hotspot" if "reduce complexity in" in title else ""


def _source_identity(item: Mapping[str, Any]) -> tuple[str, str, str] | None:
    path = ""
    for key in ("path", "file", "source_path", "exact_source", "location"):
        path = _source_path(item.get(key))
        if path:
            break
    symbol = _symbol(item)
    family = _rule_family(item)
    return (path, symbol, family) if path and symbol and family else None


def _fallback_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    identifier = _text(item.get("finding_id") or item.get("id")).casefold()
    if identifier:
        return ("id", identifier)
    return (
        "semantic",
        _text(item.get("category")).casefold(),
        _text(item.get("location")).casefold().replace(" ", ""),
        _symbol(item),
        _rule_family(item),
        _text(item.get("title") or item.get("decision_title")).casefold(),
    )


def finding_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    source = _source_identity(item)
    return ("source", *source) if source else _fallback_identity(item)


def _quality(item: Mapping[str, Any]) -> tuple[int, int, str]:
    populated = sum(
        item.get(key) not in (None, "", [], {})
        for key in (
            "business_impact",
            "impact",
            "recommendation",
            "owner_role",
            "effort",
            "cost_of_inaction",
            "residual_risk",
            "acceptance_criteria",
            "supporting_evidence",
        )
    )
    return (
        populated,
        len(str(dict(item))),
        _text(item.get("finding_id") or item.get("id")),
    )


def _merge_findings(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any]:
    preferred, other = (
        (right, left) if _quality(right) > _quality(left) else (left, right)
    )
    merged = deepcopy(dict(preferred))
    for key, value in other.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = deepcopy(value)
    aliases = [
        *list(preferred.get("finding_aliases") or []),
        preferred.get("finding_id") or preferred.get("id"),
        *list(other.get("finding_aliases") or []),
        other.get("finding_id") or other.get("id"),
    ]
    merged["finding_aliases"] = list(
        dict.fromkeys(_text(value) for value in aliases if _text(value))
    )
    canonical_id = _text(preferred.get("finding_id") or preferred.get("id"))
    if canonical_id:
        merged["finding_id"] = canonical_id
        merged["id"] = canonical_id
    return merged


def canonicalize_final_findings(
    values: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for raw in values:
        item = deepcopy(dict(raw))
        key = finding_identity(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
        else:
            selected[key] = _merge_findings(selected[key], item)
    return [selected[key] for key in order]


def _sync_finding_reference(
    value: Any, by_alias: Mapping[str, Mapping[str, Any]]
) -> Any:
    if isinstance(value, list):
        return [_sync_finding_reference(item, by_alias) for item in value]
    if not isinstance(value, Mapping):
        return value
    original = dict(value)
    output = {
        key: _sync_finding_reference(child, by_alias)
        for key, child in original.items()
    }
    identifier = _text(original.get("finding_id") or original.get("id"))
    canonical = by_alias.get(identifier)
    if canonical:
        for key in (
            "finding_id",
            "id",
            "title",
            "decision_title",
            "category",
            "priority",
            "severity",
            "status",
            "location",
            "fact",
            "evidence",
            "interpretation",
            "business_impact",
            "impact",
            "recommendation",
            "owner_role",
            "effort",
            "cost_of_inaction",
            "residual_risk",
            "acceptance_criteria",
            "finding_aliases",
            "supporting_evidence",
        ):
            if key in canonical:
                output[key] = deepcopy(canonical[key])
    return output


def _sync_counts(value: Any, *, total: int, exact: int, operational: int) -> Any:
    if isinstance(value, list):
        return [
            _sync_counts(item, total=total, exact=exact, operational=operational)
            for item in value
        ]
    if not isinstance(value, Mapping):
        return value
    output = {
        key: _sync_counts(child, total=total, exact=exact, operational=operational)
        for key, child in value.items()
    }
    for key in list(output):
        if key in _COUNT_KEYS:
            output[key] = total
        elif key in _EXACT_COUNT_KEYS:
            output[key] = exact
        elif key in _OPERATIONAL_COUNT_KEYS:
            output[key] = operational
    return output


def normalize_final_projection(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(canonical))
    records, completed, incomplete, coverage = _scanner_population(output)
    output = _sync_scanner_projection(
        output,
        records=records,
        completed=completed,
        incomplete=incomplete,
        coverage=coverage,
    )
    output["scanner_execution_records"] = deepcopy(records)
    assessment = deepcopy(dict(output.get("assessment") or {}))
    assessment["scanner_execution_records"] = deepcopy(records)
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    output["assessment"] = assessment

    source = output.get("canonical_findings")
    if not isinstance(source, list):
        source = output.get("findings_register")
    findings = canonicalize_final_findings(
        item for item in source or [] if isinstance(item, Mapping)
    )
    by_alias: dict[str, Mapping[str, Any]] = {}
    for item in findings:
        for value in (
            item.get("finding_id"),
            item.get("id"),
            *(item.get("finding_aliases") or []),
        ):
            key = _text(value)
            if key:
                by_alias[key] = item

    for surface in _FINDING_SURFACES:
        output[surface] = deepcopy(findings)
    output["executive_risk_register"] = deepcopy(findings[:7])
    output["priority_findings"] = deepcopy(findings[:5])
    for surface in _SYNC_SURFACES:
        if surface in output:
            output[surface] = _sync_finding_reference(output[surface], by_alias)

    exact_findings = [item for item in findings if _source_identity(item)]
    operational_findings = [item for item in findings if not _source_identity(item)]
    total = len(findings)
    output = _sync_counts(
        output,
        total=total,
        exact=len(exact_findings),
        operational=len(operational_findings),
    )
    output["unique_finding_count"] = total
    output["finding_register_count"] = total
    output["canonical_finding_count"] = total
    output["exact_source_finding_count"] = len(exact_findings)
    output["operational_finding_count"] = len(operational_findings)

    register = output.get("client_finding_remediation_register")
    if isinstance(register, Mapping):
        register = deepcopy(dict(register))
        register["code_findings"] = deepcopy(exact_findings)
        register["operational_findings"] = deepcopy(operational_findings)
        summary = deepcopy(dict(register.get("summary") or {}))
        summary.update(
            {
                "decision_finding_count": total,
                "finding_register_count": total,
                "canonical_finding_count": total,
                "exact_source_code_finding_count": len(exact_findings),
                "operational_or_context_finding_count": len(
                    operational_findings
                ),
            }
        )
        register["summary"] = summary
        output["client_finding_remediation_register"] = register

    contract = deepcopy(dict(output.get("v2_prepublication_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "canonical_finding_count": total,
            "scanner_result_count": len(records),
            "completed_scanner_count": len(completed),
            "incomplete_scanner_count": len(incomplete),
            "analyzer_execution_coverage": coverage,
            "source_anchor_deduplication": True,
            "nested_scanner_projection_synchronized": True,
        }
    )
    output["v2_prepublication_contract"] = contract
    return output


def _walk_key_values(value: Any, key_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) == key_name:
                found.append(child)
            found.extend(_walk_key_values(child, key_name))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_key_values(child, key_name))
    return found


def final_projection_checks(canonical: Mapping[str, Any]) -> dict[str, Any]:
    records, completed, _incomplete, coverage = _scanner_population(canonical)
    completed_names = {
        _scanner_name(item.get("scanner_name")) for item in completed
    }
    incomplete_names: set[str] = set()
    for value in _walk_key_values(canonical, "incomplete_analyzers"):
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, Mapping):
                name = _scanner_name(
                    item.get("scanner_name")
                    or item.get("scanner")
                    or item.get("tool")
                )
            else:
                name = _scanner_name(item)
            if name:
                incomplete_names.add(name)
    coverage_values = {
        int(round(float(value)))
        for value in _walk_key_values(canonical, "analyzer_execution_coverage")
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    register = canonical.get("findings_register")
    if not isinstance(register, list):
        register = canonical.get("canonical_findings")
    findings = [item for item in register or [] if isinstance(item, Mapping)]
    identities = [finding_identity(item) for item in findings]
    total = len(findings)
    stated_values = {
        int(value)
        for key in _COUNT_KEYS
        for value in _walk_key_values(canonical, key)
        if isinstance(value, int) and not isinstance(value, bool)
    }
    return {
        "completed_scanners_not_incomplete": not completed_names.intersection(
            incomplete_names
        ),
        "analyzer_coverage_values_consistent": (
            (not coverage_values and not records) or coverage_values == {coverage}
        ),
        "finding_register_has_no_equivalent_duplicates": len(identities)
        == len(set(identities)),
        "stated_unique_finding_count_matches_register": bool(findings)
        and stated_values == {total},
        "canonical_finding_count": total,
        "expected_analyzer_execution_coverage": coverage,
        "completed_scanner_names": sorted(completed_names),
        "incomplete_scanner_names": sorted(incomplete_names),
    }


def validate_final_report_package(
    package: dict[str, Any],
    delegate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    validation = deepcopy(delegate(package))
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    projection = final_projection_checks(canonical)
    checks = deepcopy(dict(validation.get("checks") or {}))
    for key in (
        "completed_scanners_not_incomplete",
        "analyzer_coverage_values_consistent",
        "finding_register_has_no_equivalent_duplicates",
        "stated_unique_finding_count_matches_register",
    ):
        checks[key] = projection[key]
    failed = sorted(key for key, passed in checks.items() if passed is not True)
    validation.update(
        {
            "status": "verified" if not failed else "blocked",
            "version": VERSION,
            "checks": checks,
            "failed_checks": failed,
            "calculated_unique_finding_count": projection[
                "canonical_finding_count"
            ],
            "canonical_projection_truth": projection,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return validation


def install_comprehensive_canonical_projection_truth_v55() -> dict[str, Any]:
    from nico import comprehensive_final_artifact_truth_v54 as artifact_truth
    from nico import phase9_comprehensive_report_integration_v1 as integration

    current_normalizer: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        integration.normalize_canonical_report
    )
    if not getattr(current_normalizer, _NORMALIZER_MARKER, False):

        @wraps(current_normalizer)
        def normalized(report: Mapping[str, Any]) -> dict[str, Any]:
            return normalize_final_projection(current_normalizer(report))

        setattr(normalized, _NORMALIZER_MARKER, True)
        setattr(normalized, "_nico_previous", current_normalizer)
        integration.normalize_canonical_report = normalized

    current_validator: Callable[[dict[str, Any]], dict[str, Any]] = (
        artifact_truth.validate_final_report_package
    )
    if not getattr(current_validator, _VALIDATOR_MARKER, False):

        @wraps(current_validator)
        def validated(package: dict[str, Any]) -> dict[str, Any]:
            return validate_final_report_package(package, current_validator)

        setattr(validated, _VALIDATOR_MARKER, True)
        setattr(validated, "_nico_previous", current_validator)
        artifact_truth.validate_final_report_package = validated

    return {
        "status": "installed",
        "version": VERSION,
        "normalizer_bound": getattr(
            integration.normalize_canonical_report, _NORMALIZER_MARKER, False
        ),
        "validator_bound": getattr(
            artifact_truth.validate_final_report_package, _VALIDATOR_MARKER, False
        ),
        "nested_scanner_projection_synchronized": True,
        "source_anchor_finding_deduplication": True,
        "canonical_register_count_authoritative": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonicalize_final_findings",
    "final_projection_checks",
    "finding_identity",
    "install_comprehensive_canonical_projection_truth_v55",
    "normalize_final_projection",
]
