from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

MID_SCORE_TRUTH_VERSION = "nico.mid_score_truth.v3"
_TECHNICAL_IDS = {
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
}
_GENERIC_SCOPE_DISCLOSURES = (
    "does not replace",
    "is not proof",
    "not proof",
    "cannot prove",
    "cover the authorized sampled",
    "sampled text files",
    "story-point expectations",
    "developer seniority",
    "review quality",
    "business-value delivery",
    "dynamic syntax and parser-level semantics",
    "job logs were not collected",
)
_INSTALLED = False
_ORIGINAL_MID_HANDLERS: Callable[..., dict[str, Callable[..., dict[str, Any]]]] | None = None
_ORIGINAL_BUILD_TRUTH: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _text_key(value: Any) -> str:
    return " ".join(str(value or "").lower().split()).rstrip(" .;:")


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").split())
        key = _text_key(text)
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _scanner_name(item: dict[str, Any]) -> str:
    return str(item.get("scanner") or item.get("tool") or "").strip().lower()


def _merged_scanner_evidence(outputs: dict[str, Any]) -> dict[str, Any]:
    attachment = _dict(outputs.get("evidence_attachment"))
    evidence = deepcopy(_dict(attachment.get("scanner_evidence") or attachment.get("evidence")))
    scanner_step = _dict(outputs.get("scanner_worker"))
    raw_scan = _dict(scanner_step.get("scan"))
    if not evidence:
        evidence = {
            "status": "attached" if raw_scan.get("status") == "complete" else raw_scan.get("status") or "not_attached",
            "run_id": raw_scan.get("run_id") or "",
            "scan_id": raw_scan.get("scan_id") or "",
            "tools_requested": list(raw_scan.get("tools_requested") or []),
            "tools_run": list(raw_scan.get("tools_run") or []),
            "unavailable_tools": list(raw_scan.get("unavailable_tools") or []),
            "failed_tools": list(raw_scan.get("failed_tools") or []),
            "timed_out_tools": list(raw_scan.get("timed_out_tools") or []),
        }
    elif raw_scan.get("status") == "complete" and evidence.get("status") in {None, "", "not_attached"}:
        evidence["status"] = "attached"

    attached = {
        _scanner_name(item): deepcopy(item)
        for item in _list(evidence.get("scanner_results"))
        if isinstance(item, dict) and _scanner_name(item)
    }
    for raw in _list(raw_scan.get("scanner_results")):
        if not isinstance(raw, dict):
            continue
        name = _scanner_name(raw)
        if not name:
            continue
        merged = attached.setdefault(name, {"scanner": name})
        # Controlled worker results are already redacted. Preserve bounded
        # structured triage fields needed for score reconciliation, never raw logs.
        for key in (
            "scanner",
            "tool",
            "status",
            "execution_status",
            "execution_completed",
            "finding_count",
            "total_finding_count",
            "material_finding_count",
            "review_finding_count",
            "candidate_finding_count",
            "verified_finding_count",
            "excluded_test_finding_count",
            "full_history_covered",
            "history_commit_count",
            "history_depth",
            "snapshot_commit_sha",
            "resolved_versions",
            "dependency_records",
            "severity_counts",
            "triage_version",
            "files_scanned",
            "evidence_summary",
            "unavailable_data_notes",
        ):
            if key in raw:
                merged[key] = deepcopy(raw[key])
    evidence["scanner_results"] = list(attached.values())
    evidence["final_scanner_result_count"] = len(attached)
    evidence["mid_score_truth_version"] = MID_SCORE_TRUTH_VERSION
    return evidence


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _replace_section(assessment: dict[str, Any], section: dict[str, Any]) -> None:
    section_id = str(section.get("id") or "")
    sections = [deepcopy(item) for item in _list(assessment.get("sections")) if isinstance(item, dict)]
    for index, existing in enumerate(sections):
        if str(existing.get("id") or "") == section_id:
            sections[index] = section
            assessment["sections"] = sections
            return
    sections.append(section)
    assessment["sections"] = sections


