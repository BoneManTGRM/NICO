from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

from nico.comprehensive_final_six_client_report_cleanup_v1 import (
    expose_candidate_penalty_basis,
)

VERSION = "nico.comprehensive-final-six-runtime-repair.v1"
_PREPARE_MARKER = "__nico_comprehensive_final_six_runtime_prepare_v1__"
_VALIDATE_MARKER = "__nico_comprehensive_final_six_runtime_validation_v1__"
_FINAL_SIX_VALIDATE_MARKER = "__nico_comprehensive_final_six_validation_v1__"

_RAW_JOB_RATE = re.compile(
    r"(?im)^(?:[-*]\s*)?(?:observed[ _]+)?job[ _]+success[ _]+rate\s*:\s*"
    r"(?:0(?:\.\d+)?|1(?:\.0+)?)\.?\s*$"
)


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


def _append_basis(stage: Mapping[str, Any], basis: str) -> dict[str, Any]:
    result = deepcopy(dict(stage))
    if _text(result.get("stage_id"), 120) != "evidence_reconciliation_and_scoring":
        return result
    summary = _text(result.get("summary"), 12000)
    if basis not in summary:
        result["summary"] = (summary.rstrip(" .") + ". " + basis).strip()
    evidence = [str(item) for item in result.get("evidence") or []]
    if basis not in evidence:
        evidence.append(basis)
    result["evidence"] = evidence
    return result


def project_penalty_basis_into_scoring_stage(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(result.get("json") or {}))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
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
    register = assessment.get("canonical_scanner_finding_register")
    if (
        "candidate_volume_penalty" not in contract
        or not isinstance(register, Mapping)
        or not isinstance(register.get("summary_by_category"), Mapping)
    ):
        return result

    canonical = expose_candidate_penalty_basis(canonical)
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    contract = deepcopy(dict(assessment.get("score_contract") or {}))
    basis = _text(contract.get("candidate_volume_penalty_basis"), 12000)
    if not basis:
        raise ValueError("candidate-triage workload deduction basis was not retained")

    top_stages = [
        _append_basis(stage, basis)
        for stage in canonical.get("stage_summaries") or []
        if isinstance(stage, Mapping)
    ]
    assessment_stages = [
        _append_basis(stage, basis)
        for stage in assessment.get("stage_summaries") or []
        if isinstance(stage, Mapping)
    ]
    if top_stages:
        canonical["stage_summaries"] = top_stages
        assessment["stage_summaries"] = deepcopy(top_stages)
    elif assessment_stages:
        assessment["stage_summaries"] = assessment_stages
        canonical["stage_summaries"] = deepcopy(assessment_stages)
    canonical["assessment"] = assessment
    result["json"] = canonical
    return result


def _visible_html(value: str) -> str:
    return _text(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))))


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def assert_corrected_final_six_surfaces(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    combined = "\n".join((markdown, _visible_html(rendered_html), _pdf_text(pdf)))
    lowered = combined.casefold()
    if "top_level_directories" in lowered:
        raise ValueError("client report retained the inaccurate top_level_directories label")
    if "independently evidence-adjusted readiness" in lowered:
        raise ValueError("client report retained overstated independent-adjustment language")
    if _RAW_JOB_RATE.search(combined):
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
    if (
        _integer(contract.get("candidate_volume_penalty"))
        and "candidate-triage workload deduction basis:" not in lowered
    ):
        raise ValueError("client report omitted the assurance-deduction calculation basis")

    observed_match = re.search(r"deployments observed\s*:\s*(\d+)", combined, re.IGNORECASE)
    successful_match = re.search(
        r"successful deployments\s*:\s*(\d+)", combined, re.IGNORECASE
    )
    if observed_match and successful_match:
        observed = int(observed_match.group(1))
        successful = int(successful_match.group(1))
        if successful > observed:
            raise ValueError(
                "client report retained an impossible deployment population: "
                f"successful={successful}, observed={observed}"
            )
        if "outcome classification breakdown: not available" in lowered:
            expected = (
                "non-success or unresolved deployment observations: "
                f"{observed - successful}"
            )
            if expected not in lowered:
                raise ValueError(
                    "client report omitted the arithmetic deployment remainder"
                )


def install_final_six_runtime_repair_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current_prepare = completion.prepare_client_report_package
    if not getattr(current_prepare, _PREPARE_MARKER, False):
        @wraps(current_prepare)
        def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
            return project_penalty_basis_into_scoring_stage(current_prepare(package))

        setattr(prepare, _PREPARE_MARKER, True)
        setattr(prepare, "_nico_previous", current_prepare)
        completion.prepare_client_report_package = prepare

    current_validate = cleanup.assert_human_review_package_cleanup
    if not getattr(current_validate, _VALIDATE_MARKER, False):
        prior = (
            getattr(current_validate, "_nico_previous")
            if getattr(current_validate, _FINAL_SIX_VALIDATE_MARKER, False)
            and hasattr(current_validate, "_nico_previous")
            else current_validate
        )

        @wraps(current_validate)
        def validate(
            canonical: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> None:
            prior(canonical, markdown, rendered_html, pdf)
            assert_corrected_final_six_surfaces(
                canonical, markdown, rendered_html, pdf
            )

        setattr(validate, _VALIDATE_MARKER, True)
        setattr(validate, "_nico_previous", prior)
        cleanup.assert_human_review_package_cleanup = validate

    return {
        "status": "installed",
        "version": VERSION,
        "scoring_stage_basis_projection_bound": getattr(
            completion.prepare_client_report_package, _PREPARE_MARKER, False
        ),
        "corrected_final_validation_bound": getattr(
            cleanup.assert_human_review_package_cleanup, _VALIDATE_MARKER, False
        ),
        "raw_percentage_false_positive_blocked": True,
        "impossible_deployment_population_fails_closed": True,
        "score_values_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_corrected_final_six_surfaces",
    "install_final_six_runtime_repair_v1",
    "project_penalty_basis_into_scoring_stage",
]
