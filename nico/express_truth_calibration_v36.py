from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_truth_calibration.v36"
_PATCH_MARKER = "_nico_express_truth_calibration_v36"

_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}

_COMPLETED_RE = re.compile(r"exact-snapshot\s+([a-z0-9_-]+)\s+status=(completed|completed_clean|passed|success)", re.I)
_FAILED_RE = re.compile(r"\b([a-z0-9_-]+)\s+(?:ended with status|status=)\s*(failed|timeout|timed_out)\b", re.I)
_ASSURANCE_ONLY_RULES = {"ANALYZER_TIMEOUT", "ANALYZER_FAILURE", "EVIDENCE_UNAVAILABLE", "HUMAN_TRIAGE_REQUIRED"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _key(value: Any) -> str:
    return re.sub(r"\W+", " ", _text(value).casefold()).strip()


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        value = _text(raw)
        semantic = _key(value)
        if value and semantic not in seen:
            seen.add(semantic)
            output.append(value)
    return output


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    aliases = {
        "dependency_health": {"dependency_health", "dependency_library_ecosystem"},
        "ci_cd": {"ci_cd", "ci_cd_analysis"},
    }
    expected = aliases.get(section_id, {section_id})
    return next(
        (
            item
            for item in result.get("sections") or []
            if isinstance(item, dict) and _text(item.get("id")).casefold() in expected
        ),
        None,
    )


def _band(score: int | None) -> tuple[str, str, str]:
    if score is None:
        return "not_scored", "NOT SCORED", "gray"
    if score >= 90:
        return "exceptional", "EXCEPTIONAL", "green"
    if score >= 80:
        return "strong", "STRONG", "green"
    if score >= 70:
        return "moderate", "MODERATE", "yellow"
    if score >= 55:
        return "weak", "WEAK", "red"
    return "critical", "CRITICAL", "red"


def _completed_tools(section: dict[str, Any]) -> set[str]:
    return {
        match.group(1).casefold()
        for value in section.get("evidence") or []
        for match in _COMPLETED_RE.finditer(_text(value))
    }


def _failed_tools(section: dict[str, Any]) -> set[str]:
    return {
        match.group(1).casefold()
        for field in ("findings", "unavailable", "evidence")
        for value in section.get(field) or []
        for match in _FAILED_RE.finditer(_text(value))
    }


def _has_verified_blocker(section: dict[str, Any]) -> bool:
    combined = " ".join(
        _text(item).casefold()
        for field in ("findings", "evidence")
        for item in section.get(field) or []
    )
    return any(
        token in combined
        for token in (
            "verified blocker",
            "confirmed critical",
            "confirmed high severity",
            "verified vulnerability",
            "verified exposure",
        )
    )


def _clean_metric_text(value: str) -> str:
    value = re.sub(r",?\s*max_function_cyclomatic=None", "", value, flags=re.I)
    value = re.sub(r",?\s*density=None", "", value, flags=re.I)
    value = re.sub(r"\s+score=([0-9.]+)", r" hotspot_index=\1", value, flags=re.I)
    value = re.sub(r"\s+hotspot_score=([0-9.]+)", r" hotspot_index=\1", value, flags=re.I)
    value = re.sub(r"\.{2,}", ".", value)
    return _text(value).rstrip(" ,")


def _compact_section(section: dict[str, Any]) -> None:
    section_id = _text(section.get("id")).casefold()
    limits = {
        "architecture_debt": (12, 8, 4),
        "velocity_complexity": (8, 5, 3),
        "static_analysis": (8, 4, 3),
        "dependency_health": (8, 4, 3),
        "secrets_review": (8, 4, 3),
    }
    evidence_limit, finding_limit, unavailable_limit = limits.get(section_id, (12, 8, 5))

    for field, maximum in (
        ("evidence", evidence_limit),
        ("findings", finding_limit),
        ("unavailable", unavailable_limit),
    ):
        original = _unique(section.get(field))
        if not original:
            section[field] = []
            continue
        section.setdefault(f"{field}_full", deepcopy(original))
        cleaned: list[str] = []
        for raw in original:
            value = _clean_metric_text(raw)
            lowered = value.casefold()
            if section_id == "architecture_debt" and any(
                fragment in lowered
                for fragment in (
                    "repository root contains",
                    "readme.md is present",
                    "package.json indicates a separate",
                    "dependency boundary is present",
                )
            ):
                continue
            if value and _key(value) not in {_key(item) for item in cleaned}:
                cleaned.append(value)
        section[field] = cleaned[:maximum]
        section[f"{field}_visible_count"] = len(section[field])
        section[f"{field}_full_count"] = len(original)


def _canonicalize_static(section: dict[str, Any]) -> None:
    completed = _completed_tools(section)
    failed = _failed_tools(section)
    blocker = _has_verified_blocker(section)

    evidence = _unique(section.get("evidence"))
    findings = _unique(section.get("findings"))
    unavailable = _unique(section.get("unavailable"))

    # Exact-snapshot completion supersedes generic "unavailable" text. ESLint is
    # explicitly inapplicable when no ESLint configuration exists; TypeScript is
    # still evaluated independently and is never relabelled as ESLint proof.
    cleaned_unavailable: list[str] = []
    eslint_inapplicable = False
    for raw in unavailable:
        lowered = raw.casefold()
        if "semgrep" in lowered and "semgrep" in completed:
            continue
        if "typescript" in lowered and "typescript" in completed:
            continue
        if "eslint" in lowered and "no eslint configuration exists" in lowered:
            eslint_inapplicable = True
            continue
        if "accepted clean execution evidence unavailable for" in lowered:
            names = {
                item.strip().casefold()
                for item in re.split(r"[,/]", raw.split(":", 1)[-1])
                if item.strip()
            }
            unresolved = names - completed - ({"eslint"} if eslint_inapplicable else set())
            if not unresolved:
                continue
            raw = "Accepted current-run execution evidence remains unresolved for: " + ", ".join(sorted(unresolved)) + "."
        cleaned_unavailable.append(raw)

    if eslint_inapplicable:
        evidence.append(
            "ESLint is not configured for this snapshot and is treated as not applicable; TypeScript compilation remains independently evaluated."
        )

    triage_match = next(
        (
            re.search(
                r"blocking=(\d+),\s*needs_review=(\d+),\s*approved=(\d+),\s*candidate_false_positive=(\d+)",
                item,
                re.I,
            )
            for item in evidence
            if "bandit triage artifact attached" in item.casefold()
        ),
        None,
    )

    cleaned_findings: list[str] = []
    for raw in findings:
        lowered = raw.casefold()
        if any(
            phrase in lowered
            for phrase in (
                "scanner-worker static tools reported",
                "parsed bandit artifact reported",
                "bandit triage summary:",
                "semgrep returned",
                "typescript returned",
            )
        ):
            continue
        cleaned_findings.append(raw)

    candidate_total = 0
    for raw in evidence + findings:
        match = re.search(r"exact-snapshot\s+(?:semgrep|typescript)\s+status=completed;\s*findings=(\d+)", raw, re.I)
        if match:
            candidate_total += int(match.group(1))
    if candidate_total:
        cleaned_findings.append(
            f"Semgrep and TypeScript produced {candidate_total} unverified candidate(s) requiring rule, severity, and exact-location triage; candidate volume is not treated as a confirmed defect count."
        )

    if triage_match:
        blocking, needs_review, approved, false_positive = map(int, triage_match.groups())
        cleaned_findings.append(
            f"Bandit attached triage records {needs_review} candidate(s) requiring review and {false_positive} candidate false-positive(s); verified blockers={blocking}, approved={approved}."
        )

    if "bandit" in failed:
        cleaned_unavailable = [item for item in cleaned_unavailable if "bandit source distinction" not in item.casefold()]
        cleaned_unavailable.append(
            "Live Bandit execution failed for this exact snapshot; the attached triage artifact remains diagnostic until current-run execution is accepted or formally dispositioned."
        )

    section["evidence"] = _unique(evidence)
    section["findings"] = _unique(cleaned_findings)
    section["unavailable"] = _unique(cleaned_unavailable)
    section["static_tool_truth"] = {
        "completed": sorted(completed),
        "failed": sorted(failed),
        "eslint_inapplicable": eslint_inapplicable,
        "verified_blocker": blocker,
    }

    review_candidates = any("triage" in item.casefold() or "candidate" in item.casefold() for item in section["findings"])
    if not blocker and (failed or review_candidates):
        previous = section.get("presented_score", section.get("score"))
        if isinstance(previous, (int, float)):
            section["diagnostic_score_before_truth_gate"] = int(previous)
        section.update(
            {
                "score": None,
                "presented_score": None,
                "presented": None,
                "score_value": None,
                "score_band": "not_scored",
                "score_band_label": "NOT SCORED",
                "score_tone": "gray",
                "technical_score_display": "NOT SCORED",
                "directly_scored": False,
                "exclude_from_maturity": True,
                "status": "review_limited_not_scored",
                "presented_status": "review_limited_not_scored",
                "display_status": "REVIEW LIMITED · NOT SCORED",
                "assurance_status": "review_limited",
                "assurance_label": "REVIEW LIMITED",
                "assurance_tone": "yellow",
                "assurance_display": "REVIEW LIMITED",
                "confidence": "review-limited",
                "presented_confidence": "review-limited",
                "score_treatment": "not_scored_unverified_candidate_and_execution_evidence",
                "score_rationale": (
                    "Static Analysis is not scored because the retained records contain unverified candidates and incomplete current-run analyzer acceptance, but no verified critical or high-severity blocker. Candidate volume and analyzer execution reliability constrain assurance; they do not establish a 28/100 technical-health conclusion."
                ),
                "summary": (
                    "Static Analysis is review-limited and not scored. Completed Semgrep and TypeScript evidence, failed live Bandit execution, and attached triage records remain visible for human disposition without being converted into a critical technical score."
                ),
            }
        )


def _score_from_section(section: dict[str, Any]) -> int | None:
    if section.get("directly_scored") is False or section.get("exclude_from_maturity") is True:
        return None
    for key in ("presented_score", "presented", "score", "source_score"):
        raw = section.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return max(0, min(100, int(round(raw))))
    return None


def _recompute_maturity(result: dict[str, Any]) -> None:
    numerator = 0.0
    denominator = 0.0
    rows: list[dict[str, Any]] = []
    assurance_numerator = 0.0
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        weight = _WEIGHTS.get(section_id, 0.0)
        score = _score_from_section(section)
        included = score is not None and weight > 0
        assurance = _text(section.get("assurance_status") or section.get("status")).casefold()
        factor = 1.0 if assurance in {"green", "verified", "approved", "accepted"} else 0.95 if assurance in {"yellow", "review_limited", "review-limited", "review_limited_not_scored"} else 0.85
        if included:
            numerator += score * weight
            assurance_numerator += score * factor * weight
            denominator += weight
        rows.append(
            {
                "section_id": section_id,
                "label": section.get("label") or section_id,
                "weight": weight,
                "technical_score": score,
                "included": included,
                "assurance_factor": factor if included else None,
            }
        )
    technical = round(numerator / denominator) if denominator else None
    adjusted = round(assurance_numerator / denominator) if denominator else None
    band_key, band_label, _tone = _band(technical)
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    maturity.update(
        {
            "score": technical,
            "source_score": technical,
            "presented_score": adjusted,
            "level": band_label.title() if technical is not None else "Not Scored",
            "label": band_label.title() if technical is not None else "Not Scored",
            "score_band": band_key,
            "score_band_label": band_label,
            "scoring_method": "weighted_scored_controls_only_v36",
            "unscored_controls_excluded": [row["section_id"] for row in rows if row["weight"] and not row["included"]],
        }
    )
    result["maturity_signal"] = maturity
    result["technical_score"] = technical
    result["evidence_adjusted_score"] = adjusted
    result["express_weighted_scoring"] = {
        "status": "complete",
        "version": VERSION,
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "records": rows,
        "evidence_assurance_factors": {"verified": 1.0, "review_limited": 0.95, "blocked": 0.85},
        "unscored_controls_are_not_zero": True,
    }


def _canonicalize_summary(result: dict[str, Any]) -> None:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    score = maturity.get("score")
    level = maturity.get("level") or "Not Scored"
    adjusted = result.get("evidence_adjusted_score", maturity.get("presented_score"))
    repository = result.get("repository") or "the authorized repository"
    score_text = "not scored" if score is None else f"{score}/100"
    adjusted_text = "not scored" if adjusted is None else f"{adjusted}/100"
    result["executive_summary"] = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repository}. "
        f"The weighted technical maturity signal is {level} ({score_text}); the independently evidence-adjusted score is {adjusted_text}. "
        "Controls with insufficient verified evidence are excluded rather than treated as zero, and client delivery remains blocked pending exact-snapshot human review."
    )


