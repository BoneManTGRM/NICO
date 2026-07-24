from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable

from nico.worker_execution import WorkerCommandResult, WorkerLimits

VERSION = "nico.comprehensive_canonical_truth.v2"
_REPORT_MARKER = "_nico_comprehensive_canonical_truth_v2"
_SCANNER_MARKER = "_nico_comprehensive_scanner_capacity_v1"

_DEFAULT_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}

_CANONICAL_STAGE_IDS = {
    "evidence_reconciliation_and_scoring",
    "executive_business_briefing",
    "canonical_scoring",
}

_PRESENTATION_KEYS = {
    "canonical_report_truth",
    "decision_summary",
    "executive_summary",
    "maturity_signal",
    "score_integrity",
    "sections",
    "mid_score_transparency",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        match = re.search(r"\b(100|[0-9]{1,2})(?:\.0+)?(?:/100)?\b", value.strip())
        if not match:
            return None
        value = match.group(1)
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def _technical_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _items(payload.get("sections"))
        if isinstance(item, dict) and str(item.get("id") or "") in _DEFAULT_WEIGHTS
    ]


def _weights(payload: dict[str, Any]) -> dict[str, int]:
    supplied = _dict(_dict(payload.get("score_integrity")).get("weights"))
    normalized: dict[str, int] = {}
    for section_id, default_weight in _DEFAULT_WEIGHTS.items():
        value = supplied.get(section_id, default_weight)
        try:
            weight = int(value)
        except (TypeError, ValueError):
            weight = default_weight
        normalized[section_id] = max(0, weight)
    return normalized


def weighted_technical_score(payload: dict[str, Any]) -> int | None:
    weights = _weights(payload)
    numerator = 0
    denominator = 0
    for section in _technical_sections(payload):
        section_id = str(section.get("id") or "")
        score = _number(section.get("score"))
        if score is None:
            continue
        weight = weights[section_id]
        numerator += score * weight
        denominator += weight
    if denominator == 0:
        return None
    return max(0, min(100, int(round(numerator / denominator))))


def canonical_technical_score(payload: dict[str, Any]) -> tuple[int | None, str]:
    integrity = _dict(payload.get("score_integrity"))
    candidates = (
        (_dict(payload.get("canonical_report_truth")).get("technical_score"), "existing canonical report truth"),
        (integrity.get("final_report_score"), "final score-integrity result"),
        (integrity.get("reported_score"), "reported immutable maturity signal"),
        (_dict(payload.get("maturity_signal")).get("score"), "immutable maturity signal"),
        (_dict(payload.get("decision_summary")).get("technical_score"), "executive decision summary"),
        (_dict(payload.get("executive_summary")).get("technical_score"), "executive summary"),
        (payload.get("technical_score"), "existing report technical score"),
    )
    for value, source in candidates:
        score = _number(value)
        if score is not None:
            return score, source
    return weighted_technical_score(payload), "normalized weighted scored technical controls"


def evidence_adjusted_score(payload: dict[str, Any]) -> int | None:
    records = _items(_dict(payload.get("mid_score_transparency")).get("records"))
    scores = [
        score
        for item in records
        if isinstance(item, dict)
        for score in [_number(item.get("presented_score"))]
        if score is not None
    ]
    if scores:
        return int(round(sum(scores) / len(scores)))
    for candidate in (
        payload.get("evidence_adjusted_score"),
        _dict(payload.get("decision_summary")).get("evidence_adjusted_score"),
        _dict(payload.get("executive_summary")).get("evidence_adjusted_score"),
    ):
        score = _number(candidate)
        if score is not None:
            return score
    return None


def _coverage_percent(payload: dict[str, Any]) -> int | None:
    coverage = _dict(payload.get("evidence_coverage"))
    return _number(coverage.get("percent"))


def technical_band(score: int | None) -> str:
    if score is None:
        return "NOT SCORED"
    if score >= 90:
        return "EXCEPTIONAL"
    if score >= 80:
        return "STRONG"
    if score >= 70:
        return "MODERATE"
    if score >= 60:
        return "DEVELOPING"
    return "CRITICAL"


