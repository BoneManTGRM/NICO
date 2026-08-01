from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from fastapi import FastAPI

from nico import comprehensive_assessment_hardening_v1 as hardening
from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v2 as v2
from nico import comprehensive_native_providers_v3 as v3
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive-native-providers.v4"

_DEPENDENCY_TOOLS = ("pip-audit", "npm-audit", "osv-scanner")
_STATIC_TOOLS = ("bandit", "semgrep", "eslint", "typescript")
_SECRET_TOOLS = ("gitleaks", "trufflehog")
_ALL_TOOLS = (*_DEPENDENCY_TOOLS, *_STATIC_TOOLS, *_SECRET_TOOLS)
_COMPLETE_STATUSES = {
    "complete",
    "completed",
    "completed_with_findings",
    "success",
    "succeeded",
}
_SCORE_MISMATCH_REASONS = {
    "canonical_score_truth_mismatch",
    "score_truth_mismatch",
    "canonical_score_mismatch",
    "canonical_evidence_adjusted_score_mismatch",
    "evidence_adjusted_score_mismatch",
    "canonical_assurance_score_mismatch",
}
_PATH_RE = re.compile(r"([A-Za-z0-9_.\-/]+\.(?:py|tsx?|jsx?|mjs|cjs|json|ya?ml|toml))")
_COMPLEXITY_TITLE_RE = re.compile(
    r"reduce\s+complexity\s+in\s+`?([A-Za-z_][A-Za-z0-9_]*)`?",
    re.IGNORECASE,
)


def _bounded(value: float | int) -> int:
    return max(0, min(100, int(round(value))))


def _tool_results(scan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    values = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    output: dict[str, dict[str, Any]] = {}
    for raw in values:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("scanner_name") or raw.get("tool") or raw.get("scanner") or "").strip().casefold()
        if name:
            output[name] = raw
    return output