def calibrate_express_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    for section in output.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id == "static_analysis":
            _canonicalize_static(section)
        _compact_section(section)
        score = _score_from_section(section)
        band_key, band_label, tone = _band(score)
        if score is not None:
            section.update(
                {
                    "score_value": score,
                    "score_band": band_key,
                    "score_band_label": band_label,
                    "score_tone": tone,
                    "technical_score_display": f"{band_label} · {score}/100",
                }
            )
        assurance = _text(section.get("assurance_status") or section.get("status")).casefold()
        if assurance in {"green", "verified", "approved", "accepted"}:
            section.update({"assurance_status": "verified", "assurance_label": "VERIFIED", "assurance_tone": "green", "confidence": "high", "presented_confidence": "high"})
        elif assurance in {"yellow", "review_limited", "review-limited", "review_limited_not_scored"}:
            section.update({"assurance_status": "review_limited", "assurance_label": "REVIEW LIMITED", "assurance_tone": "yellow", "confidence": "review-limited", "presented_confidence": "review-limited"})
    _recompute_maturity(output)
    _canonicalize_summary(output)
    output["express_truth_calibration"] = {
        "status": "complete",
        "version": VERSION,
        "candidate_volume_is_not_confirmed_defect_count": True,
        "evidence_constraints_do_not_reduce_technical_scores": True,
        "static_incomplete_without_verified_blocker_not_scored": True,
        "completed_analyzer_supersedes_generic_unavailable_text": True,
        "eslint_without_configuration_is_inapplicable": True,
        "client_visible_none_metrics_removed": True,
        "user_facing_mid_label_removed": True,
        "comprehensive_is_the_only_deep_service_label": True,
    }
    return output


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    result.clear()
    result.update(normalized)
    if isinstance(existing_reports, dict) and isinstance(result.get("reports"), dict):
        replacement = result["reports"]
        existing_reports.clear()
        existing_reports.update(replacement)
        result["reports"] = existing_reports