def _replace_score_text(value: str, score: int, band: str) -> str:
    text = value
    text = re.sub(r"(?i)(technical score\s*[:=]\s*)\d{1,3}", rf"\g<1>{score}", text)
    text = re.sub(r"(?i)(technical band\s*[:=]\s*)(critical|developing|moderate|strong|exceptional)", rf"\g<1>{band}", text)
    text = re.sub(r"(?i)(maturity level\s*[:=]\s*)(critical|developing|moderate|mid|strong|exceptional)", rf"\g<1>{band.title()}", text)
    return text


def _normalize_nested_truth(value: Any, *, score: int, band: str, adjusted: int | None, coverage: int | None) -> None:
    if isinstance(value, list):
        for item in value:
            _normalize_nested_truth(item, score=score, band=band, adjusted=adjusted, coverage=coverage)
        return
    if not isinstance(value, dict):
        return

    stage_id = str(value.get("stage_id") or value.get("id") or value.get("capability") or "")
    canonical_stage = stage_id in _CANONICAL_STAGE_IDS

    if canonical_stage:
        previous = value.get("technical_score")
        if previous not in (None, score) and "pre_reconciliation_technical_score" not in value:
            value["pre_reconciliation_technical_score"] = previous
        value["technical_score"] = score

        previous_band = value.get("technical_band")
        if previous_band not in (None, band) and "pre_reconciliation_technical_band" not in value:
            value["pre_reconciliation_technical_band"] = previous_band
        value["technical_band"] = band

        previous_level = value.get("maturity_level")
        if previous_level not in (None, band.title()) and "pre_reconciliation_maturity_level" not in value:
            value["pre_reconciliation_maturity_level"] = previous_level
        value["maturity_level"] = band.title()

        if adjusted is not None:
            value["evidence_readiness"] = adjusted
        if coverage is not None:
            value["evidence_coverage_percent"] = coverage

    for key, item in list(value.items()):
        if key in _PRESENTATION_KEYS:
            continue
        if isinstance(item, str) and canonical_stage:
            value[key] = _replace_score_text(item, score, band)
        elif isinstance(item, (dict, list)):
            _normalize_nested_truth(item, score=score, band=band, adjusted=adjusted, coverage=coverage)


def canonicalize_comprehensive_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    score, score_source = canonical_technical_score(output)
    if score is None:
        return output

    band = technical_band(score)
    adjusted = evidence_adjusted_score(output)
    coverage = _coverage_percent(output)
    previous_truth = deepcopy(_dict(output.get("canonical_report_truth")))

    truth = {
        "version": VERSION,
        "technical_score": score,
        "technical_band": band,
        "maturity_level": band.title(),
        "evidence_adjusted_score": adjusted,
        "evidence_coverage_percent": coverage,
        "review_posture": "Required",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "score_source": score_source,
        "unscored_controls_are_excluded_not_zeroed": True,
    }
    if previous_truth and previous_truth != truth:
        truth["previous_canonical_truth"] = previous_truth
    output["canonical_report_truth"] = truth
    output["technical_score"] = score
    output["technical_band"] = band
    if adjusted is not None:
        output["evidence_adjusted_score"] = adjusted
    if coverage is not None:
        output["evidence_coverage_percent"] = coverage

    maturity = _dict(output.get("maturity_signal"))
    maturity.update({"score": score, "level": band.title(), "band": band})
    output["maturity_signal"] = maturity

    decision = _dict(output.get("decision_summary"))
    decision.update({
        "technical_score": score,
        "technical_band": band,
        "maturity_level": band.title(),
        "score_source": score_source,
        "human_context_sections_affect_score_without_review": False,
    })
    if adjusted is not None:
        decision["evidence_adjusted_score"] = adjusted
    if coverage is not None:
        decision["evidence_coverage_percent"] = coverage
    output["decision_summary"] = decision

    executive = _dict(output.get("executive_summary"))
    executive.update({
        "technical_score": f"{score}/100",
        "technical_band": band,
        "maturity_level": band.title(),
    })
    if adjusted is not None:
        executive["evidence_adjusted_score"] = adjusted
    if coverage is not None:
        executive["evidence_coverage_percent"] = coverage
    output["executive_summary"] = executive

    integrity = _dict(output.get("score_integrity"))
    previous_reported = integrity.get("final_report_score") or integrity.get("reported_score")
    integrity.update({
        "version": VERSION,
        "final_report_score": score,
        "score_match": True,
        "final_report_score_matches_canonical_source": True,
        "canonical_truth_bound": True,
        "canonical_score_source": score_source,
    })
    if previous_reported not in (None, score):
        integrity["pre_reconciliation_reported_score"] = previous_reported
    output["score_integrity"] = integrity

    _normalize_nested_truth(output, score=score, band=band, adjusted=adjusted, coverage=coverage)
    return output