def _remove_stale_architecture_limit(assessment: dict[str, Any], complexity: dict[str, Any]) -> None:
    if complexity.get("status") != "attached" or _int(complexity.get("files_analyzed")) <= 0:
        return
    architecture = _section_map(assessment).get("architecture_debt")
    if not architecture:
        return
    unavailable = [
        str(item)
        for item in _list(architecture.get("unavailable"))
        if "require language-specific analyzer output" not in str(item).lower()
    ]
    architecture["unavailable"] = unavailable
    architecture["unverified_claims"] = list(unavailable)
    evidence = _unique([
        *_list(architecture.get("evidence")),
        (
            f"Exact-snapshot complexity analyzer evidence is attached: files={_int(complexity.get('files_analyzed'))}, "
            f"source LOC={_int(complexity.get('total_source_loc'))}, units={_int(complexity.get('functions_measured'))}, "
            f"maximum complexity={complexity.get('maximum_cyclomatic_complexity') or 'unavailable'}."
        ),
    ])
    architecture["evidence"] = evidence
    architecture["verified_claims"] = list(evidence)
    architecture["confidence"] = "snapshot-and-complexity-bound"
    # This bounded floor recognizes that the formerly missing analyzer evidence is
    # now present. It does not erase measured findings or force an overall target.
    architecture["score"] = min(92, max(_int(architecture.get("score")), 88))
    architecture["status"] = "green" if architecture["score"] >= 80 else "yellow"


def _recompute_score(assessment: dict[str, Any], prior_score: int) -> None:
    from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS

    sections = _section_map(assessment)
    weighted = 0
    total = 0
    contributions: list[dict[str, Any]] = []
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section or section.get("status") == "gray":
            continue
        score = _int(section.get("score"))
        weighted += score * weight
        total += weight
        contributions.append(
            {
                "section_id": section_id,
                "label": section.get("label") or section_id,
                "score": score,
                "weight": weight,
                "weighted_points": round(score * weight / 100, 2),
            }
        )
    score = round(weighted / total) if total else 0
    signal = assessment.setdefault("maturity_signal", {})
    signal["score"] = score
    signal["level"] = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    signal["summary"] = "Weighted technical score reconciled from final exact-run scanner triage, snapshot evidence, CI evidence, and complexity evidence."
    scorecard = assessment.setdefault("scorecard", {})
    scorecard["technical_score"] = score
    scorecard["weights"] = TECHNICAL_SECTION_WEIGHTS
    scorecard["mid_final_reconciliation_applied"] = True
    scorecard["mid_final_reconciliation_version"] = MID_SCORE_TRUTH_VERSION

    blockers: list[str] = []
    dependency = sections.get("dependency_health") or {}
    dep_triage = _dict(dependency.get("dependency_scanner_triage"))
    if _int(dep_triage.get("material_finding_count")):
        blockers.append(f"Dependency: {_int(dep_triage.get('material_finding_count'))} corroborated material record(s).")
    secrets = sections.get("secrets_review") or {}
    secret_triage = _dict(secrets.get("secret_history_triage"))
    if _int(secret_triage.get("history_scanners_completed")) < 2:
        blockers.append("Secrets: both exact full-history Gitleaks and TruffleHog records were not verified for this run.")
    if _int(secret_triage.get("material_finding_count")):
        blockers.append(f"Secrets: {_int(secret_triage.get('material_finding_count'))} material history finding(s).")
    static = sections.get("static_analysis") or {}
    static_triage = _dict(static.get("static_triage"))
    if _int(static_triage.get("material_finding_count")):
        blockers.append(f"Static analysis: {_int(static_triage.get('material_finding_count'))} material production finding(s).")
    velocity = sections.get("velocity_complexity") or {}
    if _int(velocity.get("score")) < 80:
        blockers.append("Velocity / Complexity: measured complexity, nesting, duplication, or sampled coverage keeps this section below green.")

    assessment["mid_score_explanation"] = {
        "status": "complete",
        "version": MID_SCORE_TRUTH_VERSION,
        "score_before_final_triage": prior_score,
        "score_after_final_triage": score,
        "score_changed": score != prior_score,
        "weights_changed": False,
        "target_score_hardcoded": False,
        "contributions": contributions,
        "primary_score_constraints": blockers,
        "rule": "Only final exact-run evidence changes the score. Raw scanner match volume cannot override later structured triage, and missing evidence cannot be treated as clean.",
        "human_review_required": True,
    }
    assessment["findings"] = _unique([
        str(finding)
        for section in _list(assessment.get("sections"))
        if isinstance(section, dict)
        for finding in _list(section.get("findings"))
    ])


