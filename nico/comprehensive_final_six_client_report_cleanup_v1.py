from __future__ import annotations

import html
import io
import math
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-final-six-client-report-cleanup.v1"
_MARKER = "__nico_comprehensive_final_six_client_report_cleanup_v1__"
_STAGE_MARKER = "__nico_comprehensive_final_six_stage_cleanup_v1__"
_LABEL_MARKER = "__nico_comprehensive_final_six_label_cleanup_v1__"
_AUGMENT_MARKER = "__nico_comprehensive_final_six_assurance_explanation_v1__"
_POSTURE_MARKER = "__nico_comprehensive_final_six_cover_copy_v1__"
_VALIDATE_MARKER = "__nico_comprehensive_final_six_validation_v1__"

_STAGE_FIELDS = ("summary", "evidence", "findings", "unavailable", "limitations")
_TOP_LEVEL_KEY = re.compile(r"\btop_level_directories(?=\[|\s*:)", re.IGNORECASE)
_JOB_RATE = re.compile(
    r"^(?P<label>(?:observed[ _]+)?job[ _]+success[ _]+rate)\s*:\s*"
    r"(?P<rate>(?:0(?:\.\d+)?|1(?:\.0+)?))\.?$",
    re.IGNORECASE,
)
_DEPLOYMENTS_OBSERVED = re.compile(r"^deployments observed\s*:\s*(\d+)\.?$", re.IGNORECASE)
_SUCCESSFUL_DEPLOYMENTS = re.compile(r"^successful deployments\s*:\s*(\d+)\.?$", re.IGNORECASE)
_DEPLOYMENT_RATIO = re.compile(
    r"^deployments\s*:\s*(\d+)\s+successful\s+of\s+(\d+)\s+observed",
    re.IGNORECASE,
)
_CLASSIFICATION_UNAVAILABLE = re.compile(
    r"^non-success deployment classification\s*:\s*not available\.?$",
    re.IGNORECASE,
)
_UNRESOLVED_DEPLOYMENTS = re.compile(
    r"^non-success or unresolved deployment observations\s*:",
    re.IGNORECASE,
)

_OLD_COVER_COPY = "independently evidence-adjusted readiness"
_NEW_COVER_COPY = "separately calculated evidence-adjusted readiness"
_CLASSIFICATION_LINE = "Outcome classification breakdown: Not available."


