from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-final-deployment-population-reconciliation.v1"
_STAGE_MARKER = "__nico_final_deployment_population_stage_v1__"
_BUILD_MARKER = "__nico_final_deployment_population_build_v1__"
_VALIDATE_MARKER = "__nico_final_deployment_population_validation_v1__"

_PREFIX = r"\s*(?:[-*•]\s*)?"
_DEPLOYMENTS_OBSERVED = re.compile(
    rf"^{_PREFIX}deployments[ _-]+observed\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_SUCCESSFUL_DEPLOYMENTS = re.compile(
    rf"^{_PREFIX}successful[ _-]+deployments\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_DEPLOYMENT_RATIO = re.compile(
    rf"^{_PREFIX}deployments\s*:\s*(\d+)\s+successful\s+of\s+(\d+)\s+observed\b.*$",
    re.IGNORECASE,
)
_NUMERIC_NON_SUCCESS = re.compile(
    rf"^{_PREFIX}non[ _-]*success(?:ful)?[ _-]+deployment(?:s)?"
    r"(?:[ _-]+classification)?\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_UNAVAILABLE_CLASSIFICATION = re.compile(
    rf"^{_PREFIX}non[ _-]*success[ _-]+deployment(?:s)?[ _-]+classification\s*:\s*"
    r"(?:not[ _-]+available|unavailable)\.?\s*$",
    re.IGNORECASE,
)
_UNRESOLVED_DEPLOYMENTS = re.compile(
    rf"^{_PREFIX}non[ _-]*success[ _-]+or[ _-]+unresolved[ _-]+deployment"
    r"[ _-]+observations\s*:\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)
_CLASSIFICATION_BREAKDOWN = re.compile(
    rf"^{_PREFIX}outcome[ _-]+classification[ _-]+breakdown\s*:\s*"
    r"(?:not[ _-]+available|unavailable)\.?\s*$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _deployment_population(lines: list[str]) -> tuple[int | None, int | None]:
    observed: int | None = None
    successful: int | None = None
    for line in lines:
        ratio = _DEPLOYMENT_RATIO.fullmatch(line)
        if ratio:
            successful = int(ratio.group(1))
            observed = int(ratio.group(2))
            continue
        match = _DEPLOYMENTS_OBSERVED.fullmatch(line)
        if match:
            observed = int(match.group(1))
            continue
        match = _SUCCESSFUL_DEPLOYMENTS.fullmatch(line)
        if match:
            successful = int(match.group(1))
    return observed, successful


def reconcile_deployment_population(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile the complete client-facing deployment population.

    Canonical evidence is not changed. When a retained numeric non-success class does
    not equal ``observed - successful``, the client surface reports the complete
    arithmetic remainder as non-success *or unresolved* and states that the outcome
    classification breakdown is unavailable. A complete numeric class is preserved.
    """

    result = deepcopy(dict(stage))
    source = result.get("evidence")
    if not isinstance(source, list):
        return result

    lines = [_text(item) for item in source if _text(item)]
    observed, successful = _deployment_population(lines)
    if observed is None or successful is None or successful > observed:
        result["evidence"] = lines
        return result

    remainder = observed - successful
    numeric: list[int] = []
    unresolved: list[int] = []
    classification_indexes: list[int] = []
    unavailable = False
    breakdown = False

    for index, line in enumerate(lines):
        numeric_match = _NUMERIC_NON_SUCCESS.fullmatch(line)
        unresolved_match = _UNRESOLVED_DEPLOYMENTS.fullmatch(line)
        if numeric_match:
            numeric.append(int(numeric_match.group(1)))
            classification_indexes.append(index)
        elif unresolved_match:
            unresolved.append(int(unresolved_match.group(1)))
            classification_indexes.append(index)
        elif _UNAVAILABLE_CLASSIFICATION.fullmatch(line):
            unavailable = True
            classification_indexes.append(index)
        elif _CLASSIFICATION_BREAKDOWN.fullmatch(line):
            breakdown = True
            classification_indexes.append(index)

    numeric_complete = bool(numeric) and all(value == remainder for value in numeric)
    unresolved_complete = bool(unresolved) and all(
        value == remainder for value in unresolved
    )

    if numeric_complete and not unavailable and not breakdown and not unresolved:
        result["evidence"] = lines
        return result
    if unresolved_complete and breakdown and not numeric and not unavailable:
        result["evidence"] = lines
        return result

    needs_reconciliation = bool(classification_indexes) or remainder > 0
    if not needs_reconciliation:
        result["evidence"] = lines
        return result

    insertion = min(classification_indexes) if classification_indexes else len(lines)
    removed = set(classification_indexes)
    cleaned = [line for index, line in enumerate(lines) if index not in removed]
    cleaned[insertion:insertion] = [
        f"Non-success or unresolved deployment observations: {remainder}.",
        "Outcome classification breakdown: Not available.",
    ]
    result["evidence"] = cleaned
    return result


def _visible_html(value: str) -> str:
    return _text(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))))


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def assert_deployment_population_reconciled(text: str) -> None:
    """Reject an incomplete or ambiguous client-facing deployment population."""

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
        if (match := _NUMERIC_NON_SUCCESS.fullmatch(line))
    ]
    unresolved = [
        int(match.group(1))
        for line in lines
        if (match := _UNRESOLVED_DEPLOYMENTS.fullmatch(line))
    ]
    unavailable = any(
        _UNAVAILABLE_CLASSIFICATION.fullmatch(line) for line in lines
    )
    breakdown = any(_CLASSIFICATION_BREAKDOWN.fullmatch(line) for line in lines)

    if numeric:
        if any(value != remainder for value in numeric):
            raise ValueError(
                "client report deployment classification does not reconcile with the observed population"
            )
        if unavailable or breakdown or unresolved:
            raise ValueError(
                "client report mixed a complete numeric deployment class with unresolved classification wording"
            )
        return

    if not unresolved or any(value != remainder for value in unresolved):
        raise ValueError("client report omitted the arithmetic deployment remainder")
    if not breakdown or unavailable:
        raise ValueError(
            "client report omitted the bounded deployment classification boundary"
        )


def assert_final_deployment_population_reconciliation(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    del canonical
    for surface in (markdown, _visible_html(rendered_html), _pdf_text(pdf)):
        assert_deployment_population_reconciled(str(surface or ""))


def install_final_deployment_population_reconciliation_v1() -> dict[str, Any]:
    """Install reconciliation after all earlier report compatibility layers."""

    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface
    from nico import comprehensive_final_six_client_report_cleanup_v1 as final_six
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current_final_six = final_six.sanitize_client_report_stage
    if not getattr(current_final_six, _STAGE_MARKER, False):
        @wraps(current_final_six)
        def final_six_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
            return reconcile_deployment_population(current_final_six(stage))

        setattr(final_six_stage, _STAGE_MARKER, True)
        setattr(final_six_stage, "_nico_previous", current_final_six)
        final_six.sanitize_client_report_stage = final_six_stage

    for module, attribute in (
        (surface, "sanitize_client_rendered_stage"),
        (cleanup, "sanitize_rendered_stage"),
    ):
        current = getattr(module, attribute)
        if getattr(current, _STAGE_MARKER, False):
            continue

        @wraps(current)
        def stage_projection(
            stage: Mapping[str, Any],
            _current: Any = current,
        ) -> dict[str, Any]:
            return reconcile_deployment_population(_current(stage))

        setattr(stage_projection, _STAGE_MARKER, True)
        setattr(stage_projection, "_nico_previous", current)
        setattr(module, attribute, stage_projection)

    current_builder = cleanup.build_ci_operational_stage
    if not getattr(current_builder, _BUILD_MARKER, False):
        @wraps(current_builder)
        def operational_stage(
            canonical: Mapping[str, Any],
            renderer: Any,
        ) -> dict[str, Any] | None:
            stage = current_builder(canonical, renderer)
            return (
                reconcile_deployment_population(stage)
                if isinstance(stage, Mapping)
                else None
            )

        setattr(operational_stage, _BUILD_MARKER, True)
        setattr(operational_stage, "_nico_previous", current_builder)
        cleanup.build_ci_operational_stage = operational_stage

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
            assert_final_deployment_population_reconciliation(
                canonical, markdown, rendered_html, pdf
            )

        setattr(validate, _VALIDATE_MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        cleanup.assert_human_review_package_cleanup = validate

    return {
        "status": "installed",
        "version": VERSION,
        "final_six_stage_bound": getattr(
            final_six.sanitize_client_report_stage, _STAGE_MARKER, False
        ),
        "surface_stage_bound": getattr(
            surface.sanitize_client_rendered_stage, _STAGE_MARKER, False
        ),
        "cleanup_stage_bound": getattr(
            cleanup.sanitize_rendered_stage, _STAGE_MARKER, False
        ),
        "operational_builder_bound": getattr(
            cleanup.build_ci_operational_stage, _BUILD_MARKER, False
        ),
        "final_validator_bound": getattr(
            cleanup.assert_human_review_package_cleanup, _VALIDATE_MARKER, False
        ),
        "canonical_source_values_unchanged": True,
        "scores_unchanged": True,
        "scanner_candidates_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "unresolved_observations_not_called_failures": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_deployment_population_reconciled",
    "assert_final_deployment_population_reconciliation",
    "install_final_deployment_population_reconciliation_v1",
    "reconcile_deployment_population",
]
