from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-final-deployment-population-reconciliation.v1.1"
_STAGE_MARKER = "__nico_final_deployment_population_stage_v1__"
_BUILD_MARKER = "__nico_final_deployment_population_build_v1__"
_PREPARE_MARKER = "__nico_final_deployment_population_prepare_v1__"
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
_STAGE_CONTAINER_KEYS = (
    "stage_summaries",
    "stages",
    "sections",
    "report_sections",
    "client_sections",
    "prior_stage_results",
    "human_evidence_summary",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _surface_lines(value: str) -> list[str]:
    return [_text(line) for line in str(value or "").splitlines() if _text(line)]


def _visible_html(value: str) -> str:
    source = str(value or "")
    source = re.sub(
        r"(?i)</(?:li|p|div|tr|h[1-6]|section|article)>|<br\s*/?>",
        "\n",
        source,
    )
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


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


def _starts_deployment_population(line: str) -> bool:
    return bool(
        _DEPLOYMENTS_OBSERVED.fullmatch(line)
        or _DEPLOYMENT_RATIO.fullmatch(line)
    )


def _deployment_blocks(text: str, *, lookahead: int = 12) -> list[list[str]]:
    """Return bounded local deployment evidence blocks.

    Reports can legitimately repeat deployment evidence in a summary and a detailed
    worksheet. Each population must be reconciled independently; values from separate
    blocks must never be combined into one synthetic population.
    """

    lines = _surface_lines(text)
    starts = [
        index
        for index, line in enumerate(lines)
        if _starts_deployment_population(line)
    ]
    blocks: list[list[str]] = []
    for offset, start in enumerate(starts):
        next_start = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        end = min(next_start, start + lookahead)
        blocks.append(lines[start:end])
    return blocks


def reconcile_deployment_population(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile one client-facing deployment evidence stage.

    Source objects are not mutated. When a retained numeric non-success class does
    not equal ``observed - successful``, the client projection reports the complete
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


def _project_stage_container(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return deepcopy(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = deepcopy(dict(value))
        if isinstance(result.get("evidence"), list):
            result = reconcile_deployment_population(result)
        for key in _STAGE_CONTAINER_KEYS:
            if key in result:
                result[key] = _project_stage_container(result[key], depth=depth + 1)
        return result
    if isinstance(value, list):
        return [_project_stage_container(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(
            _project_stage_container(item, depth=depth + 1) for item in value
        )
    return deepcopy(value)


def project_deployment_population_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Project reconciled stage evidence before the legacy base PDF is rendered."""

    result = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(result.get("json") or {}))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
    for key in _STAGE_CONTAINER_KEYS:
        if key in canonical:
            canonical[key] = _project_stage_container(canonical[key])

    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    for key in _STAGE_CONTAINER_KEYS:
        if key in assessment:
            assessment[key] = _project_stage_container(assessment[key])
    if assessment:
        canonical["assessment"] = assessment

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "deployment_population_reconciliation_version": VERSION,
            "deployment_populations_reconciled_before_base_pdf": True,
            "deployment_blocks_validated_independently": True,
            "canonical_source_objects_not_mutated": True,
            "scores_unchanged": True,
            "candidate_dispositions_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    return result


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _assert_deployment_block(block: list[str]) -> None:
    observed, successful = _deployment_population(block)
    if observed is None or successful is None:
        return
    if successful > observed:
        raise ValueError("client report deployment successes exceed observations")

    remainder = observed - successful
    numeric = [
        int(match.group(1))
        for line in block
        if (match := _NUMERIC_NON_SUCCESS.fullmatch(line))
    ]
    unresolved = [
        int(match.group(1))
        for line in block
        if (match := _UNRESOLVED_DEPLOYMENTS.fullmatch(line))
    ]
    unavailable = any(
        _UNAVAILABLE_CLASSIFICATION.fullmatch(line) for line in block
    )
    breakdown = any(_CLASSIFICATION_BREAKDOWN.fullmatch(line) for line in block)

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


def assert_deployment_population_reconciled(text: str) -> None:
    """Validate each repeated deployment evidence block independently."""

    for block in _deployment_blocks(text):
        _assert_deployment_block(block)


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
    """Install projection and validation after earlier compatibility layers."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface
    from nico import comprehensive_final_six_client_report_cleanup_v1 as final_six
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current_prepare = completion.prepare_client_report_package
    if not getattr(current_prepare, _PREPARE_MARKER, False):
        @wraps(current_prepare)
        def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
            return project_deployment_population_package(current_prepare(package))

        setattr(prepare, _PREPARE_MARKER, True)
        setattr(prepare, "_nico_previous", current_prepare)
        completion.prepare_client_report_package = prepare

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
        "pre_base_pdf_projection_bound": getattr(
            completion.prepare_client_report_package, _PREPARE_MARKER, False
        ),
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
        "deployment_blocks_validated_independently": True,
        "canonical_source_objects_not_mutated": True,
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
    "project_deployment_population_package",
    "reconcile_deployment_population",
]
