from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping

from nico import comprehensive_client_readiness_v59 as v59
from nico.phase14_analyzer_evidence_v1 import apply_analyzer_evidence
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

VERSION = "nico.comprehensive_authoritative_scanner_truth.v62"
_REQUIRED_TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)

_INCOMPLETE_ANALYZER_LIMITATION = re.compile(
    r"^Incomplete (?:applicable analyzers|analyzers with unproven applicability):\s*(?P<names>[^.]+)\.?$",
    re.IGNORECASE,
)
_APPLICABLE_ANALYZER_LINE = re.compile(
    r"^(?:Applicable|Applicability unproven) analyzers:\s*(?P<names>[^.]+)\.?$",
    re.IGNORECASE,
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_EVIDENCE_ADJUSTED_TEXT = re.compile(
    r"(?P<prefix>Evidence-Adjusted(?: readiness)?(?: is|:)\s*)\d+/100",
    re.IGNORECASE,
)
_EVIDENCE_SCORE_KEYS = {
    "evidence_adjusted_score",
    "canonical_evidence_adjusted_score",
    "evidence_readiness_score",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _commit_sha(value: Mapping[str, Any]) -> str:
    assessment = _mapping(value.get("assessment"))
    identities = (
        _mapping(value.get("identity")),
        _mapping(value.get("assessment_identity")),
        _mapping(assessment.get("identity")),
    )
    candidates = [
        value.get("commit_sha"),
        value.get("immutable_revision"),
        assessment.get("commit_sha"),
    ]
    for identity in identities:
        candidates.extend((identity.get("commit_sha"), identity.get("immutable_revision")))
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if _SHA_RE.fullmatch(text):
            return text
    return ""


def _phase14_records(
    records: list[dict[str, Any]], *, commit_sha: str
) -> list[dict[str, Any]]:
    """Project authoritative records into the raw Phase 14 evidence contract."""

    projected: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        scanner = v59._tool(record)
        if not scanner:
            continue
        status = str(record.get("status") or record.get("state") or "unknown")
        normalized_status = status.casefold().replace("-", "_").replace(" ", "_")
        if normalized_status in {
            "completed_clean",
            "completed_with_findings",
            "passed",
            "pass",
            "ok",
            "complete",
        }:
            status = "completed"
        item = {
            "scanner": scanner,
            "status": status,
            "commit_sha": record.get("commit_sha") or commit_sha,
            "run_sequence": record.get("run_sequence") or index,
            "capture_complete": bool(
                record.get("capture_complete") is True
                or record.get("verified_complete") is True
                or record.get("verified_for_this_report") is True
            ),
            "artifact_sha256": record.get("artifact_sha256")
            or record.get("artifact_hash")
            or record.get("output_sha256"),
            "exit_code": record.get("exit_code"),
            "coverage": deepcopy(record.get("coverage") or {}),
        }
        if record.get("applicable") is False and record.get("applicability_state") == "not_applicable":
            item["status"] = "not_applicable"
            item.pop("artifact_sha256", None)
            item["capture_complete"] = True
            item["not_applicable_reason"] = (
                record.get("applicability_reason")
                or record.get("not_applicable_reason")
                or record.get("failure_reason")
            )
        projected.append(item)
    return projected


def _names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    output: list[str] = []
    for item in value:
        name = v59._tool(item)
        if name and name not in output:
            output.append(name)
    return output


def _live_evidence(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = _mapping(canonical.get("assessment"))
    for candidate in (
        canonical.get("live_scanner_evidence"),
        assessment.get("live_scanner_evidence"),
        canonical.get("scanner_run_summary"),
        assessment.get("scanner_run_summary"),
    ):
        if isinstance(candidate, Mapping) and any(
            key in candidate
            for key in (
                "tools_requested",
                "tools_run",
                "failed_tools",
                "unavailable_tools",
                "timed_out_tools",
            )
        ):
            return candidate
    return {}


def _requested_records(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Retain the full requested population after applicability normalization."""

    assessment = _mapping(canonical.get("assessment"))
    for candidate in (
        canonical.get("requested_scanner_records"),
        assessment.get("requested_scanner_records"),
    ):
        if isinstance(candidate, list):
            records = [
                deepcopy(dict(item))
                for item in candidate
                if isinstance(item, Mapping)
            ]
            if records:
                return records
    return v59._direct_scanner_records(canonical)


def _requested_tools(
    canonical: Mapping[str, Any],
    records: list[dict[str, Any]],
) -> list[str]:
    live = _live_evidence(canonical)
    requested = _names(live.get("tools_requested"))
    if requested:
        return requested

    direct: list[str] = []
    for record in records:
        name = v59._tool(record)
        if name and name not in direct:
            direct.append(name)
    if direct:
        return direct

    assessment = _mapping(canonical.get("assessment"))
    for candidate in (
        canonical.get("requested_analyzers"),
        canonical.get("applicable_analyzers"),
        assessment.get("requested_analyzers"),
        assessment.get("applicable_analyzers"),
    ):
        names = _names(candidate)
        if names:
            return names
    return []


def _failure_reason(name: str, live: Mapping[str, Any]) -> str:
    if name in set(_names(live.get("timed_out_tools"))):
        return f"{name} timed out before complete exact-SHA evidence was retained."
    if name in set(_names(live.get("unavailable_tools"))):
        return f"{name} was unavailable for the exact-run scanner execution."
    if name in set(_names(live.get("failed_tools"))):
        return f"{name} failed during the exact-run scanner execution."
    return f"{name} did not retain a complete exact-SHA scanner record."


def _authoritative_truth(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    records = _requested_records(canonical)
    truth: dict[str, dict[str, Any]] = {}
    for record in records:
        state = v59._scanner_state(record)
        if state is not None:
            truth[state["scanner_name"]] = state

    live = _live_evidence(canonical)
    requested = _requested_tools(canonical, records)
    failed = set(_names(live.get("failed_tools")))
    unavailable = set(_names(live.get("unavailable_tools")))
    timed_out = set(_names(live.get("timed_out_tools")))
    failed_or_missing = failed | unavailable | timed_out

    for name in requested:
        state = truth.get(name)
        if state is None:
            truth[name] = {
                "scanner_name": name,
                "status": "failed" if name in failed_or_missing else "missing",
                "completed": False,
                "verified": False,
                "exact_commit_match": False,
                "artifact_retained": False,
                "finding_count": 0,
                "failure_reason": _failure_reason(name, live),
            }
            continue
        if name in failed_or_missing:
            state.update(
                {
                    "status": "failed",
                    "completed": False,
                    "verified": False,
                    "failure_reason": state.get("failure_reason")
                    or _failure_reason(name, live),
                }
            )

    if set(requested) == set(_REQUIRED_TOOLS):
        requested = list(_REQUIRED_TOOLS)
    return truth, requested


def _canonical_records(
    output: Mapping[str, Any],
    truth: Mapping[str, Mapping[str, Any]],
    requested_tools: list[str],
) -> list[dict[str, Any]]:
    existing = _requested_records(output)
    records: dict[str, dict[str, Any]] = {}
    for raw in existing:
        name = v59._tool(raw)
        if not name:
            continue
        item = deepcopy(raw)
        state = truth.get(name)
        if state is not None:
            raw_status = str(
                item.get("status")
                or item.get("state")
                or item.get("execution_status")
                or ""
            ).casefold().replace("-", "_")
            projected_status = state.get("status")
            if state.get("completed") is not True and raw_status in {
                "unavailable",
                "missing",
                "not_installed",
                "not_available",
            }:
                projected_status = raw_status
            item.update(
                {
                    "scanner_name": name,
                    "status": projected_status,
                    "state": projected_status,
                    "completed": state.get("completed") is True,
                    "verified": state.get("verified") is True,
                    "verified_complete": state.get("verified") is True,
                    "exact_commit_match": state.get("exact_commit_match") is True,
                    "finding_count": state.get("finding_count", 0),
                    "failure_reason": state.get("failure_reason", ""),
                    "failure_or_unavailable_reason": state.get("failure_reason", ""),
                }
            )
        records[name] = item

    for name in requested_tools:
        if name in records:
            continue
        state = truth[name]
        records[name] = {
            "scanner_name": name,
            "tool": name,
            "status": state.get("status"),
            "state": state.get("status"),
            "completed": False,
            "verified": False,
            "verified_complete": False,
            "verified_for_this_report": False,
            "exact_commit_match": state.get("exact_commit_match") is True,
            "artifact_retained": False,
            "finding_count": 0,
            "findings": [],
            "failure_reason": state.get("failure_reason", ""),
            "failure_or_unavailable_reason": state.get("failure_reason", ""),
            "execution_source": "live_scanner_manifest_synthetic_record_v62",
            "current_run": True,
            "required": True,
        }
    order = requested_tools or sorted(records)
    return [records[name] for name in order if name in records] + [
        records[name] for name in sorted(records) if name not in set(order)
    ]


def _analyzer_population_lines(
    value: str,
    *,
    applicable: set[str],
    not_applicable: set[str],
    completed: set[str],
    field: str,
) -> list[str] | None:
    match = _APPLICABLE_ANALYZER_LINE.fullmatch(value.strip())
    is_incomplete = False
    if not match and field in {"unavailable", "limitations", "unavailable_data_notes"}:
        match = _INCOMPLETE_ANALYZER_LIMITATION.fullmatch(value.strip())
        is_incomplete = bool(match)
    if not match:
        return None
    names = [name.strip() for name in match.group("names").split(",") if name.strip()]
    names = [name for name in names if name.casefold() not in not_applicable]
    if is_incomplete:
        names = [name for name in names if name.casefold() not in completed]
    established = [name for name in names if name.casefold() in applicable]
    unresolved = [name for name in names if name.casefold() not in applicable]
    lines = []
    if established:
        label = "Incomplete applicable analyzers" if is_incomplete else "Applicable analyzers"
        lines.append(f"{label}: {', '.join(established)}.")
    if unresolved:
        label = (
            "Incomplete analyzers with unproven applicability"
            if is_incomplete else "Applicability unproven analyzers"
        )
        lines.append(f"{label}: {', '.join(unresolved)}.")
    return lines


def _reconcile_unavailable_scanner_limitations(
    value: Mapping[str, Any],
    *,
    applicable: set[str],
    not_applicable: set[str],
    completed: set[str],
) -> dict[str, Any]:
    """Reconcile authored projections without traversing retained scanner payloads."""

    output = deepcopy(dict(value))
    limitation_fields = {"unavailable", "limitations", "unavailable_data_notes"}

    def project(owner: dict[str, Any], *, include_evidence: bool) -> None:
        fields = limitation_fields | ({"evidence"} if include_evidence else set())
        for field in fields:
            values = owner.get(field)
            if not isinstance(values, list):
                continue
            lines: list[Any] = []
            for item in values:
                # Structured retained evidence is opaque, even when it contains
                # keys or source text resembling a generated report heading.
                if not isinstance(item, str):
                    lines.append(item)
                    continue
                population = _analyzer_population_lines(
                    item, applicable=applicable, not_applicable=not_applicable,
                    completed=completed, field=field,
                )
                if population is not None:
                    lines.extend(population)
                elif field in limitation_fields and any(
                    item.strip().casefold().startswith(f"{name}:")
                    for name in not_applicable
                ):
                    continue
                else:
                    lines.append(item)
            owner[field] = lines

    owners = [output]
    if isinstance(output.get("assessment"), dict):
        owners.append(output["assessment"])
    for owner in owners:
        project(owner, include_evidence=False)
        for collection in ("sections", "stage_summaries"):
            for row in owner.get(collection) or []:
                if not isinstance(row, dict):
                    continue
                stage_id = str(row.get("stage_id") or row.get("id") or "")
                if stage_id == "client_evidence_summary" or stage_id.startswith("client_human_evidence_"):
                    continue
                project(row, include_evidence=True)
    return output


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _synchronize_evidence_score_aliases(
    value: Any,
    *,
    technical_score: int,
    payload_penalty: int,
    execution_penalty: int,
) -> Any:
    """Repair derived score aliases after applicability changes the denominator."""

    evidence_penalty = payload_penalty + execution_penalty
    evidence_adjusted = max(0, technical_score - evidence_penalty)
    if isinstance(value, list):
        return [
            _synchronize_evidence_score_aliases(
                item,
                technical_score=technical_score,
                payload_penalty=payload_penalty,
                execution_penalty=execution_penalty,
            )
            for item in value
        ]
    if isinstance(value, str):
        return _EVIDENCE_ADJUSTED_TEXT.sub(
            lambda match: f"{match.group('prefix')}{evidence_adjusted}/100",
            value,
        )
    if not isinstance(value, Mapping):
        return value

    output = {
        str(key): _synchronize_evidence_score_aliases(
            item,
            technical_score=technical_score,
            payload_penalty=payload_penalty,
            execution_penalty=execution_penalty,
        )
        for key, item in value.items()
    }
    for key in _EVIDENCE_SCORE_KEYS:
        if key in output:
            output[key] = evidence_adjusted
    if "incomplete_analyzer_penalty" in output:
        output["incomplete_analyzer_penalty"] = execution_penalty
    if "evidence_completeness_penalty" in output:
        output["evidence_completeness_penalty"] = evidence_penalty
    if "assurance_penalty" in output:
        output["assurance_penalty"] = evidence_penalty
    if "evidence_penalty_points" in output:
        output["evidence_penalty_points"] = evidence_penalty
    if "score_formula" in output:
        output["score_formula"] = (
            f"{technical_score} - {payload_penalty} - {execution_penalty} = "
            f"{evidence_adjusted}"
        )
    return output


def reconcile_authoritative_scanner_truth(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile exact-run records without counting technology-inapplicable tools."""

    output = deepcopy(dict(canonical))
    raw_truth, requested_tools = _authoritative_truth(output)
    raw_records = _canonical_records(output, raw_truth, requested_tools)
    output["requested_scanner_records"] = deepcopy(raw_records)
    output["scanner_execution_records"] = deepcopy(raw_records)
    assessment = deepcopy(dict(_mapping(output.get("assessment"))))
    assessment["requested_scanner_records"] = deepcopy(raw_records)
    assessment["scanner_execution_records"] = deepcopy(raw_records)
    output["assessment"] = assessment
    output = normalize_scanner_applicability_canonical(output)
    applicability_summary = deepcopy(output["assessment"]["scanner_applicability_summary"])

    requested_records = [
        deepcopy(dict(item))
        for item in output.get("requested_scanner_records") or []
        if isinstance(item, Mapping)
    ]
    required_records = [
        deepcopy(dict(item))
        for item in output.get("scanner_execution_records") or []
        if isinstance(item, Mapping)
    ]
    not_applicable_records = [
        deepcopy(dict(item))
        for item in output.get("not_applicable_scanner_records") or []
        if isinstance(item, Mapping)
    ]
    applicable_records = [r for r in required_records if r.get("applicable") is True]
    unproven_records = [r for r in required_records if r.get("applicable") is None]
    applicable_names = {v59._tool(r) for r in applicable_records}
    unproven_names = sorted(v59._tool(r) for r in unproven_records)
    truth: dict[str, dict[str, Any]] = {}
    for record in requested_records:
        state = v59._scanner_state(record)
        if state is not None:
            truth[state["scanner_name"]] = state

    required_tools = [
        name
        for record in required_records
        if (name := v59._tool(record))
    ]
    required_set = set(required_tools)
    requested = len(required_tools)
    completed = {
        name
        for name, state in truth.items()
        if state.get("completed") is True and name in required_set
    }
    incomplete = required_set - completed

    assessment = _mapping(output.get("assessment"))
    technical = assessment.get("technical_score") or output.get("technical_score")
    try:
        technical_score = int(round(float(technical)))
    except (TypeError, ValueError):
        technical_score = None

    output = v59._normalize_tree(
        output,
        truth=truth,
        completed=completed,
        incomplete=incomplete,
        requested=requested,
        symbols=v59._symbols(output),
        technical_score=technical_score,
    )
    output["requested_scanner_records"] = deepcopy(requested_records)
    output["scanner_execution_records"] = deepcopy(required_records)
    output["not_applicable_scanner_records"] = deepcopy(not_applicable_records)
    not_applicable_names = {
        name.casefold()
        for record in not_applicable_records
        if (name := v59._tool(record))
    }
    output = _reconcile_unavailable_scanner_limitations(
        output,
        applicable=applicable_names,
        not_applicable=not_applicable_names,
        completed=completed,
    )

    # Phase 15 may have produced an analyzer summary before repository
    # applicability was finalized. Rebuild the projection from authoritative raw
    # records so summary rows are never re-ingested as evidence and inapplicable
    # analyzers cannot remain required blockers.
    commit_sha = _commit_sha(output)
    phase14_records = _phase14_records(requested_records, commit_sha=commit_sha)
    if commit_sha and phase14_records:
        output = apply_analyzer_evidence(
            output,
            expected_sha=commit_sha,
            records=phase14_records,
            required_scanners=required_tools,
        )
        evidence_health = deepcopy(dict(output.get("evidence_health_summary") or {}))
        phase14 = _mapping(evidence_health.get("phase14_analyzer_evidence"))
        analyzer_summaries = [
            deepcopy(dict(item))
            for item in phase14.get("analyzers") or []
            if isinstance(item, Mapping)
        ]
        execution_incomplete = [
            item
            for item in analyzer_summaries
            if item.get("required") is True
            and item.get("status") not in {"completed", "success"}
        ]
        evidence_health["completed_scanners"] = [
            item.get("scanner")
            for item in analyzer_summaries
            if item.get("status") in {"completed", "success"}
        ]
        evidence_health["incomplete_analyzers"] = deepcopy(execution_incomplete)
        evidence_health["incomplete_scanner_records"] = deepcopy(execution_incomplete)
        output["evidence_health_summary"] = evidence_health
    assessment_output = deepcopy(dict(_mapping(output.get("assessment"))))
    assessment_output["scanner_applicability_summary"] = applicability_summary
    assessment_output["requested_scanner_records"] = deepcopy(requested_records)
    assessment_output["scanner_execution_records"] = deepcopy(required_records)
    assessment_output["completed_scanner_records"] = [
        deepcopy(record)
        for record in required_records
        if record.get("completed") is True
    ]
    assessment_output["incomplete_scanner_records"] = [
        deepcopy(record)
        for record in required_records
        if record.get("completed") is not True
    ]
    assessment_output["not_applicable_scanner_records"] = deepcopy(
        not_applicable_records
    )
    assessment_output["scanner_execution_summary"] = {
        **deepcopy(dict(_mapping(assessment_output.get("scanner_execution_summary")))),
        "record_count": len(requested_records),
        "applicable_record_count": len(applicable_records),
        "applicability_unproven_count": len(unproven_records),
        "not_applicable_count": len(not_applicable_records),
        "completed_count": len(completed),
        "verified_count": sum(
            record.get("verified_complete") is True
            or record.get("verified_for_this_report") is True
            for record in required_records
        ),
        "incomplete_count": len(incomplete),
    }
    output["assessment"] = assessment_output

    coverage = round(100 * len(completed) / requested) if requested else 0
    output["analyzer_execution_coverage"] = coverage
    output["scanner_execution_coverage"] = coverage
    output["completed_applicable_analyzers"] = len(completed & applicable_names)
    output["incomplete_applicable_analyzers"] = len(incomplete & applicable_names)

    # Scoring is produced before repository applicability is finalized. A tool that
    # is later proven inapplicable must not survive as a numeric evidence penalty or
    # a stale 8/9 coverage claim anywhere in the canonical projection.
    if technical_score is not None and not_applicable_records:
        assessment_for_penalty = _mapping(output.get("assessment"))
        score_contract = _mapping(assessment_for_penalty.get("score_contract"))
        evidence_coverage = _mapping(assessment_for_penalty.get("evidence_coverage"))
        payload_penalty = max(
            _nonnegative_int(score_contract.get("missing_raw_payload_penalty")),
            _nonnegative_int(evidence_coverage.get("missing_raw_payload_penalty")),
        )
        execution_penalty = min(12, len(incomplete) * 4)
        output = _synchronize_evidence_score_aliases(
            output,
            technical_score=technical_score,
            payload_penalty=payload_penalty,
            execution_penalty=execution_penalty,
        )
        assessment_output = deepcopy(dict(_mapping(output.get("assessment"))))
        coverage_output = deepcopy(
            dict(_mapping(assessment_output.get("evidence_coverage")))
        )
        coverage_output.update(
            {
                "percent": coverage,
                "applicable_analyzers": len(applicable_records),
                "required_analyzers": requested,
                "applicability_unproven_analyzers": unproven_names,
                "completed_verified_analyzers": len(completed),
                "incomplete_analyzers": sorted(incomplete),
            }
        )
        assessment_output["evidence_coverage"] = coverage_output
        output["assessment"] = assessment_output

    reconciliation = deepcopy(dict(_mapping(output.get("v2_scanner_reconciliation"))))
    if reconciliation:
        reconciliation.update(
            {
                "record_count": len(requested_records),
                "applicable_record_count": len(applicable_records),
                "applicability_unproven_count": len(unproven_records),
                "not_applicable_count": len(not_applicable_records),
                "completed_count": len(completed),
                "incomplete_count": len(incomplete),
                "technology_inapplicable_scanners_excluded": True,
            }
        )
        output["v2_scanner_reconciliation"] = reconciliation

    contract = deepcopy(dict(output.get("client_readiness_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "scanner_execution_completion": coverage,
            "analyzer_execution_coverage": coverage,
            "coverage_numerator": len(completed),
            "coverage_denominator": requested,
            "coverage_population": "applicable_or_applicability_unproven_scanner_executions",
            "requested_exact_run_scanners": list(requested_tools),
            "applicable_exact_run_scanners": sorted(applicable_names),
            "applicability_unproven_scanners": unproven_names,
            "not_applicable_exact_run_scanners": [
                v59._tool(record) for record in not_applicable_records
            ],
            "completed_exact_commit_scanners": sorted(completed),
            "incomplete_analyzers": sorted(incomplete),
            "authoritative_scanner_record_count": len(requested_records),
            "applicable_scanner_record_count": len(applicable_records),
            "not_applicable_scanner_record_count": len(not_applicable_records),
            "authoritative_source": "direct_exact_run_records_plus_live_scanner_manifest",
            "missing_requested_scanners_retained_as_incomplete_records": True,
            "technology_inapplicable_scanners_excluded_from_coverage_denominator": True,
            "not_applicable_scanners_receive_completion_credit": False,
            "recursive_stale_projection_counts_ignored": True,
            "maturity_label": v59._maturity_label(technical_score),
            "technical_maturity_is_not_operational_readiness": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "approval_required_for_client_delivery": True,
            "cross_format_truth_required": True,
            "identifier_integrity_required": True,
        }
    )
    output["client_readiness_contract"] = contract
    if unproven_names:
        gate = deepcopy(dict(output.get("delivery_gate") or {}))
        gate["analyzer_evidence_ready"] = False
        gate["analyzer_assurance_state"] = "review_limited"
        gate["applicability_unproven_scanners"] = unproven_names
        gate["analyzer_evidence_blockers"] = list(gate.get("analyzer_evidence_blockers") or []) + [
            f"{name}: applicability_unproven" for name in unproven_names]
        output["delivery_gate"] = gate
    health = deepcopy(dict(output.get("evidence_health_summary") or {}))
    health["applicability_unproven_scanners"] = unproven_names
    output["evidence_health_summary"] = health
    def applicable_counts(value: Any) -> Any:
        if isinstance(value, list):
            return [applicable_counts(item) for item in value]
        if not isinstance(value, Mapping):
            return value
        return {key: (len(completed & applicable_names) if key in {"completed_applicable_analyzers", "completed_applicable_scanners"}
            else len(incomplete & applicable_names) if key in {"incomplete_applicable_analyzers", "incomplete_applicable_scanners"}
            else applicable_counts(item)) for key, item in value.items()}
    output = applicable_counts(output)
    output["scanner_state_reconciled"] = True
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    # Applicability can become known at this boundary after assurance was bound.
    # Refresh the existing dependent state from the final canonical records.
    if isinstance(output.get("source_security_assurance"), Mapping):
        from nico.comprehensive_score_assurance_ledger_v45 import bind_source_security_assurance
        output = bind_source_security_assurance(output)
    return output


__all__ = [
    "VERSION",
    "reconcile_authoritative_scanner_truth",
]
