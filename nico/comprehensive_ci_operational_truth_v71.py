from __future__ import annotations

import base64
import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-ci-operational-truth.v73"
_MARKER = "_nico_comprehensive_ci_operational_truth_v73"
_REVIEW_MARKER = "_nico_comprehensive_ci_boundary_review_v73"
_FINAL_MARKER = "_nico_comprehensive_ci_boundary_final_v73"

_CI_HEADINGS = {
    "## CI/CD Operational Readiness and Historical Health",
    "## Preparación operativa y salud histórica de CI/CD",
    "## Preparacion operativa y salud historica de CI/CD",
}
_INSERT_BEFORE_HEADINGS = {
    "## Human Review and Acceptance Gate",
    "## Puerta de revisión humana y aceptación",
    "## Puerta de revisión y aceptación humana",
    "## Puerta de revisión y entrega",
    "## Delivery Status",
    "## Estado de entrega",
}
_EN_BOUNDARY_MARKERS = (
    "A. CI/CD configuration maturity:",
    "B. Current operational readiness:",
    "C. Required-check health:",
    "D. Historical workflow outcomes",
)
_ES_BOUNDARY_MARKERS = (
    "A. Madurez de configuración de CI/CD:",
    "B. Preparación operativa actual:",
    "C. Estado de las verificaciones requeridas:",
    "D. Resultados históricos de los flujos de trabajo",
)


def _text(value: Any) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _chain_has_marker(current: Callable[..., Any], marker: str) -> bool:
    seen: set[int] = set()
    candidate: Any = current
    while callable(candidate) and id(candidate) not in seen:
        seen.add(id(candidate))
        if getattr(candidate, marker, False):
            return True
        candidate = getattr(candidate, "_nico_previous", None)
    return False


def _is_spanish(canonical: Mapping[str, Any], spanish: bool) -> bool:
    if spanish:
        return True
    identity = _mapping(canonical.get("identity"))
    assessment = _mapping(canonical.get("assessment"))
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return language.startswith("es")