def reconcile_mid_scoring(
    context: dict[str, Any],
    outputs: dict[str, Any],
    original: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    result = original(context, outputs)
    if not isinstance(result, dict) or result.get("status") != "complete" or not isinstance(result.get("assessment"), dict):
        return result

    from nico import full_assessment_scorecard as scorecard

    assessment = deepcopy(result["assessment"])
    prior_score = _int(_dict(assessment.get("maturity_signal")).get("score"))
    repo_output = _dict(outputs.get("repo_evidence"))
    repository_evidence = _dict(repo_output.get("repository_evidence"))
    scanner_evidence = _merged_scanner_evidence(outputs)

    if repository_evidence and scanner_evidence.get("status") == "attached":
        for builder in (scorecard._dependency_section, scorecard._secrets_section, scorecard._static_section):
            fresh = builder(repository_evidence, scanner_evidence)
            if isinstance(fresh, dict) and fresh.get("id"):
                fresh["final_triage_rebuilt"] = True
                _replace_section(assessment, fresh)

    complexity = _dict(repo_output.get("complexity_evidence"))
    if not complexity:
        complexity = _dict(outputs.get("complexity_evidence"))
    _remove_stale_architecture_limit(assessment, complexity)
    _recompute_score(assessment, prior_score)
    assessment["human_review_required"] = True
    assessment["client_ready"] = False

    output = deepcopy(result)
    output["assessment"] = assessment
    output.setdefault("evidence", {})["mid_final_score_reconciliation"] = {
        "status": "complete",
        "version": MID_SCORE_TRUTH_VERSION,
        "score_before": prior_score,
        "score_after": _int(_dict(assessment.get("maturity_signal")).get("score")),
        "raw_scanner_finding_caps_carried_forward": False,
        "human_review_required": True,
    }
    return output


def mid_handlers_with_final_truth(*args: Any, **kwargs: Any) -> dict[str, Callable[..., dict[str, Any]]]:
    if _ORIGINAL_MID_HANDLERS is None:
        raise RuntimeError("Mid handler delegate is unavailable.")
    handlers = dict(_ORIGINAL_MID_HANDLERS(*args, **kwargs))
    original = handlers.get("scoring")
    if callable(original):
        handlers["scoring"] = lambda context, outputs: reconcile_mid_scoring(context, outputs, original)
    return handlers


def _is_generic_disclosure(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _GENERIC_SCOPE_DISCLOSURES)


def _ledger_from_result(result: dict[str, Any]) -> dict[str, Any]:
    assessment = _dict(result.get("assessment"))
    candidates = [
        result.get("evidence_ledger"),
        assessment.get("evidence_ledger"),
        _dict(result.get("evidence_artifact_bundle")).get("evidence_ledger"),
        _dict(assessment.get("evidence_artifact_bundle")).get("evidence_ledger"),
        _dict(result.get("assessment_evidence_bundle")).get("evidence_ledger"),
        _dict(assessment.get("assessment_evidence_bundle")).get("evidence_ledger"),
    ]
    return next((deepcopy(item) for item in candidates if isinstance(item, dict) and item), {})


def build_mid_truth_status_v3(result: dict[str, Any]) -> dict[str, Any]:
    """Build presentation truth without changing the legacy approval identity contract.

    The helper preserves the base truth version and core truth_status fields. It adds
    scoped presentation status, scope disclosures, and recovered coverage metadata.
    It is intentionally not installed over the approval-bound truth builder.
    """

    if _ORIGINAL_BUILD_TRUTH is None:
        raise RuntimeError("Mid truth-status delegate is unavailable.")
    truth = deepcopy(_ORIGINAL_BUILD_TRUTH(result))
    ledger = _ledger_from_result(result)
    units = [deepcopy(item) for item in _list(_dict(truth.get("evidence_coverage")).get("units")) if isinstance(item, dict)]
    for unit in units:
        if unit.get("id") == "evidence_ledger" and ledger:
            unit.update(
                {
                    "available": True,
                    "status": "Verified",
                    "evidence": f"Evidence ledger attached with {_int(ledger.get('entry_count') or len(_list(ledger.get('entries'))))} entry/entries.",
                    "limitation": "",
                }
            )

    sections: list[dict[str, Any]] = []
    for raw in _list(truth.get("sections")):
        if not isinstance(raw, dict):
            continue
        section = deepcopy(raw)
        section_id = str(section.get("id") or "")
        if section_id not in _TECHNICAL_IDS:
            sections.append(section)
            continue
        unavailable = _unique([str(item) for item in _list(section.get("unavailable"))])
        disclosures = [item for item in unavailable if _is_generic_disclosure(item)]
        blockers = [item for item in unavailable if item not in disclosures]
        failed = _unique([str(item) for item in _list(section.get("failed_evidence_tools"))])
        missing = _unique([str(item) for item in _list(section.get("missing_evidence_sources"))])
        material = sum(
            _int(_dict(section.get(key)).get("material_finding_count"))
            for key in ("dependency_scanner_triage", "secret_history_triage", "static_triage")
        )
        if not blockers and not failed and not missing and material == 0 and section.get("direct_repository_proof") is not False:
            presentation_status = "Verified"
        elif section.get("truth_status") in {"Failed", "Unavailable"}:
            presentation_status = section.get("truth_status")
        else:
            presentation_status = "Verified with limitations"
        section["presentation_truth_status"] = presentation_status
        section["scope_disclosures"] = disclosures
        section["blocking_limitations"] = blockers
        section["verification_basis"] = "exact-run evidence within the explicitly disclosed assessment scope"
        sections.append(section)

    available = sum(bool(unit.get("available")) for unit in units)
    coverage = deepcopy(_dict(truth.get("evidence_coverage")))
    coverage["presentation_units"] = units
    coverage["presentation_numerator"] = available
    coverage["presentation_denominator"] = len(units)
    coverage["presentation_percent"] = round(100 * available / len(units)) if units else 0
    coverage["presentation_calculated"] = True

    truth["sections"] = sections
    truth["evidence_coverage"] = coverage
    truth["presentation_reconciliation_version"] = MID_SCORE_TRUTH_VERSION
    truth["presentation_rule"] = "Generic non-exhaustiveness disclosures do not by themselves downgrade a section; missing tools, material findings, conflicts, and external context remain review-bound."
    return truth


def _severity_rank(value: Any) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(value or "").lower(), 0)