def _summary_by_tool(scan: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    by_tool = summary.get("by_tool") if isinstance(summary.get("by_tool"), dict) else {}
    output: dict[str, dict[str, int]] = {}
    for name, raw in by_tool.items():
        if not isinstance(raw, dict):
            continue
        output[str(name).casefold()] = {
            key: int(raw.get(key) or 0)
            for key in (
                "raw",
                "material",
                "review_required",
                "approved_or_nonblocking",
                "excluded_test_only",
            )
        }
    return output


def _group_counts(scan: Mapping[str, Any], tools: tuple[str, ...]) -> dict[str, int]:
    by_tool = _summary_by_tool(scan)
    results = _tool_results(scan)
    counts = {
        key: 0
        for key in (
            "raw",
            "material",
            "review_required",
            "approved_or_nonblocking",
            "excluded_test_only",
        )
    }
    for tool in tools:
        raw = by_tool.get(tool, {})
        for key in counts:
            counts[key] += int(raw.get(key) or 0)
        result = results.get(tool, {})
        counts["approved_or_nonblocking"] += int(result.get("verified_example_placeholder_count") or 0)
    return counts


def _tool_complete(record: Mapping[str, Any] | None) -> bool:
    if not isinstance(record, Mapping):
        return False
    status = str(record.get("status") or "").strip().casefold()
    return bool(
        status in _COMPLETE_STATUSES
        and record.get("completed") is not False
        and record.get("verified") is True
        and record.get("exact_commit_match") is True
        and record.get("raw_artifact_retention_complete") is True
    )


def _incomplete_tools(scan: Mapping[str, Any], tools: tuple[str, ...]) -> list[str]:
    results = _tool_results(scan)
    return [tool for tool in tools if not _tool_complete(results.get(tool))]


def _scanner_section(
    section_id: str,
    label: str,
    scan: Mapping[str, Any],
    tools: tuple[str, ...],
    *,
    summary: str,
    material_weight: int,
    material_cap: int,
) -> dict[str, Any]:
    counts = _group_counts(scan, tools)
    incomplete = _incomplete_tools(scan, tools)
    material_penalty = min(material_cap, counts["material"] * material_weight)
    execution_penalty = min(32, len(incomplete) * 8)
    score = _bounded(96 - material_penalty - execution_penalty)
    findings: list[str] = []
    assurance: list[str] = []
    if counts["material"]:
        findings.append(f"{counts['material']} verified material finding(s) require disposition.")
    if counts["review_required"]:
        assurance.append(
            f"{counts['review_required']} unverified candidate(s) remain review-required; candidate volume affects assurance only and is not scored as confirmed defect volume."
        )
    if incomplete:
        assurance.append(f"Incomplete applicable analyzers: {', '.join(incomplete)}.")
    evidence = [
        f"Applicable analyzers: {', '.join(tools)}.",
        f"Raw candidates: {counts['raw']}.",
        f"Verified material: {counts['material']}.",
        f"Review required: {counts['review_required']}.",
        f"Approved/nonblocking: {counts['approved_or_nonblocking']}.",
        f"Excluded non-production/test-only: {counts['excluded_test_only']}.",
        "Technical-score impact is limited to verified material findings and incomplete applicable analyzer execution.",
    ]
    section = legacy._section(section_id, label, score, summary, evidence, findings, assurance)
    section["score_contract"] = {
        "version": VERSION,
        "verified_material_findings_affect_technical_score": True,
        "unverified_candidate_volume_affects_technical_score": False,
        "unverified_candidate_volume_affects_assurance_only": True,
        "completed_with_findings_is_complete_execution": True,
        "material_count": counts["material"],
        "review_required_count": counts["review_required"],
        "incomplete_analyzers": incomplete,
    }
    return section


def _section_map(assessment: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): deepcopy(item)
        for item in assessment.get("sections") or []
        if isinstance(item, dict) and item.get("id")
    }


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    baseline = v3.canonical_scoring_provider(context)
    if baseline.get("status") != "complete":
        return baseline

    assessment = deepcopy(dict(baseline.get("assessment") or {}))
    sections = _section_map(assessment)
    repo = legacy._repo(context)
    scan = legacy._scan(context)
    dependency_evidence = (
        repo.get("dependency_evidence")
        if isinstance(repo.get("dependency_evidence"), dict)
        else {}
    )

    dependency = _scanner_section(
        "dependency_health",
        "Dependency / Library Ecosystem",
        scan,
        _DEPENDENCY_TOOLS,
        summary=(
            "Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability."
        ),
        material_weight=18,
        material_cap=72,
    )
    if not dependency_evidence.get("lockfile_paths"):
        dependency["findings"].append("No lockfile evidence was retained in the captured snapshot.")
        dependency["score"] = dependency["source_score"] = dependency["presented_score"] = max(
            0, int(dependency["presented_score"]) - 10
        )

    secrets = _scanner_section(
        "secrets_review",
        "Secrets Exposure Review",
        scan,
        _SECRET_TOOLS,
        summary=(
            "History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations."
        ),
        material_weight=25,
        material_cap=75,
    )
    static = _scanner_section(
        "static_analysis",
        "Static Analysis",
        scan,
        _STATIC_TOOLS,
        summary=(
            "Bandit, Semgrep, ESLint, and TypeScript evidence were evaluated independently against the exact immutable commit."
        ),
        material_weight=16,
        material_cap=64,
    )

    sections["dependency_health"] = dependency
    sections["secrets_review"] = secrets
    sections["static_analysis"] = static
    ordered_ids = [
        "code_audit",
        "dependency_health",
        "secrets_review",
        "static_analysis",
        "ci_cd",
        "architecture_debt",
        "velocity_complexity",
    ]
    updated_sections = [sections[item_id] for item_id in ordered_ids if item_id in sections]
    for item_id, item in sections.items():
        if item_id not in ordered_ids:
            updated_sections.append(item)
    assessment["sections"] = updated_sections

    scored = [
        int(item.get("presented_score"))
        for item in updated_sections
        if isinstance(item.get("presented_score"), int)
        and item.get("exclude_from_maturity") is not True
    ]
    technical_score = round(sum(scored) / len(scored)) if scored else 0
    incomplete = _incomplete_tools(scan, _ALL_TOOLS)
    category_counts = {
        "dependency": _group_counts(scan, _DEPENDENCY_TOOLS),
        "secret": _group_counts(scan, _SECRET_TOOLS),
        "static": _group_counts(scan, _STATIC_TOOLS),
    }
    review_categories = [
        category
        for category, counts in category_counts.items()
        if counts["review_required"] > 0
    ]
    analyzer_coverage = round(100 * (len(_ALL_TOOLS) - len(incomplete)) / len(_ALL_TOOLS))
    assurance_penalty = min(14, len(review_categories) + len(incomplete) * 4)
    evidence_adjusted = max(0, min(technical_score, technical_score - assurance_penalty))
    level = "Senior" if technical_score >= 82 else "Mid" if technical_score >= 58 else "Junior"

    coverage = deepcopy(dict(assessment.get("evidence_coverage") or {}))
    coverage.update(
        {
            "calculated": True,
            "percent": analyzer_coverage,
            "label": "Exact-SHA analyzer execution coverage",
            "incomplete_analyzers": incomplete,
            "review_candidate_categories": review_categories,
            "review_candidate_category_count": len(review_categories),
            "review_candidate_score_effect": "assurance_only",
        }
    )
    assessment["evidence_coverage"] = coverage
    assessment["technical_score"] = technical_score
    assessment["canonical_technical_score"] = technical_score
    assessment["canonical_evidence_adjusted_score"] = evidence_adjusted
    assessment["evidence_adjusted_score"] = evidence_adjusted
    assessment["maturity_signal"] = {
        **dict(assessment.get("maturity_signal") or {}),
        "level": level,
        "score": technical_score,
        "source_score": technical_score,
        "presented_score": technical_score,
        "technical_score": technical_score,
        "canonical_evidence_adjusted_score": evidence_adjusted,
        "evidence_adjusted_score": evidence_adjusted,
        "evidence_readiness_score": evidence_adjusted,
    }
    score_contract = deepcopy(dict(assessment.get("score_contract") or {}))
    score_contract.update(
        {
            "version": VERSION,
            "technical_score": technical_score,
            "evidence_adjusted_score": evidence_adjusted,
            "same_sha_score_deterministic": True,
            "target_score_not_used_as_input": True,
            "score_override_allowed": False,
            "unverified_candidate_volume_affects_technical_score": False,
            "unverified_candidate_volume_affects_assurance_only": True,
            "completed_with_findings_is_complete_execution": True,
            "analyzer_execution_coverage": analyzer_coverage,
            "incomplete_analyzers": incomplete,
            "review_candidate_categories": review_categories,
            "assurance_penalty": assurance_penalty,
        }
    )
    assessment["score_contract"] = score_contract
    assessment["executive_summary"] = (
        f"Exact-SHA technical evidence for {context['repository']} produced an evidence-bound {level} maturity signal "
        f"({technical_score}/100) and evidence-adjusted readiness of {evidence_adjusted}/100. "
        "Only verified material findings and incomplete applicable analyzers affect technical scores; unverified candidate volume affects assurance only."
    )

    result = deepcopy(baseline)
    result["assessment"] = assessment
    evidence = deepcopy(dict(result.get("evidence") or {}))
    evidence.update(
        {
            "maturity_level": level,
            "technical_score": technical_score,
            "canonical_technical_score": technical_score,
            "evidence_adjusted_score": evidence_adjusted,
            "canonical_evidence_adjusted_score": evidence_adjusted,
            "same_sha_score_deterministic": True,
            "analyzer_execution_coverage": analyzer_coverage,
            "incomplete_analyzers": incomplete,
            "review_candidate_categories": review_categories,
            "unverified_candidate_score_effect": "assurance_only",
        }
    )
    result["evidence"] = evidence
    result["summary"] = (
        "Canonical scoring completed from immutable technical evidence with verified-material technical scoring, "
        "assurance-only review candidates, completed-with-findings execution truth, and synchronized score aliases."
    )
    return result


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_path(item: Mapping[str, Any]) -> str:
    for key in ("exact_source", "location", "source", "path", "source_path"):
        match = _PATH_RE.search(_text(item.get(key)))
        if match:
            return match.group(1).casefold()
    return ""