def calibrated_section_truth(result: dict[str, Any]) -> dict[str, Any]:
    from nico import express_section_status_truth_v26 as truth

    original = getattr(calibrated_section_truth, "_nico_original", truth.reconcile_section_status_truth)
    normalized = original(result)
    return calibrate_express_truth(normalized)


def calibrated_score_records(result: dict[str, Any]):
    from nico import express_evidence_specific_scoring_v33 as scoring

    calibrated = calibrate_express_truth(result)
    _apply_in_place(result, calibrated)
    records = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or section.get("directly_scored") is False or section.get("presented_score", section.get("score")) is None:
            continue
        source = section.get("source_score", section.get("score"))
        try:
            source_value = max(0, min(100, int(round(float(source)))))
        except (TypeError, ValueError):
            continue
        details = scoring._deductions(section)
        technical_details = tuple(item for item in details if item.rule_id not in _ASSURANCE_ONLY_RULES)
        assurance_details = tuple(item for item in details if item.rule_id in _ASSURANCE_ONLY_RULES)
        presented = max(0, source_value - sum(item.points for item in technical_details))
        band_key, _band_label, _tone = _band(presented)
        confidence = "review-limited" if assurance_details else "high"
        rationale_parts = [
            f"{item.rule_id} (-{item.points}): {item.reason}"
            for item in technical_details
        ]
        if assurance_details:
            rationale_parts.append(
                "Evidence assurance remains review-limited; analyzer failures, unavailable evidence, and untriaged candidates do not reduce the technical-health percentage."
            )
        rationale = "; ".join(rationale_parts) or "No technical-health deduction was triggered; evidence assurance is reported independently."
        record = scoring.EvidenceScoreRecord(
            section_id=_text(section.get("id")),
            label=_text(section.get("label") or section.get("title") or section.get("id")),
            source_score=source_value,
            presented_score=presented,
            status=band_key,
            deductions=tuple((f"{item.rule_id} — {item.reason} Evidence: {item.evidence}", item.points) for item in technical_details),
            deduction_details=technical_details,
            confidence=confidence,
            rationale=rationale,
        )
        section["source_score"] = source_value
        section["presented_score"] = presented
        section["presented"] = presented
        section["score_rationale"] = rationale
        section["score_deductions"] = scoring._deduction_payload(record)
        section["presented_confidence"] = confidence
        records.append(record)

    _recompute_maturity(result)
    result["express_score_transparency"] = {
        "version": VERSION,
        "overall_presented_score": result.get("evidence_adjusted_score"),
        "source_maturity_score": (result.get("maturity_signal") or {}).get("score"),
        "method": (
            "Technical scores retain only evidence-backed technical deductions. Analyzer execution failures, unavailable evidence, and untriaged candidates affect assurance, not technical health. Unscored controls are excluded rather than treated as zero."
        ),
        "records": [
            {
                "section_id": item.section_id,
                "label": item.label,
                "source_score": item.source_score,
                "presented_score": item.presented_score,
                "status": item.status,
                "confidence": item.confidence,
                "deductions": scoring._deduction_payload(item),
                "rationale": item.rationale,
            }
            for item in records
        ],
        "evidence_constraints_do_not_reduce_technical_score": True,
        "unscored_controls_excluded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return records, int(result.get("evidence_adjusted_score") or 0)


def install_express_truth_calibration_v36() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_report_premium_v14 as premium
    from nico import express_score_assurance_export_v1 as score_export
    from nico import express_section_status_truth_v26 as truth
    from nico.api import main as api_main

    if not hasattr(calibrated_section_truth, "_nico_original"):
        setattr(calibrated_section_truth, "_nico_original", truth.reconcile_section_status_truth)
    truth.reconcile_section_status_truth = calibrated_section_truth
    pdf_score.reconcile_section_status_truth = calibrated_section_truth
    score_export.reconcile_section_status_truth = calibrated_section_truth

    scoring.reconcile_express_scores = calibrated_score_records
    premium.reconcile_express_scores = calibrated_score_records

    current_renderer: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    renderer_status = "already_installed"
    if not getattr(current_renderer, _PATCH_MARKER, False):
        @wraps(current_renderer)
        def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
            _apply_in_place(result, calibrate_express_truth(result))
            pdf, error = current_renderer(result)
            _apply_in_place(result, calibrate_express_truth(result))
            return pdf, error

        setattr(render, _PATCH_MARKER, True)
        setattr(render, "_nico_previous", current_renderer)
        assessment_quality._build_polished_pdf_base64 = render
        renderer_status = "installed"

    current_finalize = api_main.finalize_express_result_consistency
    finalize_status = "already_installed"
    if not getattr(current_finalize, _PATCH_MARKER, False):
        @wraps(current_finalize)
        def finalize(result: dict[str, Any]) -> dict[str, Any]:
            _apply_in_place(result, calibrate_express_truth(result))
            output = current_finalize(result)
            return calibrate_express_truth(output)

        setattr(finalize, _PATCH_MARKER, True)
        setattr(finalize, "_nico_previous", current_finalize)
        api_main.finalize_express_result_consistency = finalize
        finalize_status = "installed"

    return {
        "status": "installed" if "installed" in {renderer_status, finalize_status} else "already_installed",
        "version": VERSION,
        "renderer_binding": renderer_status,
        "finalizer_binding": finalize_status,
        "static_candidate_only_result_not_scored": True,
        "evidence_assurance_separate_from_technical_score": True,
        "maturity_uses_scored_controls_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "calibrate_express_truth",
    "calibrated_score_records",
    "calibrated_section_truth",
    "install_express_truth_calibration_v36",
]
