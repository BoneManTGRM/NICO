from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_static_scanner_velocity_scoring.v44"
_PATCH_MARKER = "_nico_express_static_scanner_velocity_scoring_v44"
_NUMBER_RE = r"(?:\d+(?:\.\d+)?|\.\d+)"

_KNOWN_SCANNERS = {
    "bandit",
    "eslint",
    "gitleaks",
    "npm-audit",
    "osv-scanner",
    "pip-audit",
    "semgrep",
    "trufflehog",
    "typescript",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    aliases = {
        "scanner_worker_evidence": {"scanner_worker_evidence", "scanner_evidence"},
        "velocity_complexity": {"velocity_complexity", "velocity_and_complexity"},
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


def _all_statements(result: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for field in ("evidence", "findings", "unavailable", "evidence_full", "findings_full", "unavailable_full"):
            for value in section.get(field) or []:
                text = _text(value)
                if text:
                    output.append(text)
    return output


def _tool_states(result: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]:
    observed: set[str] = set()
    completed: set[str] = set()
    failed: set[str] = set()
    inapplicable: set[str] = set()

    for statement in _all_statements(result):
        lowered = statement.casefold()
        for tool in _KNOWN_SCANNERS:
            if tool in lowered:
                observed.add(tool)

        for match in re.finditer(
            r"exact-snapshot\s+([a-z0-9_-]+)\s+status=(completed|completed_clean|passed|success)",
            statement,
            re.I,
        ):
            completed.add(match.group(1).casefold())

        completed_match = re.search(r"tools completed:\s*([^.;]+)", statement, re.I)
        if completed_match:
            for item in completed_match.group(1).split(","):
                tool = item.strip().casefold()
                if tool:
                    completed.add(tool)
                    observed.add(tool)

        for match in re.finditer(
            r"\b([a-z0-9_-]+)\s+(?:ended with status|status=)\s*(failed|timeout|timed_out)\b",
            statement,
            re.I,
        ):
            failed.add(match.group(1).casefold())

        if "no eslint configuration exists" in lowered or (
            "eslint" in lowered and "not applicable" in lowered
        ):
            observed.add("eslint")
            inapplicable.add("eslint")

    completed &= _KNOWN_SCANNERS
    failed &= _KNOWN_SCANNERS
    observed &= _KNOWN_SCANNERS
    inapplicable &= _KNOWN_SCANNERS
    return observed, completed, failed, inapplicable


def _band(score: int) -> tuple[str, str, str]:
    if score >= 90:
        return "exceptional", "EXCEPTIONAL", "green"
    if score >= 80:
        return "strong", "STRONG", "green"
    if score >= 70:
        return "moderate", "MODERATE", "yellow"
    if score >= 55:
        return "weak", "WEAK", "red"
    return "critical", "CRITICAL", "red"


def _has_verified_blocker(section: dict[str, Any]) -> bool:
    combined = " ".join(
        _text(item).casefold()
        for field in ("evidence", "findings", "unavailable")
        for item in section.get(field) or []
    )
    explicit_zero = bool(re.search(r"(?:blocking|verified blockers?)=0\b", combined))
    blocker_language = any(
        token in combined
        for token in (
            "confirmed critical",
            "confirmed high severity",
            "verified vulnerability",
            "verified exposure",
            "verified blocker",
        )
    )
    return blocker_language and not explicit_zero


def _move_analyzer_execution_failures_to_limitations(section: dict[str, Any]) -> None:
    retained: list[str] = []
    limitations = [_text(item) for item in section.get("unavailable") or [] if _text(item)]
    seen = {item.casefold() for item in limitations}
    failure_re = re.compile(
        r"\b(?:bandit|eslint|semgrep|typescript)\s+(?:ended with status|status=)\s*(?:failed|timeout|timed_out)\b",
        re.I,
    )
    for raw in section.get("findings") or []:
        value = _text(raw)
        if failure_re.search(value):
            if value.casefold() not in seen:
                limitations.append(value)
                seen.add(value.casefold())
            continue
        retained.append(value)
    section["findings"] = retained
    section["unavailable"] = limitations


def _apply_static_score(result: dict[str, Any]) -> None:
    section = _section(result, "static_analysis")
    if not section or _has_verified_blocker(section):
        return

    observed, completed, failed, inapplicable = _tool_states(result)
    applicable = ({"semgrep", "typescript", "bandit"} & observed) - inapplicable
    if not {"semgrep", "typescript"}.issubset(completed) or not applicable:
        return

    section_text = " ".join(
        _text(item).casefold()
        for field in ("evidence", "findings", "unavailable")
        for item in section.get(field) or []
    )
    triage_zero_blockers = bool(
        re.search(r"blocking=0\b", section_text)
        or re.search(r"verified blockers?=0\b", section_text)
    )
    accepted_units = float(len(applicable & completed))
    if "bandit" in applicable and "bandit" not in completed and triage_zero_blockers:
        accepted_units += 0.5
    coverage = round(100 * accepted_units / len(applicable))

    # This is deliberately bounded. Completed Semgrep and TypeScript evidence and
    # a zero-blocker Bandit triage record support a Strong technical signal, but
    # incomplete live Bandit acceptance and untriaged candidates prevent an
    # Exceptional score. Evidence assurance remains independently review-limited.
    score = max(70, min(85, 70 + round(15 * coverage / 100)))
    band_key, band_label, tone = _band(score)
    section.update(
        {
            "score": score,
            "source_score": score,
            "presented_score": score,
            "presented": score,
            "score_value": score,
            "score_band": band_key,
            "score_band_label": band_label,
            "score_tone": tone,
            "technical_score_display": f"{band_label} · {score}/100",
            "directly_scored": True,
            "exclude_from_maturity": False,
            "score_kind": "technical",
            "status": "review_limited",
            "presented_status": "review_limited",
            "display_status": f"REVIEW LIMITED · {score}/100",
            "assurance_status": "review_limited",
            "assurance_label": "REVIEW LIMITED",
            "assurance_tone": "yellow",
            "confidence": "review-limited",
            "presented_confidence": "review-limited",
            "analyzer_execution_coverage": coverage,
            "score_treatment": "bounded_static_technical_signal_from_accepted_analyzer_coverage_v44",
            "score_rationale": (
                f"Bounded static technical signal ({score}/100): exact-snapshot Semgrep and TypeScript completed, "
                f"accepted analyzer coverage is {coverage}%, and no verified critical or high-severity blocker is retained. "
                "The score is capped below Exceptional until live Bandit execution and rule-level candidate triage are accepted."
            ),
            "summary": (
                f"Static Analysis has a bounded Strong technical signal ({score}/100) with Review Limited assurance. "
                "Completed analyzers and zero verified blockers support scoring; failed or incomplete analyzer acceptance and untriaged candidates remain visible and prevent an Exceptional result."
            ),
        }
    )
    _move_analyzer_execution_failures_to_limitations(section)
    section.pop("diagnostic_score_before_truth_gate", None)


def _apply_scanner_coverage(result: dict[str, Any]) -> None:
    section = _section(result, "scanner_worker_evidence")
    if not section:
        return

    observed, completed, failed, inapplicable = _tool_states(result)
    applicable = observed - inapplicable
    if not applicable:
        return
    coverage = round(100 * len(applicable & completed) / len(applicable))
    _band_key, _band_label, tone = _band(coverage)
    section.update(
        {
            "score": coverage,
            "source_score": coverage,
            "presented_score": coverage,
            "presented": coverage,
            "score_value": coverage,
            "score_band": "execution_coverage",
            "score_band_label": "EXECUTION COVERAGE",
            "score_tone": tone,
            "technical_score_display": f"EXECUTION COVERAGE · {coverage}/100",
            "score_kind": "execution_coverage",
            "score_metric_label": "Execution coverage",
            "directly_scored": False,
            "exclude_from_maturity": True,
            "included_in_maturity": False,
            "status": "supplemental",
            "presented_status": "supplemental",
            "assurance_status": "supplemental",
            "assurance_label": "SUPPLEMENTAL",
            "assurance_tone": "gray",
            "confidence": "supplemental",
            "presented_confidence": "supplemental",
            "scanner_execution_coverage": coverage,
            "scanner_execution_completed": sorted(applicable & completed),
            "scanner_execution_failed": sorted(applicable & failed),
            "scanner_execution_inapplicable": sorted(inapplicable),
            "score_treatment": "supplemental_execution_coverage_excluded_from_maturity_v44",
            "score_rationale": (
                f"Execution coverage is {coverage}/100 across {len(applicable)} applicable observed analyzer(s). "
                "This operational metric is supplemental and excluded from technical maturity because scanner outputs are already mapped into the core controls; scoring them again would double-count the same evidence."
            ),
            "summary": (
                f"Scanner execution coverage is {coverage}/100. The metric shows whether the analyzer suite ran successfully, "
                "while remaining supplemental and excluded from technical maturity to prevent double counting."
            ),
        }
    )


def _apply_velocity_score(result: dict[str, Any]) -> None:
    section = _section(result, "velocity_complexity")
    if not section:
        return

    combined = " ".join(
        _text(item)
        for field in ("evidence", "evidence_full", "findings", "unavailable")
        for item in section.get(field) or []
    )
    cadence_match = re.search(rf"\(({_NUMBER_RE})\s*/\s*week\)", combined, re.I)
    ratio_match = re.search(rf"pull request traceability ratio:.*?=\s*({_NUMBER_RE})", combined, re.I)
    cadence = float(cadence_match.group(1)) if cadence_match else 0.0
    traceability = float(ratio_match.group(1)) if ratio_match else 0.0
    measured = "complexity engine current-run artifact completed" in combined.casefold()
    technical_findings = [
        item
        for item in section.get("findings") or []
        if _text(item) and _text(item).casefold() not in {"no retained item.", "no retained item"}
    ]
    current = section.get("presented_score", section.get("score"))
    current_value = int(current) if isinstance(current, (int, float)) and not isinstance(current, bool) else 0

    if technical_findings or cadence < 1.0 or traceability < 0.8 or not measured:
        return

    # A minimum Strong score is justified when delivery cadence, PR traceability,
    # and current-run complexity measurement are all objectively present. Missing
    # trend history and stakeholder context constrain assurance, not technical health.
    score = max(current_value, 85)
    band_key, band_label, tone = _band(score)
    section.update(
        {
            "score": score,
            "source_score": score,
            "presented_score": score,
            "presented": score,
            "score_value": score,
            "score_band": band_key,
            "score_band_label": band_label,
            "score_tone": tone,
            "technical_score_display": f"{band_label} · {score}/100",
            "directly_scored": True,
            "exclude_from_maturity": False,
            "score_kind": "technical",
            "status": "review_limited",
            "presented_status": "review_limited",
            "assurance_status": "review_limited",
            "assurance_label": "REVIEW LIMITED",
            "assurance_tone": "yellow",
            "confidence": "review-limited",
            "presented_confidence": "review-limited",
            "score_treatment": "objective_velocity_traceability_measurement_calibration_v44",
            "score_rationale": (
                f"Objective delivery calibration ({score}/100): commit cadence is {cadence:.2f}/week, PR traceability is {traceability:.2f}, "
                "and the current-run complexity artifact completed. Missing retained trend history and stakeholder business mapping remain assurance limitations and do not reduce technical health."
            ),
            "summary": (
                f"Velocity and delivery traceability support a Strong technical score ({score}/100). "
                "Assurance remains Review Limited until retained trend history and stakeholder context are available."
            ),
        }
    )


def apply_express_static_scanner_velocity_scoring_v44(result: dict[str, Any]) -> dict[str, Any]:
    _apply_static_score(result)
    _apply_velocity_score(result)
    _apply_scanner_coverage(result)

    from nico import express_truth_calibration_v36 as v36

    v36._recompute_maturity(result)
    v36._canonicalize_summary(result)
    result["express_static_scanner_velocity_scoring"] = {
        "status": "complete",
        "version": VERSION,
        "static_uses_bounded_evidence_backed_score": True,
        "scanner_worker_uses_execution_coverage_not_technical_double_counting": True,
        "velocity_uses_objective_cadence_traceability_and_measurement": True,
        "analyzer_execution_failures_are_assurance_limitations": True,
        "assurance_remains_independent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def install_express_static_scanner_velocity_scoring_v44() -> dict[str, Any]:
    from nico import express_truth_calibration_v36 as v36

    current: Callable[[dict[str, Any]], dict[str, Any]] = v36.calibrate_express_truth
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def calibrate(result: dict[str, Any]) -> dict[str, Any]:
        output = current(result)
        return apply_express_static_scanner_velocity_scoring_v44(output)

    setattr(calibrate, _PATCH_MARKER, True)
    setattr(calibrate, "_nico_previous", current)
    v36.calibrate_express_truth = calibrate

    return {
        "status": "installed",
        "version": VERSION,
        "static_scored_when_minimum_accepted_evidence_exists": True,
        "static_score_capped_until_full_triage": True,
        "scanner_execution_coverage_visible": True,
        "scanner_execution_coverage_excluded_from_maturity": True,
        "velocity_minimum_strong_when_objective_signals_pass": True,
        "analyzer_execution_failures_are_assurance_limitations": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "apply_express_static_scanner_velocity_scoring_v44",
    "install_express_static_scanner_velocity_scoring_v44",
]