def _function_name(item: Mapping[str, Any]) -> str:
    for key in (
        "function_or_component",
        "function",
        "function_name",
        "component",
        "symbol",
        "region_name",
    ):
        value = _text(item.get(key)).strip("` ")
        if value:
            return value.casefold()
    match = _COMPLEXITY_TITLE_RE.search(_text(item.get("title")))
    return match.group(1).casefold() if match else ""


def _finding_identity(item: Mapping[str, Any]) -> tuple[str, ...]:
    category = _text(item.get("category")).casefold()
    title = _text(item.get("title")).casefold()
    path = _source_path(item)
    function = _function_name(item)
    rule = _text(
        item.get("rule_id")
        or item.get("advisory_id")
        or item.get("analyzer_rule")
        or item.get("rule")
    ).casefold()
    evidence = _text(item.get("evidence") or item.get("fact")).casefold()
    complexity = "complexity" in title or "cyclomatic_complexity" in evidence or "complexity_hotspot" in rule
    if complexity and path and function:
        return ("complexity", path, function)
    if rule and path:
        return (category or "finding", path, rule, function)
    finding_id = _text(item.get("finding_id") or item.get("id"))
    return ("id", finding_id.casefold()) if finding_id else ("record", hashlib.sha256(json.dumps(dict(item), sort_keys=True, default=str).encode()).hexdigest())


