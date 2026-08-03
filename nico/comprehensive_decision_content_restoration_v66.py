from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.v2_assessment_pipeline import canonicalize_findings

VERSION = "nico.comprehensive-decision-content-restoration.v66"

_FINDING_SURFACES = (
    "canonical_findings",
    "decision_grade_findings_register",
    "findings_register",
    "executive_risk_register",
    "priority_findings",
)
_REVIEW_CATEGORIES = {"dependency", "secret", "static"}
_NON_PRODUCTION_SEGMENTS = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "generated",
    "vendor",
    "vendors",
    "dist",
    "build",
    "coverage",
    "node_modules",
}
_PATH_RE = re.compile(r"([A-Za-z0-9_.\-/]+\.(?:py|tsx?|jsx?|mjs|cjs|json|ya?ml|toml))")


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _iter_mappings(value: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 14:
        return
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_mappings(child, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_mappings(child, depth + 1)


def _mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [deepcopy(dict(item)) for item in value if isinstance(item, Mapping)]


def _decision_grade_shape(item: Mapping[str, Any]) -> bool:
    identity = bool(
        _text(item.get("finding_id") or item.get("id"))
        or _text(item.get("location") or item.get("exact_source") or item.get("path"))
    )
    descriptive = bool(
        _text(item.get("title") or item.get("decision_title"))
        or _text(item.get("rule_id") or item.get("finding_family"))
    )
    decision_fields = sum(
        bool(item.get(key))
        for key in (
            "recommendation",
            "business_impact",
            "impact",
            "acceptance_criteria",
            "verification",
            "owner_role",
            "effort",
            "residual_risk",
            "rollback",
            "exit_criteria",
        )
    )
    return identity and descriptive and decision_fields >= 2


def _stable_record_key(item: Mapping[str, Any]) -> str:
    for key in ("finding_id", "id", "advisory_id", "rule_id"):
        value = _text(item.get(key)).casefold()
        if value:
            return f"{key}:{value}"
    location = _text(item.get("location") or item.get("exact_source") or item.get("path")).casefold()
    symbol = _text(
        item.get("symbol")
        or item.get("function")
        or item.get("function_or_component")
        or item.get("component")
    ).casefold()
    title = _text(item.get("title") or item.get("decision_title")).casefold()
    return hashlib.sha256(f"{location}|{symbol}|{title}".encode("utf-8")).hexdigest()


def _manual_dedupe(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in records:
        item = deepcopy(dict(raw))
        key = _stable_record_key(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
            continue
        current = selected[key]
        current_quality = len(json.dumps(current, sort_keys=True, default=str))
        item_quality = len(json.dumps(item, sort_keys=True, default=str))
        if item_quality > current_quality:
            selected[key] = item
    return [selected[key] for key in order]


def _canonicalize(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped = _manual_dedupe(records)
    if not deduped:
        return []
    try:
        return canonicalize_findings(deduped)
    except (TypeError, ValueError):
        return deduped


def _structured_findings(
    raw_stages: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    roots: list[Any] = [assessment]
    for stage_id in (
        "risk_reduction_and_executive_briefing",
        "evidence_reconciliation_and_scoring",
        "decision_report_generation",
    ):
        stage = raw_stages.get(stage_id)
        if isinstance(stage, Mapping):
            roots.append(stage)

    for root in roots:
        for node in _iter_mappings(root):
            for surface in _FINDING_SURFACES:
                records.extend(
                    item
                    for item in _mapping_items(node.get(surface))
                    if _decision_grade_shape(item)
                )
            generic = _mapping_items(node.get("findings"))
            records.extend(item for item in generic if _decision_grade_shape(item))
    return _canonicalize(records)


def _path_from_hotspot(item: Mapping[str, Any]) -> str:
    for key in ("path", "source_path", "file", "filename", "location"):
        value = _text(item.get(key))
        match = _PATH_RE.search(value)
        if match:
            return match.group(1)
    return ""


def _non_production_path(path: str) -> bool:
    normalized = path.casefold().replace("\\", "/")
    segments = [segment for segment in normalized.split("/") if segment]
    filename = segments[-1] if segments else ""
    return bool(
        filename.startswith("test_")
        or filename.endswith(
            ("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
        )
        or any(segment in _NON_PRODUCTION_SEGMENTS for segment in segments)
    )


def _complexity_hotspots(raw_stages: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, int, str], dict[str, Any]] = {}
    for node in _iter_mappings(raw_stages):
        hotspots = _mapping_items(node.get("hotspots"))
        for item in hotspots:
            path = _path_from_hotspot(item)
            line = _integer(item.get("line") or item.get("start_line"))
            name = _text(
                item.get("name")
                or item.get("symbol")
                or item.get("function")
                or item.get("component")
            )
            complexity = _integer(
                item.get("cyclomatic_complexity")
                or item.get("complexity")
                or item.get("cc")
            )
            if not path or not name or complexity < 30 or _non_production_path(path):
                continue
            key = (path.casefold(), line, name.casefold())
            current = selected.get(key)
            if current is None or complexity > _integer(
                current.get("cyclomatic_complexity") or current.get("complexity")
            ):
                normalized = deepcopy(item)
                normalized.update(
                    {
                        "path": path,
                        "line": line,
                        "name": name,
                        "cyclomatic_complexity": complexity,
                    }
                )
                selected[key] = normalized
    return sorted(
        selected.values(),
        key=lambda item: (
            -_integer(item.get("cyclomatic_complexity")),
            _text(item.get("path")).casefold(),
            _integer(item.get("line")),
        ),
    )[:50]


def _complexity_recommendation(name: str, path: str) -> str:
    lowered = f"{name} {path}".casefold()
    if "report" in lowered or "pdf" in lowered or "markdown" in lowered:
        return (
            f"Separate canonical-data preparation, translation selection, layout construction, "
            f"and artifact validation in `{name}`; preserve snapshot report fixtures and "
            "cross-format truth tests; target cyclomatic complexity at or below 30."
        )
    if any(token in lowered for token in ("collect", "evidence", "snapshot", "scanner")):
        return (
            f"Split collection, normalization, classification, and serialization responsibilities "
            f"in `{name}` into bounded pure helpers; preserve exact-SHA evidence fixtures and add "
            "regression tests for failure and partial-evidence paths."
        )
    if name == "main" or path.startswith("scripts/"):
        return (
            f"Separate argument parsing, orchestration, evidence assembly, and artifact writing in "
            f"`{name}`; add command-level characterization tests and enforce the approved complexity threshold."
        )
    return (
        f"Decompose `{name}` around cohesive branch groups, preserve behavior with characterization "
        "tests, and enforce cyclomatic complexity at or below 30 on the exact remediation commit."
    )


def _synthesized_complexity_findings(
    hotspots: list[Mapping[str, Any]],
    commit_sha: str,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in hotspots:
        path = _text(item.get("path"))
        line = _integer(item.get("line"))
        end_line = _integer(item.get("end_line"))
        name = _text(item.get("name"))
        complexity = _integer(item.get("cyclomatic_complexity"))
        method = _text(item.get("method") or "retained exact-SHA complexity evidence")
        location = f"{path}:{line}" if line else path
        if end_line and end_line >= line:
            location = f"{path}:{line}-{end_line}"
        fingerprint = hashlib.sha256(
            f"{commit_sha}|{path}|{line}|{name}|complexity_hotspot".encode("utf-8")
        ).hexdigest()[:12].upper()
        verification = [
            f"The exact-SHA rerun no longer reports cyclomatic complexity above 30 at {path}:{line}.",
            "Targeted characterization tests pass on the remediation commit.",
            "The repository's complete required-check suite passes on the remediation commit.",
            "No new material regression or cross-format report-truth mismatch is introduced.",
        ]
        findings.append(
            {
                "finding_id": f"NICO-FINDING-{fingerprint}",
                "id": f"NICO-FINDING-{fingerprint}",
                "category": "architecture",
                "finding_family": "complexity_hotspot",
                "rule_id": "complexity_hotspot",
                "priority": "P1",
                "severity": "high",
                "status": "review_required",
                "disposition": "proposed_exact_source_review_required",
                "title": f"Reduce complexity in {name}",
                "decision_title": f"Reduce complexity in {name}",
                "location": location,
                "exact_source": location,
                "path": path,
                "line": line,
                "end_line": end_line or None,
                "symbol": name,
                "function": name,
                "function_or_component": name,
                "fact": (
                    f"cyclomatic_complexity={complexity}; method={method}; "
                    "source=retained exact-SHA architecture evidence"
                ),
                "evidence": (
                    f"cyclomatic_complexity={complexity}; method={method}; "
                    "exact_commit_match=True"
                ),
                "interpretation": f"Concentrated branching in `{name}`.",
                "technical_impact": "High-complexity code hotspot.",
                "business_impact": (
                    "Concentrated branch logic increases regression risk, review cost, "
                    "and the difficulty of safe change."
                ),
                "recommendation": _complexity_recommendation(name, path),
                "verification": verification,
                "acceptance_criteria": verification,
                "rollback": (
                    "Revert the isolated remediation change if targeted or full verification fails; "
                    "retain the failed evidence and keep client delivery blocked."
                ),
                "exit_criteria": [
                    "All verification requirements pass on the exact remediation commit.",
                    "The exact-SHA rerun no longer reports the condition as unresolved material risk.",
                    "No new material regression is introduced.",
                ],
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
                "cost_of_inaction": (
                    "Higher regression probability, slower review, and growing maintenance cost."
                ),
                "residual_risk": "Requires exact-source human review after automated remediation proof.",
                "source_commit_sha": commit_sha,
                "exact_commit_match": True,
                "production_scope": True,
                "production_relevant": True,
                "requires_human_triage": True,
                "technical_score_impact": "architecture_score_input",
            }
        )
    return _canonicalize(findings)


def _finding_summary_candidates(raw_stages: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values: list[Mapping[str, Any]] = []
    for node in _iter_mappings(raw_stages):
        summary = node.get("finding_summary")
        if isinstance(summary, Mapping):
            values.append(summary)
        triage = node.get("scanner_triage")
        if isinstance(triage, Mapping) and isinstance(triage.get("finding_summary"), Mapping):
            values.append(triage["finding_summary"])
    return values


def _summary_quality(value: Mapping[str, Any]) -> tuple[int, int, int]:
    raw = _integer(value.get("raw_total") or value.get("raw"))
    review = _integer(value.get("review_required_total") or value.get("review"))
    populated = len(json.dumps(value, sort_keys=True, default=str))
    return review, raw, populated


def _normalize_count_group(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _integer(value.get(key))
        for key in (
            "raw",
            "material",
            "review_required",
            "excluded_test_only",
            "approved_or_nonblocking",
        )
        if value.get(key) not in (None, "")
    }


def _review_candidate_summary(raw_stages: Mapping[str, Any]) -> dict[str, Any]:
    candidates = _finding_summary_candidates(raw_stages)
    source = max(candidates, key=_summary_quality) if candidates else {}
    by_category_raw = source.get("by_category") if isinstance(source.get("by_category"), Mapping) else {}
    by_tool_raw = source.get("by_tool") if isinstance(source.get("by_tool"), Mapping) else {}
    by_category = {
        str(name): _normalize_count_group(value)
        for name, value in by_category_raw.items()
        if isinstance(value, Mapping)
    }
    by_tool = {
        str(name): _normalize_count_group(value)
        for name, value in by_tool_raw.items()
        if isinstance(value, Mapping)
    }
    review_total = _integer(
        source.get("review_required_total")
        or source.get("review")
        or sum(value.get("review_required", 0) for value in by_category.values())
    )
    raw_total = _integer(
        source.get("raw_total")
        or source.get("raw")
        or sum(value.get("raw", 0) for value in by_category.values())
    )
    material_total = _integer(
        source.get("material_total")
        or source.get("material")
        or sum(value.get("material", 0) for value in by_category.values())
    )
    return {
        "raw_total": raw_total,
        "verified_material_total": material_total,
        "review_required_total": review_total,
        "excluded_test_only_total": _integer(source.get("excluded_test_only_total")),
        "approved_or_nonblocking_total": _integer(source.get("approved_or_nonblocking_total")),
        "by_category": by_category,
        "by_tool": by_tool,
        "score_effect": "assurance_only_until_triaged",
        "confirmed_material_findings_are_separate": True,
        "raw_candidate_payload_may_be_retained_outside_final_report": True,
    }


def _safe_review_candidate(item: Mapping[str, Any]) -> dict[str, Any] | None:
    category = _text(item.get("category")).casefold()
    status = _text(item.get("status") or item.get("disposition")).casefold()
    review_required = item.get("review_required") is True or any(
        token in status for token in ("review_required", "triage_required", "candidate", "unverified")
    )
    if category not in _REVIEW_CATEGORIES or not review_required or _decision_grade_shape(item):
        return None
    output: dict[str, Any] = {
        "category": category,
        "tool": _text(item.get("tool") or item.get("scanner_name")),
        "candidate_id": _text(
            item.get("advisory_id")
            or item.get("rule_id")
            or item.get("finding_id")
            or item.get("id")
        ),
        "title": _text(item.get("title") or item.get("message")),
        "severity": _text(item.get("severity")),
        "location": _text(item.get("location") or item.get("path")),
        "package": _text(item.get("package") or item.get("package_name")),
        "installed_version": _text(item.get("installed_version") or item.get("version")),
        "fixed_version": _text(item.get("fixed_version") or item.get("fixed_versions")),
        "dependency_path": _text(item.get("dependency_path")),
        "scope": _text(item.get("scope") or item.get("production_scope")),
        "reachability": _text(item.get("reachability")),
        "disposition": _text(item.get("disposition") or "review_required"),
        "score_effect": "assurance_only_until_triaged",
    }
    return {key: value for key, value in output.items() if value not in (None, "")}


def _review_candidate_register(raw_stages: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for node in _iter_mappings(raw_stages):
        candidate = _safe_review_candidate(node)
        if not candidate:
            continue
        key = _stable_record_key(candidate)
        selected.setdefault(key, candidate)
        if len(selected) >= 250:
            break
    return list(selected.values())


def _ci_operational_context(
    raw_stages: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for section in assessment.get("sections") or []:
        if not isinstance(section, Mapping) or _text(section.get("id")).casefold() != "ci_cd":
            continue
        contract = section.get("score_contract") if isinstance(section.get("score_contract"), Mapping) else {}
        trend = contract.get("operational_trend") if isinstance(contract.get("operational_trend"), Mapping) else {}
        if trend:
            candidates.append(deepcopy(dict(trend)))
    for node in _iter_mappings(raw_stages):
        if any(
            key in node
            for key in (
                "successful_runs",
                "non_success_runs",
                "workflow_outcome_classes",
                "required_check_health",
                "current_default_branch_required_check_health",
            )
        ):
            candidates.append(
                {
                    key: deepcopy(node.get(key))
                    for key in (
                        "successful_runs",
                        "non_success_runs",
                        "jobs_observed",
                        "job_success_rate",
                        "deployments_observed",
                        "successful_deployments",
                        "non_success_deployments",
                        "workflow_outcome_classes",
                        "historical_genuine_failure_rate",
                        "required_check_health",
                        "assessed_commit_required_check_health",
                        "current_default_branch_required_check_health",
                    )
                    if node.get(key) not in (None, "", [], {})
                }
            )
    merged: dict[str, Any] = {}
    for candidate in sorted(candidates, key=lambda item: len(item), reverse=True):
        for key, value in candidate.items():
            if key not in merged and value not in (None, "", [], {}):
                merged[key] = deepcopy(value)
    if merged:
        merged.update(
            {
                "classification": "mutable_operational_trend",
                "technical_score_effect": "none",
                "configuration_maturity_scored_separately": True,
                "required_check_health_reported_separately": True,
            }
        )
    return merged


def restore_decision_content(
    canonical: Mapping[str, Any],
    *,
    raw_stages: Mapping[str, Any],
    assessment: Mapping[str, Any],
    commit_sha: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Restore retained decision content without reintroducing duplicate report pages.

    Structured decision-grade findings are preferred. Exact-SHA production complexity
    hotspots are converted to review-required canonical findings only when the prior
    stage package did not retain a structured register. Scanner candidates remain a
    separate assurance-only population and are never promoted to confirmed defects.
    """

    output = deepcopy(dict(canonical))
    updated_assessment = deepcopy(dict(assessment))
    structured = _structured_findings(raw_stages, updated_assessment)
    hotspots = _complexity_hotspots(raw_stages)
    synthesized = [] if structured else _synthesized_complexity_findings(hotspots, commit_sha)
    findings = structured or synthesized
    review_summary = _review_candidate_summary(raw_stages)
    review_register = _review_candidate_register(raw_stages)
    ci_context = _ci_operational_context(raw_stages, updated_assessment)

    for surface in (
        "canonical_findings",
        "findings_register",
        "decision_grade_findings_register",
    ):
        output[surface] = deepcopy(findings)
    output["executive_risk_register"] = deepcopy(findings[:7])
    output["priority_findings"] = deepcopy(findings[:5])
    output["architecture_hotspots"] = deepcopy(hotspots)
    output["review_candidate_summary"] = deepcopy(review_summary)
    output["review_candidate_register"] = deepcopy(review_register)
    output["ci_operational_context"] = deepcopy(ci_context)
    output["decision_grade_finding_count"] = len(findings)
    output["exact_source_finding_count"] = sum(
        bool(_text(item.get("location") or item.get("exact_source"))) for item in findings
    )
    output["review_required_candidate_count"] = review_summary.get("review_required_total", 0)

    updated_assessment["findings_register"] = deepcopy(findings)
    updated_assessment["decision_grade_findings_register"] = deepcopy(findings)
    updated_assessment["executive_risk_register"] = deepcopy(findings[:7])
    updated_assessment["priority_findings"] = deepcopy(findings[:5])
    updated_assessment["architecture_hotspots"] = deepcopy(hotspots)
    updated_assessment["review_candidate_summary"] = deepcopy(review_summary)
    updated_assessment["review_candidate_register"] = deepcopy(review_register)
    updated_assessment["ci_operational_context"] = deepcopy(ci_context)
    updated_assessment["decision_grade_finding_count"] = len(findings)
    updated_assessment["review_required_candidate_count"] = review_summary.get(
        "review_required_total", 0
    )

    limitations: list[str] = []
    if review_summary.get("review_required_total", 0) and not review_register:
        limitations.append(
            "Review-required candidate counts were retained, but raw candidate payloads were not "
            "embedded in the final-stage package; exact candidate disposition must use the retained scanner artifacts."
        )
    if synthesized:
        limitations.append(
            "The prior structured risk register was unavailable, so exact-SHA production complexity "
            "hotspots were restored as review-required canonical findings without claiming human approval."
        )
    output["decision_content_limitations"] = limitations
    updated_assessment["decision_content_limitations"] = deepcopy(limitations)

    manifest = {
        "version": VERSION,
        "structured_finding_count_recovered": len(structured),
        "complexity_hotspot_count_retained": len(hotspots),
        "complexity_finding_count_synthesized": len(synthesized),
        "canonical_finding_count": len(findings),
        "review_required_candidate_count": review_summary.get("review_required_total", 0),
        "review_candidate_record_count_retained": len(review_register),
        "ci_operational_context_retained": bool(ci_context),
        "duplicate_full_page_finding_render_not_requested": True,
        "confirmed_defects_not_inferred_from_review_candidates": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output["decision_content_restoration"] = deepcopy(manifest)
    updated_assessment["decision_content_restoration"] = deepcopy(manifest)
    output["assessment"] = updated_assessment
    return output, updated_assessment, manifest


__all__ = [
    "VERSION",
    "restore_decision_content",
]