def _ci_section(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = _mapping(canonical.get("assessment"))
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section_id = _text(raw.get("id") or raw.get("section_id")).casefold()
        if section_id in {
            "ci_cd",
            "ci_cd_architecture_complexity_velocity",
            "ci_cd_operational_readiness",
        }:
            return raw
    return {}


def _ci_context(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = _mapping(canonical.get("assessment"))
    section = _ci_section(canonical)
    candidates = (
        canonical.get("ci_operational_context"),
        assessment.get("ci_operational_context"),
        assessment.get("ci_cd_operational_health"),
        section.get("operational_health"),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping) and candidate:
            return dict(candidate)
    return {}


def _configuration_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    section = _ci_section(canonical)
    contract = _mapping(section.get("score_contract"))
    inputs = _mapping(contract.get("score_inputs"))
    controls = _mapping(inputs.get("configuration_controls"))
    score = section.get("presented_score", section.get("score"))
    score_label = f"{_integer(score)}/100" if isinstance(score, (int, float)) else (
        "Sin puntuación" if spanish else "Not scored"
    )
    exact = contract.get("exact_configuration_match") is True
    permissions = inputs.get("explicit_permissions_present") is True
    immutable = sum(value is True for value in controls.values())
    total = len(controls)
    if spanish:
        return (
            "A. Madurez de configuración de CI/CD: "
            f"{score_label}; coincidencia con SHA exacto={'sí' if exact else 'no'}; "
            f"permisos explícitos={'sí' if permissions else 'no'}; "
            f"controles inmutables={immutable}/{total}."
        )
    return (
        "A. CI/CD configuration maturity: "
        f"{score_label}; exact-SHA match={exact}; explicit permissions={permissions}; "
        f"immutable controls={immutable}/{total}."
    )


def _current_readiness_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    context = _ci_context(canonical)
    status = _text(
        context.get("operational_health_status")
        or context.get("ci_cd_operational_health_status")
        or context.get("current_operational_readiness")
    )
    if spanish:
        if status:
            return (
                "B. Preparación operativa actual: "
                f"{status}; requiere identidad exacta del despliegue y aceptación de producción actual."
            )
        return (
            "B. Preparación operativa actual: no establecida únicamente por la evidencia del repositorio; "
            "deben adjuntarse la identidad exacta de los despliegues frontend/backend y la aceptación de producción actual."
        )
    if status:
        return (
            "B. Current operational readiness: "
            f"{status}; exact deployment identity and current production acceptance remain required."
        )
    return (
        "B. Current operational readiness: not established by repository evidence alone; "
        "exact deployed frontend/backend commit proof and current production acceptance must be attached."
    )


def _required_check_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    context = _ci_context(canonical)
    required = context.get("required_checks") or context.get("required_check_health")
    if isinstance(required, Mapping) and required:
        values = {str(key): _text(value).casefold() for key, value in required.items()}
        green = all(value in {"success", "neutral", "skipped", "passed", "passing"} for value in values.values())
        if spanish:
            return (
                "C. Estado de las verificaciones requeridas: "
                f"{'aprobado' if green else 'requiere revisión'}; "
                f"registros exactos conservados={len(values)}."
            )
        return (
            "C. Required-check health: "
            f"{'passing' if green else 'review required'}; exact retained records={len(values)}."
        )
    if spanish:
        return (
            "C. Estado de las verificaciones requeridas: no se trata como aprobado salvo que se adjunten "
            "los registros exactos de verificaciones requeridas del commit evaluado o de liberación."
        )
    return (
        "C. Required-check health: not treated as passed unless exact required-check records "
        "for the assessed or release commit are attached."
    )


def _historical_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    section = _ci_section(canonical)
    operational = _mapping(section.get("operational_health"))
    context = _ci_context(canonical)
    if not operational:
        operational = context
    taxonomy = _mapping(operational.get("outcome_taxonomy"))
    if not taxonomy:
        taxonomy = _mapping(context.get("outcome_taxonomy"))
    success = _integer(taxonomy.get("success") or context.get("successful_workflow_runs"))
    failure = _integer(taxonomy.get("failure") or context.get("failed_workflow_runs"))
    cancelled = _integer(taxonomy.get("cancelled") or context.get("cancelled_workflow_runs"))
    skipped = _integer(taxonomy.get("skipped") or context.get("skipped_workflow_runs"))
    timed_out = _integer(taxonomy.get("timed_out") or context.get("timed_out_workflow_runs"))
    unknown = _integer(taxonomy.get("unknown") or context.get("unknown_workflow_runs"))
    observed = _integer(
        operational.get("workflow_run_count")
        or operational.get("observed_run_count")
        or context.get("workflow_run_count")
        or context.get("observed_workflow_runs")
        or context.get("workflow_runs_observed")
    )
    if spanish:
        return (
            "D. Resultados históricos de los flujos de trabajo (contexto sin puntuación): "
            f"correctas={success}, fallidas={failure}, canceladas={cancelled}, omitidas={skipped}, "
            f"agotadas_por_tiempo={timed_out}, desconocidas={unknown}, observadas={observed}."
        )
    return (
        "D. Historical workflow outcomes (unscored context): "
        f"success={success}, failure={failure}, cancelled={cancelled}, skipped={skipped}, "
        f"timed_out={timed_out}, unknown={unknown}, observed={observed}."
    )


def ci_cd_boundary_lines(canonical: Mapping[str, Any], *, spanish: bool) -> list[str]:
    spanish = _is_spanish(canonical, spanish)
    return [
        _configuration_line(canonical, spanish=spanish),
        _current_readiness_line(canonical, spanish=spanish),
        _required_check_line(canonical, spanish=spanish),
        _historical_line(canonical, spanish=spanish),
    ]


def ci_cd_boundary_markers(canonical: Mapping[str, Any], *, spanish: bool) -> tuple[str, ...]:
    return _ES_BOUNDARY_MARKERS if _is_spanish(canonical, spanish) else _EN_BOUNDARY_MARKERS


def _flatten_scalars(
    value: Mapping[str, Any],
    *,
    prefix: str = "",
    depth: int = 0,
    limit: int = 32,
) -> list[tuple[str, Any]]:
    if limit <= 0:
        return []
    output: list[tuple[str, Any]] = []
    for raw_key, raw_value in value.items():
        key = f"{prefix}.{raw_key}" if prefix else str(raw_key)
        if isinstance(raw_value, Mapping) and depth < 2:
            output.extend(
                _flatten_scalars(
                    raw_value,
                    prefix=key,
                    depth=depth + 1,
                    limit=max(0, limit - len(output)),
                )
            )
        elif isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            output.append((key, raw_value))
        if len(output) >= limit:
            break
    return output[:limit]


def ci_operational_truth_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    context = _ci_context(canonical)
    if not context and not _ci_section(canonical):
        return ""
    spanish = _is_spanish(canonical, spanish)
    heading = (
        "## Preparación operativa y salud histórica de CI/CD"
        if spanish
        else "## CI/CD Operational Readiness and Historical Health"
    )
    separation = (
        "La madurez de configuración de CI/CD es evidencia técnica inmutable del commit exacto. "
        "La preparación operativa, el estado de verificaciones y los resultados históricos son evidencia mutable y permanecen separados de esa madurez."
        if spanish
        else "CI/CD configuration maturity is immutable exact-commit technical evidence. "
        "Current readiness, required-check health, and historical outcomes are mutable evidence and remain separate from that maturity."
    )
    lines = [heading, "", separation, ""]
    lines.extend(f"- {line}" for line in ci_cd_boundary_lines(canonical, spanish=spanish))
    extras = _flatten_scalars(context)
    if extras:
        lines.extend(["", "### Contexto operativo adicional" if spanish else "### Additional operational context", ""])
        for key, value in extras[:16]:
            lines.append(f"- `{key}`: {_text(value)}")
    lines.extend(
        [
            "",
            (
                "Los resultados operativos e históricos son contexto de decisión y no cambian por sí solos la puntuación técnica inmutable."
                if spanish
                else "Operational and historical outcomes are decision context and do not by themselves change the immutable technical score."
            ),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _replace_or_insert_ci_section(markdown: str, replacement: str) -> str:
    lines = str(markdown or "").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() in _CI_HEADINGS), None)
    if start is not None:
        end = next(
            (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
            len(lines),
        )
        lines[start:end] = [*replacement.rstrip().splitlines(), ""]
        return "\n".join(lines).strip() + "\n"
    insert_at = next(
        (index for index, line in enumerate(lines) if line.strip() in _INSERT_BEFORE_HEADINGS),
        len(lines),
    )
    lines[insert_at:insert_at] = [*replacement.rstrip().splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def repair_ci_operational_markdown(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
    replacement = ci_operational_truth_markdown(canonical, spanish=spanish)
    if not replacement:
        return str(markdown or "")
    return _replace_or_insert_ci_section(str(markdown or ""), replacement)


def inject_ci_boundaries_into_review_sections(
    sections: list[dict[str, Any]],
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> list[dict[str, Any]]:
    output = deepcopy(sections)
    boundary_lines = ci_cd_boundary_lines(canonical, spanish=spanish)
    all_markers = (*_EN_BOUNDARY_MARKERS, *_ES_BOUNDARY_MARKERS)
    for section in output:
        if _text(section.get("id")) != "historical_trends_and_change_failure":
            continue
        existing = [
            _text(item)
            for item in section.get("evidence") or []
            if _text(item) and not any(_text(item).startswith(marker) for marker in all_markers)
        ]
        section["evidence"] = [*boundary_lines, *existing]
    return output


def _surface_text(value: str, *, html_source: bool = False) -> str:
    text = str(value or "")
    if html_source:
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.split())


def _pdf_text(encoded: Any) -> str:
    try:
        pdf = base64.b64decode(str(encoded or ""), validate=True)
    except Exception as exc:
        raise ValueError("client report did not retain a decodable PDF") from exc
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report did not retain a valid final PDF")
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    return _surface_text(extracted)


def validate_ci_boundary_surfaces(result: Mapping[str, Any]) -> dict[str, Any]:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    spanish = _is_spanish(canonical, False)
    markers = ci_cd_boundary_markers(canonical, spanish=spanish)
    surfaces = {
        "markdown": _surface_text(str(result.get("markdown") or "")),
        "html": _surface_text(str(result.get("html") or ""), html_source=True),
        "pdf": _pdf_text(result.get("pdf_base64")),
    }
    for surface_name, surface_text in surfaces.items():
        missing = [marker for marker in markers if _surface_text(marker) not in surface_text]
        if missing:
            raise ValueError(f"client report omitted CI/CD boundary in {surface_name}: {missing[0]}")
    return {
        "version": VERSION,
        "report_language": "es-MX" if spanish else "en",
        "four_part_ci_cd_boundary_in_markdown": True,
        "four_part_ci_cd_boundary_in_html": True,
        "four_part_ci_cd_boundary_in_pdf": True,
        "configuration_and_operational_health_separated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _install_review_boundary_bridge() -> bool:
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5

    current = v5.substantive_review_sections
    if _chain_has_marker(current, _REVIEW_MARKER):
        for module in (v2, v3, v4):
            module.review_sections = current
        return True

    @wraps(current)
    def substantive_review_sections(canonical: Mapping[str, Any], *, spanish: bool) -> list[dict[str, Any]]:
        sections = current(canonical, spanish=spanish)
        return inject_ci_boundaries_into_review_sections(sections, canonical, spanish=spanish)

    setattr(substantive_review_sections, _REVIEW_MARKER, True)
    setattr(substantive_review_sections, "_nico_previous", current)
    v5.substantive_review_sections = substantive_review_sections
    for module in (v2, v3, v4):
        module.review_sections = substantive_review_sections
    return True


def _install_final_surface_bridge() -> bool:
    from nico import client_report_completion_v2 as completion

    current = completion.finalize_client_report_package
    if _chain_has_marker(current, _FINAL_MARKER):
        return True

    @wraps(current)
    def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
        result = current(package)
        validation = validate_ci_boundary_surfaces(result)
        completion_contract = deepcopy(dict(result.get("client_report_completion") or {}))
        completion_contract.update(validation)
        result["client_report_completion"] = completion_contract
        return result

    setattr(finalize_client_report_package, _FINAL_MARKER, True)
    setattr(finalize_client_report_package, "_nico_previous", current)
    completion.finalize_client_report_package = finalize_client_report_package
    return True


def install_ci_operational_truth_v71() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection

    current: Callable[..., str] = completion.compact_client_markdown
    if not _chain_has_marker(current, _MARKER):
        @wraps(current)
        def compact_client_markdown(
            existing: str,
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> str:
            rendered = current(existing, canonical, register, spanish=spanish)
            return repair_ci_operational_markdown(rendered, canonical, spanish=spanish)

        setattr(compact_client_markdown, _MARKER, True)
        setattr(compact_client_markdown, "_nico_previous", current)
        completion.compact_client_markdown = compact_client_markdown
        projection.compact_client_markdown = compact_client_markdown
    else:
        projection.compact_client_markdown = completion.compact_client_markdown

    review_bound = _install_review_boundary_bridge()
    final_bound = _install_final_surface_bridge()
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "four_part_ci_cd_boundary": True,
        "english_and_spanish_supported": True,
        "historical_workflow_outcomes_rendered": True,
        "review_companion_boundary_bound": review_bound,
        "cross_format_boundary_validation_bound": final_bound,
        "configuration_and_operational_health_separated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "ci_cd_boundary_lines",
    "ci_cd_boundary_markers",
    "ci_operational_truth_markdown",
    "inject_ci_boundaries_into_review_sections",
    "install_ci_operational_truth_v71",
    "repair_ci_operational_markdown",
    "validate_ci_boundary_surfaces",
]