def _record_richness(item: Mapping[str, Any]) -> tuple[int, int, int]:
    location = _text(item.get("exact_source") or item.get("location"))
    has_span = int(bool(re.search(r":\d+[-:]\d+", location)))
    source_context = int(bool(item.get("bounded_source_excerpt") or item.get("source_excerpt")))
    return (has_span, source_context, len(json.dumps(dict(item), sort_keys=True, default=str)))


def deduplicate_finding_register(assessment: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(assessment))
    keys = [
        key
        for key in ("decision_grade_findings_register", "findings_register")
        if isinstance(output.get(key), list)
    ]
    if not keys:
        return output
    source_key = keys[0]
    records = [deepcopy(item) for item in output.get(source_key) or [] if isinstance(item, Mapping)]
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    order: list[tuple[str, ...]] = []
    for item in records:
        identity = _finding_identity(item)
        if identity not in grouped:
            order.append(identity)
            grouped[identity] = []
        grouped[identity].append(item)

    deduped: list[dict[str, Any]] = []
    removed = 0
    for identity in order:
        candidates = grouped[identity]
        preferred = deepcopy(max(candidates, key=_record_richness))
        identifiers: list[str] = []
        for candidate in candidates:
            values = [candidate.get("finding_id"), candidate.get("id")]
            values.extend(candidate.get("source_finding_ids") or [])
            values.extend(candidate.get("finding_aliases") or [])
            for value in values:
                normalized = _text(value)
                if normalized and normalized not in identifiers:
                    identifiers.append(normalized)
        if len(candidates) > 1:
            removed += len(candidates) - 1
            preferred["source_finding_ids"] = identifiers
            preferred["finding_aliases"] = [
                value
                for value in identifiers
                if value not in {_text(preferred.get("finding_id")), _text(preferred.get("id"))}
            ]
            preferred["duplicate_source_records_reconciled"] = len(candidates) - 1
            preferred["canonical_identity"] = "|".join(identity)
        deduped.append(preferred)

    output["findings_register"] = deepcopy(deduped)
    if "decision_grade_findings_register" in output:
        output["decision_grade_findings_register"] = deepcopy(deduped)
    output["finding_deduplication_summary"] = {
        "version": VERSION,
        "input_record_count": len(records),
        "canonical_record_count": len(deduped),
        "duplicate_record_count_removed": removed,
        "source_aliases_preserved": True,
        "deduplication_affects_score": False,
    }
    return output


_BASE_COMPRESS = hardening.compress_review_candidates
_BASE_SCORE_REPAIR = hardening._repair_stale_report_contracts_hardened


def compress_review_candidates(assessment: Mapping[str, Any]) -> dict[str, Any]:
    return deduplicate_finding_register(_BASE_COMPRESS(assessment))


def _iter_mappings(value: Any, depth: int = 0):
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_mappings(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child, depth + 1)


def _authoritative_scores(canonical: Mapping[str, Any]) -> tuple[int, int] | None:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else canonical
    if not isinstance(assessment, Mapping):
        return None
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical_raw = assessment.get("technical_score", maturity.get("technical_score", maturity.get("score")))
    adjusted_raw = assessment.get(
        "canonical_evidence_adjusted_score",
        assessment.get("evidence_adjusted_score", maturity.get("evidence_adjusted_score")),
    )
    if not isinstance(technical_raw, (int, float)) or isinstance(technical_raw, bool):
        return None
    technical = _bounded(technical_raw)
    adjusted = technical if not isinstance(adjusted_raw, (int, float)) or isinstance(adjusted_raw, bool) else _bounded(adjusted_raw)
    if adjusted > technical:
        return None
    section_scores = [
        int(item.get("presented_score"))
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
        and isinstance(item.get("presented_score"), int)
        and item.get("exclude_from_maturity") is not True
    ]
    if section_scores and round(sum(section_scores) / len(section_scores)) != technical:
        return None
    return technical, adjusted


