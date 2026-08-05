from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-final-two-report-truth.v1"
_OLD_COVER_COPY = "independently evidence-adjusted"
_NEW_COVER_COPY = "separately calculated evidence-adjusted"
_STAGE_MARKER = "__nico_final_two_report_stage_truth_v1__"
_COVER_MARKER = "__nico_final_two_report_cover_truth_v1__"
_APPLY_MARKER = "__nico_final_two_report_cover_apply_v1__"
_VALIDATE_MARKER = "__nico_final_two_report_validation_v1__"

_DEPLOYMENTS_OBSERVED = re.compile(
    r"^\s*deployments[ _-]+observed\s*:\s*(\d+)\.?\s*$", re.IGNORECASE
)
_SUCCESSFUL_DEPLOYMENTS = re.compile(
    r"^\s*successful[ _-]+deployments\s*:\s*(\d+)\.?\s*$", re.IGNORECASE
)
_DEPLOYMENT_RATIO = re.compile(
    r"^\s*deployments\s*:\s*(\d+)\s+successful\s+of\s+(\d+)\s+observed\b.*$",
    re.IGNORECASE,
)
_NUMERIC_NON_SUCCESS = re.compile(
    r"^\s*non[ _-]*success(?:ful)?[ _-]+deployments"
    r"(?:[ _-]+classification)?\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_UNAVAILABLE_CLASSIFICATION = re.compile(
    r"^\s*non[ _-]*success[ _-]+deployment(?:s)?[ _-]+classification\s*:\s*"
    r"(?:not[ _-]+available|unavailable)\.?\s*$",
    re.IGNORECASE,
)
_UNRESOLVED_DEPLOYMENTS = re.compile(
    r"^\s*non[ _-]*success[ _-]+or[ _-]+unresolved[ _-]+deployment"
    r"[ _-]+observations\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_CLASSIFICATION_BREAKDOWN = re.compile(
    r"^\s*outcome[ _-]+classification[ _-]+breakdown\s*:\s*"
    r"(?:not[ _-]+available|unavailable)\.?\s*$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _deployment_population(lines: list[str]) -> tuple[int | None, int | None]:
    observed: int | None = None
    successful: int | None = None
    for line in lines:
        ratio = _DEPLOYMENT_RATIO.match(line)
        if ratio:
            successful = int(ratio.group(1))
            observed = int(ratio.group(2))
            continue
        match = _DEPLOYMENTS_OBSERVED.match(line)
        if match:
            observed = int(match.group(1))
            continue
        match = _SUCCESSFUL_DEPLOYMENTS.match(line)
        if match:
            successful = int(match.group(1))
    return observed, successful


def repair_deployment_population(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Repair only client-facing deployment arithmetic, without changing source evidence.

    A numeric non-success count is retained only when it reconciles exactly with the
    observed population. When the retained taxonomy accounts for fewer observations
    than ``observed - successful``, the client surface reports the complete arithmetic
    remainder as non-success *or unresolved* and keeps the unavailable classification
    boundary explicit. This does not infer that unresolved observations are failures.
    """

    result = deepcopy(dict(stage))
    raw = result.get("evidence")
    if not isinstance(raw, list):
        return result
    lines = [_text(item) for item in raw if _text(item)]
    observed, successful = _deployment_population(lines)
    if observed is None or successful is None or successful > observed:
        result["evidence"] = lines
        return result

    remainder = observed - successful
    numeric_values: list[int] = []
    unresolved_values: list[int] = []
    target_indexes: list[int] = []
    unavailable = False
    breakdown = False
    for index, line in enumerate(lines):
        numeric = _NUMERIC_NON_SUCCESS.match(line)
        unresolved = _UNRESOLVED_DEPLOYMENTS.match(line)
        if numeric:
            numeric_values.append(int(numeric.group(1)))
            target_indexes.append(index)
        elif _UNAVAILABLE_CLASSIFICATION.match(line):
            unavailable = True
            target_indexes.append(index)
        elif unresolved:
            unresolved_values.append(int(unresolved.group(1)))
            target_indexes.append(index)
        elif _CLASSIFICATION_BREAKDOWN.match(line):
            breakdown = True
            target_indexes.append(index)

    numeric_complete = bool(numeric_values) and all(
        value == remainder for value in numeric_values
    )
    unresolved_complete = bool(unresolved_values) and all(
        value == remainder for value in unresolved_values
    )
    needs_bounded_remainder = (
        unavailable
        or breakdown
        or bool(unresolved_values)
        or (bool(numeric_values) and not numeric_complete)
    )
    if not needs_bounded_remainder:
        result["evidence"] = lines
        return result
    if unresolved_complete and breakdown and not numeric_values and not unavailable:
        result["evidence"] = lines
        return result

    insertion = min(target_indexes) if target_indexes else len(lines)
    cleaned = [
        line
        for index, line in enumerate(lines)
        if index not in set(target_indexes)
    ]
    desired = [
        f"Non-success or unresolved deployment observations: {remainder}.",
        "Outcome classification breakdown: Not available.",
    ]
    cleaned[insertion:insertion] = desired
    result["evidence"] = cleaned
    return result


def _assert_deployment_surface(text: str) -> None:
    lines = [_text(line) for line in str(text or "").splitlines() if _text(line)]
    observed, successful = _deployment_population(lines)
    if observed is None or successful is None:
        return
    if successful > observed:
        raise ValueError("client report deployment successes exceed observations")
    remainder = observed - successful
    numeric = [
        int(match.group(1))
        for line in lines
        if (match := _NUMERIC_NON_SUCCESS.match(line))
    ]
    unresolved = [
        int(match.group(1))
        for line in lines
        if (match := _UNRESOLVED_DEPLOYMENTS.match(line))
    ]
    breakdown = any(_CLASSIFICATION_BREAKDOWN.match(line) for line in lines)
    unavailable = any(_UNAVAILABLE_CLASSIFICATION.match(line) for line in lines)
    if numeric and any(value != remainder for value in numeric):
        raise ValueError(
            "client report deployment classification does not reconcile with the observed population"
        )
    if unresolved and any(value != remainder for value in unresolved):
        raise ValueError("client report retained an incorrect deployment remainder")
    if breakdown and not unresolved:
        raise ValueError(
            "client report marked deployment classification unavailable without the arithmetic remainder"
        )
    if unavailable:
        raise ValueError(
            "client report retained an unavailable deployment classification without bounded remainder wording"
        )


def assert_final_two_report_truth(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    from pypdf import PdfReader

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    combined = "\n".join((str(markdown or ""), str(rendered_html or ""), extracted))
    if _OLD_COVER_COPY in combined.casefold():
        raise ValueError("client report retained overstated independent-adjustment language")
    for surface in (markdown, rendered_html, extracted):
        _assert_deployment_surface(str(surface or ""))


def install_final_two_report_truth_v1() -> dict[str, Any]:
    """Install the last two report corrections at late production seams."""

    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import v2_dark_branded_cover as cover

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
            return repair_deployment_population(_current(stage))

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
            return (
                repair_deployment_population(stage)
                if isinstance(stage, Mapping)
                else None
            )

        setattr(operational_stage, _STAGE_MARKER, True)
        setattr(operational_stage, "_nico_previous", current_operational)
        cleanup.build_ci_operational_stage = operational_stage

    current_cover = cover._cover
    if not getattr(current_cover, _COVER_MARKER, False):
        @wraps(current_cover)
        def corrected_cover(
            canonical: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> bytes:
            posture = cover._executive_posture

            @wraps(posture)
            def corrected_posture(*args: Any, **kwargs: Any) -> str:
                return str(posture(*args, **kwargs)).replace(
                    _OLD_COVER_COPY,
                    _NEW_COVER_COPY,
                )

            cover._executive_posture = corrected_posture
            try:
                pdf = current_cover(canonical, spanish=spanish)
            finally:
                cover._executive_posture = posture
            if not spanish:
                from pypdf import PdfReader

                text = "\n".join(
                    page.extract_text() or ""
                    for page in PdfReader(io.BytesIO(pdf)).pages[:1]
                ).casefold()
                if _OLD_COVER_COPY in text or _NEW_COVER_COPY not in text:
                    raise ValueError("dark branded cover did not use bounded evidence-adjustment language")
            return pdf

        setattr(corrected_cover, _COVER_MARKER, True)
        setattr(corrected_cover, "_nico_previous", current_cover)
        cover._cover = corrected_cover

    current_apply = cover.apply_dark_branded_cover
    if not getattr(current_apply, _APPLY_MARKER, False):
        @wraps(current_apply)
        def apply_cover(package: Mapping[str, Any]) -> dict[str, Any]:
            result = current_apply(package)
            canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
            language = _text(
                canonical.get("report_language") or canonical.get("locale")
            ).casefold()
            if not language.startswith("es"):
                pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
                from pypdf import PdfReader

                text = "\n".join(
                    page.extract_text() or ""
                    for page in PdfReader(io.BytesIO(pdf)).pages[:1]
                ).casefold()
                if _OLD_COVER_COPY in text or _NEW_COVER_COPY not in text:
                    raise ValueError("final branded cover retained overstated adjustment language")
            return result

        setattr(apply_cover, _APPLY_MARKER, True)
        setattr(apply_cover, "_nico_previous", current_apply)
        cover.apply_dark_branded_cover = apply_cover

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
            assert_final_two_report_truth(canonical, markdown, rendered_html, pdf)

        setattr(validate, _VALIDATE_MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        cleanup.assert_human_review_package_cleanup = validate

    return {
        "status": "installed",
        "version": VERSION,
        "bounded_cover_copy_bound": getattr(cover._cover, _COVER_MARKER, False),
        "final_cover_validation_bound": getattr(
            cover.apply_dark_branded_cover, _APPLY_MARKER, False
        ),
        "deployment_population_truth_bound": getattr(
            cleanup.sanitize_rendered_stage, _STAGE_MARKER, False
        ),
        "final_validation_bound": getattr(
            cleanup.assert_human_review_package_cleanup, _VALIDATE_MARKER, False
        ),
        "scores_unchanged": True,
        "scanner_candidates_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "canonical_source_values_unchanged": True,
        "unresolved_deployments_not_called_failures": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_final_two_report_truth",
    "install_final_two_report_truth_v1",
    "repair_deployment_population",
]