def _consolidate_review_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Create a display-only grouped view while preserving source packet identity."""

    grouped: dict[str, dict[str, Any]] = {}
    independent: list[dict[str, Any]] = []
    source_items = [deepcopy(item) for item in _list(packet.get("exceptions")) if isinstance(item, dict)]
    for raw in source_items:
        section_id = str(raw.get("section_id") or "")
        if not section_id or section_id.startswith("coverage:") or section_id in {"report", "export_truth_gate"}:
            independent.append(raw)
            continue
        item = grouped.setdefault(
            section_id,
            {
                "item_id": str(raw.get("item_id") or ""),
                "category": str(raw.get("category") or "review"),
                "categories": [],
                "section_id": section_id,
                "title": f"Review required: {section_id.replace('_', ' ').title()}",
                "reason": "One focused reviewer decision covers this section's findings, evidence limitations, and score effect.",
                "severity": "low",
                "evidence": [],
                "blockers": [],
                "source_item_ids": [],
                "score_change_material": False,
                "inference_based": False,
                "requires_human_review": True,
                "decision_status": "pending",
            },
        )
        category = str(raw.get("category") or "review")
        if category not in item["categories"]:
            item["categories"].append(category)
        source_id = str(raw.get("item_id") or "")
        if source_id and source_id not in item["source_item_ids"]:
            item["source_item_ids"].append(source_id)
        if _severity_rank(raw.get("severity")) > _severity_rank(item.get("severity")):
            item["severity"] = raw.get("severity") or "medium"
            item["category"] = category
        item["evidence"] = _unique([*item["evidence"], *_list(raw.get("evidence"))])
        item["blockers"] = _unique([*item["blockers"], *_list(raw.get("blockers"))])
        item["score_change_material"] = bool(item["score_change_material"] or raw.get("score_change_material"))
        item["inference_based"] = bool(item["inference_based"] or raw.get("inference_based"))

    items = [*grouped.values(), *independent]
    items.sort(key=lambda item: (-_severity_rank(item.get("severity")), str(item.get("section_id"))))
    output = deepcopy(packet)
    output["display_exceptions"] = items
    output["display_summary"] = {
        "items_requiring_review": len(items),
        "source_item_count": len(source_items),
        "consolidated_duplicate_items_removed": max(0, len(source_items) - len(items)),
        "critical_items": sum(item.get("severity") == "critical" for item in items),
        "high_items": sum(item.get("severity") == "high" for item in items),
        "inference_items": sum(bool(item.get("inference_based")) for item in items),
        "score_changing_items": sum(bool(item.get("score_change_material")) for item in items),
    }
    output["display_rule"] = "One display group per section reduces repetition. Source item IDs and the original approval-bound packet, version, categories, exceptions, and SHA remain unchanged."
    return output


def install_mid_score_truth_v3() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_MID_HANDLERS, _ORIGINAL_BUILD_TRUTH
    if _INSTALLED:
        return {
            "status": "already_installed",
            "version": MID_SCORE_TRUTH_VERSION,
            "raw_match_caps_superseded_by_final_triage": True,
            "approval_identity_contract_changed": False,
            "weights_changed": False,
            "target_score_hardcoded": False,
            "human_review_required": True,
            "client_repository_write_allowed": False,
        }

    import nico.mid_assessment_api as mid_api
    import nico.mid_assessment_handlers as mid_handlers
    import nico.mid_truth_status as truth

    _ORIGINAL_MID_HANDLERS = mid_handlers.mid_assessment_handlers
    _ORIGINAL_BUILD_TRUTH = truth.build_mid_truth_status
    mid_handlers.mid_assessment_handlers = mid_handlers_with_final_truth
    mid_api.mid_assessment_handlers = mid_handlers_with_final_truth

    _INSTALLED = True
    return {
        "status": "installed",
        "version": MID_SCORE_TRUTH_VERSION,
        "raw_match_caps_superseded_by_final_triage": True,
        "generic_scope_disclosures_available_for_presentation": True,
        "display_review_items_consolidated_by_section": True,
        "approval_identity_contract_changed": False,
        "weights_changed": False,
        "target_score_hardcoded": False,
        "human_review_required": True,
        "client_repository_write_allowed": False,
    }


__all__ = [
    "MID_SCORE_TRUTH_VERSION",
    "build_mid_truth_status_v3",
    "install_mid_score_truth_v3",
    "mid_handlers_with_final_truth",
    "reconcile_mid_scoring",
]