def _sync_score_container(container: dict[str, Any], technical: int, adjusted: int) -> int:
    touched = 0
    score_keys = {
        "technical_score": technical,
        "canonical_technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "canonical_evidence_adjusted_score": adjusted,
    }
    looks_like_score_container = bool(
        set(container) & set(score_keys)
        or isinstance(container.get("maturity_signal"), Mapping)
        or isinstance(container.get("score_contract"), Mapping)
    )
    if not looks_like_score_container:
        return 0
    for key, value in score_keys.items():
        if key in container or key in {"technical_score", "canonical_evidence_adjusted_score"}:
            if container.get(key) != value:
                touched += 1
            container[key] = value
    maturity = container.get("maturity_signal")
    if isinstance(maturity, dict):
        for key in ("score", "source_score", "presented_score", "technical_score"):
            if maturity.get(key) != technical:
                touched += 1
            maturity[key] = technical
        for key in ("evidence_adjusted_score", "canonical_evidence_adjusted_score", "evidence_readiness_score"):
            if maturity.get(key) != adjusted:
                touched += 1
            maturity[key] = adjusted
    contract = container.get("score_contract")
    if isinstance(contract, dict):
        if contract.get("technical_score") != technical:
            touched += 1
        if contract.get("evidence_adjusted_score") != adjusted:
            touched += 1
        contract["technical_score"] = technical
        contract["evidence_adjusted_score"] = adjusted
    return touched


def repair_score_truth(canonical: dict[str, Any]) -> int:
    scores = _authoritative_scores(canonical)
    if scores is None:
        return _BASE_SCORE_REPAIR(canonical)
    technical, adjusted = scores
    touched = sum(_sync_score_container(item, technical, adjusted) for item in _iter_mappings(canonical))
    repaired = _BASE_SCORE_REPAIR(canonical)
    consistency = getattr(hardening, "_score_consistency", None)
    consistent = True
    if callable(consistency):
        consistent, _ = consistency(canonical)
    if not consistent:
        return repaired
    for item in _iter_mappings(canonical):
        status = _text(item.get("report_contract_status")).casefold()
        reason = _text(item.get("report_contract_reason")).casefold()
        if status == "blocked" and reason in _SCORE_MISMATCH_REASONS:
            item["pre_reconciliation_report_contract"] = {
                "status": item.get("report_contract_status"),
                "reason": item.get("report_contract_reason"),
            }
            item["report_contract_status"] = "reconciled"
            item["report_contract_reason"] = "canonical_score_truth_reconciled_after_section_and_alias_equality_verification"
            item["report_contract_reconciled"] = True
            item["report_contract_reconciliation_version"] = VERSION
            repaired += 1
    canonical["score_alias_synchronization"] = {
        "version": VERSION,
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "aliases_updated": touched,
        "section_average_verified": True,
        "publication_block_removed_only_after_consistency": True,
    }
    return repaired


hardening.compress_review_candidates = compress_review_candidates
hardening._repair_stale_report_contracts_hardened = repair_score_truth


def native_comprehensive_providers() -> dict[str, legacy.Provider]:
    providers = v3.native_comprehensive_providers()
    providers["canonical_scoring"] = canonical_scoring_provider
    return providers


def install_native_comprehensive_providers(app: FastAPI) -> dict[str, legacy.Provider]:
    v3.install_native_comprehensive_providers(app)
    existing = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(existing) if isinstance(existing, dict) else {}
    providers.update(native_comprehensive_providers())
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    status = dict(getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {})
    status.update(
        {
            "artifact_schema": VERSION,
            "category_specific_scoring_bound": providers.get("canonical_scoring") is canonical_scoring_provider,
            "verified_material_only_technical_scoring": True,
            "review_candidate_volume_affects_technical_score": False,
            "completed_with_findings_is_complete_execution": True,
            "canonical_finding_deduplication_bound": True,
            "score_alias_synchronization_bound": True,
            "evidence_adjusted_mismatch_reconciliation_bound": True,
            "target_score_not_used_as_input": True,
            "score_override_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    app.state.nico_native_comprehensive_provider_status = status
    return providers


__all__ = [
    "VERSION",
    "canonical_scoring_provider",
    "compress_review_candidates",
    "deduplicate_finding_register",
    "install_native_comprehensive_providers",
    "native_comprehensive_providers",
    "repair_score_truth",
]