def normalize_truncated_tool_record(record: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(record)
    if not output.get("output_truncated"):
        return output
    parsed_count = int(output.get("findings_count") or len(_items(output.get("findings"))))
    output["status"] = "failed"
    output["verified_for_this_report"] = False
    output["failure_or_unavailable_reason"] = "Scanner output exceeded the bounded capture limit before the complete result could be verified."
    output["reason"] = output["failure_or_unavailable_reason"]
    output["unverified_truncated_findings_count"] = parsed_count
    output["findings"] = []
    output["findings_count"] = 0
    output["guardrail"] = "Truncated analyzer output cannot be scored or represented as a complete clean or finding result."
    return output


def _is_comprehensive_payload(payload: dict[str, Any]) -> bool:
    source_identity = _dict(payload.get("source_identity"))
    candidates = (
        payload.get("run_id"),
        source_identity.get("run_id"),
        payload.get("report_type"),
        payload.get("report_path"),
        payload.get("service_id"),
        payload.get("service_tier"),
        payload.get("assessment_type"),
        payload.get("title"),
        payload.get("subtitle"),
    )
    normalized = [str(value or "").strip().lower().replace("_", "-") for value in candidates]
    return any(
        value.startswith(("comprun-", "fullrun-"))
        or "comprehensive" in value
        or "integral" in value
        for value in normalized
    )


def _install_report_truth() -> int:
    from nico import mid_report_v9_production_binding as v9

    current: Callable[[dict[str, Any]], dict[str, Any]] = v9.enrich_mid_v9
    if getattr(current, _REPORT_MARKER, False):
        return 0

    previous: Callable[[dict[str, Any]], dict[str, Any]] = getattr(current, "_nico_previous", current)

    def wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        result = previous(payload)
        if _is_comprehensive_payload(payload) or _is_comprehensive_payload(result):
            return canonicalize_comprehensive_payload(result)
        return result

    setattr(wrapped, _REPORT_MARKER, True)
    setattr(wrapped, "_nico_previous", previous)
    v9.enrich_mid_v9 = wrapped
    return 1


def _install_scanner_capacity() -> bool:
    from nico import scanner_tool_runners

    current = scanner_tool_runners.run_scanner_tool
    if getattr(current, _SCANNER_MARKER, False):
        return False

    def run_with_bounded_complete_static_output(spec: Any, workspace: Any, *, runner: Callable[..., WorkerCommandResult] = scanner_tool_runners.run_command) -> dict[str, Any]:
        if str(getattr(spec, "name", "")) != "bandit":
            return current(spec, workspace, runner=runner)

        def expanded_runner(command: Any, *, cwd: Any, limits: WorkerLimits) -> WorkerCommandResult:
            expanded = WorkerLimits(
                timeout_seconds=limits.timeout_seconds,
                max_output_chars=max(limits.max_output_chars, 2_000_000),
            )
            return runner(command, cwd=cwd, limits=expanded)

        record = current(spec, workspace, runner=expanded_runner)
        return normalize_truncated_tool_record(record) if isinstance(record, dict) else record

    setattr(run_with_bounded_complete_static_output, _SCANNER_MARKER, True)
    setattr(run_with_bounded_complete_static_output, "_nico_previous", current)
    scanner_tool_runners.run_scanner_tool = run_with_bounded_complete_static_output
    return True


def install_comprehensive_canonical_truth() -> dict[str, Any]:
    return {
        "status": "installed",
        "version": VERSION,
        "report_functions_rebound": _install_report_truth(),
        "bandit_capacity_guard_installed": _install_scanner_capacity(),
        "technical_score_source": "established immutable maturity signal, with weighted fallback",
        "truncated_scanner_output_scored": False,
    }


__all__ = [
    "VERSION",
    "canonical_technical_score",
    "canonicalize_comprehensive_payload",
    "evidence_adjusted_score",
    "install_comprehensive_canonical_truth",
    "normalize_truncated_tool_record",
    "technical_band",
    "weighted_technical_score",
]