def _text(value: Any, limit: int = 200000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _percent(rate: float) -> str:
    value = rate * 100.0
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def normalize_client_report_line(value: Any) -> Any:
    """Normalize only known client-facing presentation defects.

    Canonical source values remain unchanged. This function changes labels and
    formatting only after evidence has entered a client-facing stage projection.
    """

    if not isinstance(value, str):
        return value
    rendered = _TOP_LEVEL_KEY.sub("Top-level entries", value)
    rendered = rendered.replace(_OLD_COVER_COPY, _NEW_COVER_COPY)
    match = _JOB_RATE.fullmatch(rendered.strip())
    if match:
        rate = float(match.group("rate"))
        label = (
            "Observed job success rate"
            if match.group("label").casefold().startswith("observed")
            else "Job success rate"
        )
        return f"{label}: {_percent(rate)}."
    return rendered


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_client_report_line(value)
    if isinstance(value, Mapping):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    if isinstance(value, set):
        return {_normalize_value(item) for item in value}
    return value


def _deployment_population(lines: list[str]) -> tuple[int | None, int | None]:
    observed: int | None = None
    successful: int | None = None
    for line in lines:
        observed_match = _DEPLOYMENTS_OBSERVED.fullmatch(line.strip())
        if observed_match:
            observed = int(observed_match.group(1))
        successful_match = _SUCCESSFUL_DEPLOYMENTS.fullmatch(line.strip())
        if successful_match:
            successful = int(successful_match.group(1))
        ratio_match = _DEPLOYMENT_RATIO.match(line.strip())
        if ratio_match:
            successful = int(ratio_match.group(1))
            observed = int(ratio_match.group(2))
    return observed, successful


def _repair_deployment_population(lines: list[str]) -> list[str]:
    observed, successful = _deployment_population(lines)
    classification_unavailable = any(
        _CLASSIFICATION_UNAVAILABLE.fullmatch(line.strip()) for line in lines
    )
    if (
        not classification_unavailable
        or observed is None
        or successful is None
        or successful > observed
    ):
        return lines

    unresolved = observed - successful
    unresolved_line = (
        f"Non-success or unresolved deployment observations: {unresolved}."
    )
    output: list[str] = []
    inserted = False
    for line in lines:
        if _UNRESOLVED_DEPLOYMENTS.match(line.strip()):
            continue
        if _CLASSIFICATION_UNAVAILABLE.fullmatch(line.strip()):
            if not inserted:
                output.extend((unresolved_line, _CLASSIFICATION_LINE))
                inserted = True
            continue
        output.append(line)
    if not inserted:
        output.extend((unresolved_line, _CLASSIFICATION_LINE))
    return output


def sanitize_client_report_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Apply presentation-only cleanup to bounded client stage fields."""

    result = deepcopy(dict(stage))
    for field in _STAGE_FIELDS:
        if field in result:
            result[field] = _normalize_value(result[field])
    evidence = result.get("evidence")
    if isinstance(evidence, list):
        result["evidence"] = _repair_deployment_population(
            [str(item) for item in evidence]
        )
    return result


def _volume_band(total_review: int) -> tuple[str, int]:
    if total_review <= 0:
        return "none", 0
    increment = min(
        3,
        max(0, math.ceil(math.log10(total_review + 1)) - 2),
    )
    if total_review <= 99:
        band = "1-99"
    elif total_review <= 999:
        band = "100-999"
    elif total_review <= 9_999:
        band = "1,000-9,999"
    else:
        band = "10,000+"
    return band, increment


def expose_candidate_penalty_basis(result: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the existing assurance deduction arithmetic without changing it."""

    output = deepcopy(dict(result))
    assessment = (
        deepcopy(dict(output.get("assessment") or {}))
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    contract = (
        deepcopy(dict(assessment.get("score_contract") or {}))
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    register = (
        assessment.get("canonical_scanner_finding_register")
        if isinstance(assessment.get("canonical_scanner_finding_register"), Mapping)
        else {}
    )
    summary = (
        register.get("summary_by_category")
        if isinstance(register.get("summary_by_category"), Mapping)
        else {}
    )
    active_categories = sorted(
        str(category)
        for category, values in summary.items()
        if isinstance(values, Mapping) and _integer(values.get("review_required")) > 0
    )
    totals = register.get("totals") if isinstance(register.get("totals"), Mapping) else {}
    total_review = _integer(
        contract.get("candidate_volume_review_required_total")
        or totals.get("review_required")
    )
    penalty = _integer(contract.get("candidate_volume_penalty"))
    category_points = len(active_categories)
    band, volume_increment = _volume_band(total_review)
    uncapped = category_points + volume_increment
    cap = _integer(contract.get("candidate_volume_penalty_cap") or 6)
    expected = min(cap, uncapped)
    if penalty != expected:
        raise ValueError(
            "candidate-triage workload deduction does not match its retained model: "
            f"reported={penalty}, expected={expected}"
        )

    basis = (
        f"Candidate-triage workload deduction basis: {category_points} active review "
        f"categories x 1 point, plus {volume_increment} volume point"
        f"{'s' if volume_increment != 1 else ''} for {total_review} review-required "
        f"candidates in the {band} band; bounded total={penalty} point"
        f"{'s' if penalty != 1 else ''}."
    )
    contract.update(
        {
            "candidate_volume_active_review_categories": active_categories,
            "candidate_volume_active_category_count": category_points,
            "candidate_volume_category_points": category_points,
            "candidate_volume_band": band,
            "candidate_volume_increment": volume_increment,
            "candidate_volume_penalty_basis": basis,
            "candidate_volume_penalty_arithmetic_verified": True,
        }
    )
    assessment["score_contract"] = contract

    executive = _text(assessment.get("executive_summary"), 12000)
    if basis not in executive:
        executive = (executive.rstrip(" .") + ". " + basis).strip()
    assessment["executive_summary"] = executive
    output["assessment"] = assessment
    output["summary"] = executive

    evidence = (
        deepcopy(dict(output.get("evidence") or {}))
        if isinstance(output.get("evidence"), Mapping)
        else {}
    )
    evidence.update(
        {
            "candidate_volume_penalty_basis": basis,
            "candidate_volume_active_category_count": category_points,
            "candidate_volume_band": band,
            "candidate_volume_increment": volume_increment,
        }
    )
    output["evidence"] = evidence
    return output


def _visible_html(value: str) -> str:
    return _text(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))))


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def assert_final_six_client_report_cleanup(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    """Fail closed if any of the six corrected presentation defects returns."""

    combined = "\n".join((markdown, _visible_html(rendered_html), _pdf_text(pdf)))
    lowered = combined.casefold()
    if "top_level_directories" in lowered:
        raise ValueError("client report retained the inaccurate top_level_directories label")
    if _OLD_COVER_COPY in lowered:
        raise ValueError("client report retained overstated independent-adjustment language")
    if re.search(
        r"(?:observed[ _]+)?job[ _]+success[ _]+rate\s*:\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\.?",
        combined,
        re.IGNORECASE,
    ):
        raise ValueError("client report retained a raw decimal job success rate")

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    contract = (
        assessment.get("score_contract")
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    penalty = _integer(contract.get("candidate_volume_penalty"))
    if penalty and "candidate-triage workload deduction basis:" not in lowered:
        raise ValueError("client report omitted the assurance-deduction calculation basis")

    observed_match = re.search(r"deployments observed\s*:\s*(\d+)", combined, re.IGNORECASE)
    successful_match = re.search(
        r"successful deployments\s*:\s*(\d+)", combined, re.IGNORECASE
    )
    unavailable = "outcome classification breakdown: not available" in lowered
    if observed_match and successful_match and unavailable:
        observed = int(observed_match.group(1))
        successful = int(successful_match.group(1))
        if successful <= observed:
            required = (
                f"non-success or unresolved deployment observations: "
                f"{observed - successful}"
            )
            if required not in lowered:
                raise ValueError(
                    "client report omitted the arithmetic deployment remainder"
                )


def install_final_six_client_report_cleanup_v1() -> dict[str, Any]:
    """Install the six final report cleanups at the shared render boundary."""

    from nico import comprehensive_candidate_volume_assurance_v2 as assurance
    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import v2_dark_branded_cover as cover
    from nico.comprehensive_client_review_companion_v7 import (
        install_comprehensive_review_companion_v7,
    )

    paired_review = install_comprehensive_review_companion_v7()

    current_label = surface._label
    if not getattr(current_label, _LABEL_MARKER, False):
        @wraps(current_label)
        def label(value: Any) -> str:
            normalized = _text(value, 180).casefold().replace("-", "_").replace(" ", "_")
            if normalized == "top_level_directories":
                return "Top-level entries"
            return current_label(value)

        setattr(label, _LABEL_MARKER, True)
        setattr(label, "_nico_previous", current_label)
        surface._label = label

    current_humanize = surface.humanize_client_surface_value
    if not getattr(current_humanize, _MARKER, False):
        @wraps(current_humanize)
        def humanize(value: Any, *, item_limit: int = 700) -> str:
            return str(
                normalize_client_report_line(
                    current_humanize(value, item_limit=item_limit)
                )
            )

        setattr(humanize, _MARKER, True)
        setattr(humanize, "_nico_previous", current_humanize)
        surface.humanize_client_surface_value = humanize

    for module, attribute in (
        (surface, "sanitize_client_rendered_stage"),
        (cleanup, "sanitize_rendered_stage"),
    ):
        current_stage = getattr(module, attribute)
        if getattr(current_stage, _STAGE_MARKER, False):
            continue

        @wraps(current_stage)
        def stage_cleanup(
            stage: Mapping[str, Any],
            _current: Any = current_stage,
        ) -> dict[str, Any]:
            return sanitize_client_report_stage(_current(stage))

        setattr(stage_cleanup, _STAGE_MARKER, True)
        setattr(stage_cleanup, "_nico_previous", current_stage)
        setattr(module, attribute, stage_cleanup)

    current_operational = cleanup.build_ci_operational_stage
    if not getattr(current_operational, _STAGE_MARKER, False):
        @wraps(current_operational)
        def operational_stage(
            canonical: Mapping[str, Any],
            renderer: Any,
        ) -> dict[str, Any] | None:
            stage = current_operational(canonical, renderer)
            return sanitize_client_report_stage(stage) if isinstance(stage, Mapping) else None

        setattr(operational_stage, _STAGE_MARKER, True)
        setattr(operational_stage, "_nico_previous", current_operational)
        cleanup.build_ci_operational_stage = operational_stage

    current_augment = assurance._augment_contract
    if not getattr(current_augment, _AUGMENT_MARKER, False):
        @wraps(current_augment)
        def augment(result: dict[str, Any]) -> dict[str, Any]:
            return expose_candidate_penalty_basis(current_augment(result))

        setattr(augment, _AUGMENT_MARKER, True)
        setattr(augment, "_nico_previous", current_augment)
        assurance._augment_contract = augment

    current_posture = cover._executive_posture
    if not getattr(current_posture, _POSTURE_MARKER, False):
        @wraps(current_posture)
        def executive_posture(*args: Any, **kwargs: Any) -> str:
            return str(normalize_client_report_line(current_posture(*args, **kwargs)))

        setattr(executive_posture, _POSTURE_MARKER, True)
        setattr(executive_posture, "_nico_previous", current_posture)
        cover._executive_posture = executive_posture

    current_validate = cleanup.assert_human_review_package_cleanup
    if not getattr(current_validate, _VALIDATE_MARKER, False):
        @wraps(current_validate)
        def validate(
            canonical: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> None:
            current_validate(canonical, markdown, rendered_html, pdf)
            assert_final_six_client_report_cleanup(
                canonical, markdown, rendered_html, pdf
            )

        setattr(validate, _VALIDATE_MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        cleanup.assert_human_review_package_cleanup = validate

    return {
        "status": "installed",
        "version": VERSION,
        "top_level_entries_label_bound": getattr(surface._label, _LABEL_MARKER, False),
        "job_rate_percentage_projection_bound": getattr(
            surface.humanize_client_surface_value, _MARKER, False
        ),
        "deployment_remainder_projection_bound": getattr(
            cleanup.sanitize_rendered_stage, _STAGE_MARKER, False
        ),
        "cover_copy_bound": getattr(cover._executive_posture, _POSTURE_MARKER, False),
        "assurance_deduction_explanation_bound": getattr(
            assurance._augment_contract, _AUGMENT_MARKER, False
        ),
        "paired_review_companion": paired_review,
        "final_validation_bound": getattr(
            cleanup.assert_human_review_package_cleanup, _VALIDATE_MARKER, False
        ),
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "canonical_source_values_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_final_six_client_report_cleanup",
    "expose_candidate_penalty_basis",
    "install_final_six_client_report_cleanup_v1",
    "normalize_client_report_line",
    "sanitize_client_report_stage",
]
