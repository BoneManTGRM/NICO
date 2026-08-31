from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

from nico import comprehensive_ci_operational_truth_v71 as ci_truth

VERSION = "nico.comprehensive-ci-boundary-compat.v74"
_MARKER = "_nico_comprehensive_ci_boundary_compat_v74"
_FINAL_LINES_MARKER = "_nico_comprehensive_ci_lines_v74"
_MISSING = object()

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
_EN_LABELS = {
    "successful_workflow_runs": "Successful workflow runs",
    "non_successful_workflow_runs": "Non-success workflow runs",
    "failed_workflow_runs": "Failed workflow runs",
    "cancelled_workflow_runs": "Cancelled workflow runs",
    "canceled_workflow_runs": "Cancelled workflow runs",
    "skipped_workflow_runs": "Skipped workflow runs",
    "timed_out_workflow_runs": "Timed-out workflow runs",
    "unknown_workflow_runs": "Unknown workflow runs",
    "workflow_runs_observed": "Workflow runs observed",
    "observed_workflow_runs": "Workflow runs observed",
    "workflow_run_count": "Workflow runs observed",
    "jobs_observed": "Jobs observed",
    "observed_job_success_rate": "Observed job success rate",
    "deployments_observed": "Deployments observed",
    "successful_deployments": "Successful deployments",
    "non_successful_deployments": "Non-success deployments",
    "non_success_deployments": "Non-success deployments",
    "operational_health_score": "Operational health score",
    "ci_cd_operational_health_score": "CI/CD operational health score",
    "operational_health_status": "Operational health status",
    "ci_cd_operational_health_status": "CI/CD operational health status",
}
_ES_LABELS = {
    "successful_workflow_runs": "Ejecuciones de flujo exitosas",
    "non_successful_workflow_runs": "Ejecuciones de flujo no exitosas",
    "failed_workflow_runs": "Ejecuciones de flujo fallidas",
    "cancelled_workflow_runs": "Ejecuciones de flujo canceladas",
    "canceled_workflow_runs": "Ejecuciones de flujo canceladas",
    "skipped_workflow_runs": "Ejecuciones de flujo omitidas",
    "timed_out_workflow_runs": "Ejecuciones de flujo agotadas por tiempo",
    "unknown_workflow_runs": "Ejecuciones de flujo con estado desconocido",
    "workflow_runs_observed": "Ejecuciones de flujo observadas",
    "observed_workflow_runs": "Ejecuciones de flujo observadas",
    "workflow_run_count": "Ejecuciones de flujo observadas",
    "jobs_observed": "Trabajos observados",
    "observed_job_success_rate": "Tasa de éxito observada de trabajos",
    "deployments_observed": "Despliegues observados",
    "successful_deployments": "Despliegues exitosos",
    "non_successful_deployments": "Despliegues no exitosos",
    "non_success_deployments": "Despliegues no exitosos",
    "operational_health_score": "Puntuación de salud operativa",
    "ci_cd_operational_health_score": "Puntuación de salud operativa de CI/CD",
    "operational_health_status": "Estado de salud operativa",
    "ci_cd_operational_health_status": "Estado de salud operativa de CI/CD",
}


def _text(value: Any) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value if value is not None else 0))
    except (TypeError, ValueError):
        return 0


def _present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return _MISSING


def _count(
    primary: Mapping[str, Any],
    primary_keys: tuple[str, ...],
    fallback: Mapping[str, Any],
    fallback_keys: tuple[str, ...],
) -> int:
    value = _present(primary, *primary_keys)
    if value is _MISSING:
        value = _present(fallback, *fallback_keys)
    return _integer(0 if value is _MISSING else value)


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


def _looks_comprehensive(markdown: str, canonical: Mapping[str, Any]) -> bool:
    assessment = _mapping(canonical.get("assessment"))
    identity = _mapping(canonical.get("identity"))
    service = _text(
        canonical.get("service_id")
        or canonical.get("product")
        or canonical.get("assessment_product")
        or assessment.get("service_id")
        or assessment.get("assessment_product")
    ).casefold()
    run_id = _text(identity.get("run_id") or canonical.get("run_id")).casefold()
    rendered = str(markdown or "").casefold()
    return any(
        (
            "comprehensive" in service,
            run_id.startswith("comprun_"),
            "nico comprehensive" in rendered,
            "evaluación técnica integral nico" in rendered,
            "evaluacion tecnica integral nico" in rendered,
        )
    )


def _configuration_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    section = _ci_section(canonical)
    contract = _mapping(section.get("score_contract"))
    inputs = _mapping(contract.get("score_inputs"))
    controls = _mapping(inputs.get("configuration_controls"))
    score = section.get("presented_score", section.get("score"))
    score_label = (
        f"{_integer(score)}/100"
        if isinstance(score, (int, float)) and not isinstance(score, bool)
        else ("Sin puntuación" if spanish else "Not scored")
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
        green = all(
            value in {"success", "neutral", "skipped", "passed", "passing"}
            for value in values.values()
        )
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


def _historical_values(canonical: Mapping[str, Any]) -> dict[str, int]:
    section = _ci_section(canonical)
    operational = _mapping(section.get("operational_health"))
    context = _ci_context(canonical)
    if not operational:
        operational = context
    taxonomy = _mapping(operational.get("outcome_taxonomy"))
    if not taxonomy:
        taxonomy = _mapping(context.get("outcome_taxonomy"))

    values = {
        "success": _count(
            taxonomy,
            ("success", "successful"),
            context,
            ("successful_workflow_runs",),
        ),
        "failure": _count(
            taxonomy,
            ("failure", "failed", "non_success"),
            context,
            ("failed_workflow_runs", "non_successful_workflow_runs"),
        ),
        "cancelled": _count(
            taxonomy,
            ("cancelled", "canceled"),
            context,
            ("cancelled_workflow_runs", "canceled_workflow_runs"),
        ),
        "skipped": _count(
            taxonomy,
            ("skipped",),
            context,
            ("skipped_workflow_runs",),
        ),
        "timed_out": _count(
            taxonomy,
            ("timed_out", "timeout"),
            context,
            ("timed_out_workflow_runs",),
        ),
        "unknown": _count(
            taxonomy,
            ("unknown",),
            context,
            ("unknown_workflow_runs",),
        ),
    }
    observed = _present(operational, "workflow_run_count", "observed_run_count")
    if observed is _MISSING:
        observed = _present(
            context,
            "workflow_run_count",
            "observed_workflow_runs",
            "workflow_runs_observed",
        )
    values["observed"] = (
        sum(values.values()) if observed is _MISSING else _integer(observed)
    )
    return values


def _historical_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    values = _historical_values(canonical)
    if spanish:
        return (
            "D. Resultados históricos de los flujos de trabajo (contexto sin puntuación): "
            f"correctas={values['success']}, fallidas={values['failure']}, "
            f"canceladas={values['cancelled']}, omitidas={values['skipped']}, "
            f"agotadas_por_tiempo={values['timed_out']}, desconocidas={values['unknown']}, "
            f"observadas={values['observed']}."
        )
    return (
        "D. Historical workflow outcomes (unscored context): "
        f"success={values['success']}, failure={values['failure']}, "
        f"cancelled={values['cancelled']}, skipped={values['skipped']}, "
        f"timed_out={values['timed_out']}, unknown={values['unknown']}, "
        f"observed={values['observed']}."
    )


def ci_cd_boundary_lines(canonical: Mapping[str, Any], *, spanish: bool) -> list[str]:
    spanish = _is_spanish(canonical, spanish)
    return [
        _configuration_line(canonical, spanish=spanish),
        _current_readiness_line(canonical, spanish=spanish),
        _required_check_line(canonical, spanish=spanish),
        _historical_line(canonical, spanish=spanish),
    ]


def ci_cd_boundary_markers(
    canonical: Mapping[str, Any], *, spanish: bool
) -> tuple[str, ...]:
    return _ES_BOUNDARY_MARKERS if _is_spanish(canonical, spanish) else _EN_BOUNDARY_MARKERS


def _flatten_scalars(
    value: Mapping[str, Any],
    *,
    prefix: str = "",
    depth: int = 0,
    limit: int = 32,
) -> list[tuple[str, Any]]:
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
        elif isinstance(raw_value, (list, tuple)):
            scalars = [
                _text(item)
                for item in raw_value
                if isinstance(item, (str, int, float, bool)) and _text(item)
            ]
            if scalars:
                output.append((key, ", ".join(scalars[:12])))
        if len(output) >= limit:
            break
    return output[:limit]


def _format_value(key: str, value: Any, *, spanish: bool) -> str:
    if isinstance(value, bool):
        return ("Sí" if value else "No") if spanish else ("Yes" if value else "No")
    if value is None:
        return "No proporcionado" if spanish else "Not supplied"
    if isinstance(value, float) and "rate" in key.casefold() and 0 <= value <= 1:
        return f"{value * 100:.1f}%"
    return _text(value)


def _label(key: str, *, spanish: bool) -> str:
    leaf = key.rsplit(".", 1)[-1]
    labels = _ES_LABELS if spanish else _EN_LABELS
    return labels.get(leaf, f"`{key}`")


def ci_operational_truth_markdown(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
    force: bool = False,
) -> str:
    context = _ci_context(canonical)
    if not context and not _ci_section(canonical) and not force:
        return ""
    spanish = _is_spanish(canonical, spanish)
    heading = (
        "## Preparación operativa y salud histórica de CI/CD"
        if spanish
        else "## CI/CD Operational Readiness and Historical Health"
    )
    separation = (
        "La madurez de configuración de CI/CD corresponde a evidencia técnica inmutable del commit exacto. "
        "La salud operativa siguiente es contexto mutable de flujos, trabajos y despliegues; permanece separada de la madurez de configuración y no sustituye la aceptación de producción."
        if spanish
        else "CI/CD configuration maturity corresponds to immutable exact-commit technical evidence. "
        "The operational health below is mutable workflow, job, and deployment context; it remains separate from configuration maturity and does not substitute for production acceptance."
    )
    lines = [heading, "", separation, ""]
    lines.extend(f"- {line}" for line in ci_cd_boundary_lines(canonical, spanish=spanish))

    items = _flatten_scalars(context)
    if items:
        lines.extend(
            [
                "",
                "### Contexto operativo adicional"
                if spanish
                else "### Additional operational context",
                "",
            ]
        )
        for key, value in items:
            lines.append(
                f"- {_label(key, spanish=spanish)}: "
                f"{_format_value(key, value, spanish=spanish)}"
            )
    else:
        lines.extend(
            [
                "",
                (
                    "- Contexto operativo conservado: no se suministró evidencia mutable para esta ejecución."
                    if spanish
                    else "- Operational context retained: no mutable run evidence was supplied for this assessment."
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "Estos resultados operativos son evidencia contextual y no cambian por sí solos la puntuación técnica inmutable."
                if spanish
                else "These operational results are contextual evidence and do not by themselves change the immutable technical score."
            ),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def repair_ci_operational_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    replacement = ci_operational_truth_markdown(
        canonical,
        spanish=spanish,
        force=_looks_comprehensive(markdown, canonical),
    )
    if not replacement:
        return str(markdown or "")
    return ci_truth._replace_or_insert_ci_section(str(markdown or ""), replacement)


def _patch_final_truth_lines() -> bool:
    from nico import comprehensive_client_truth_final_v1 as final_truth

    current = getattr(final_truth, "_ci_lines", None)
    if callable(current) and getattr(current, _FINAL_LINES_MARKER, False):
        return True

    def _ci_lines(canonical: Mapping[str, Any]) -> list[str]:
        return ci_cd_boundary_lines(
            canonical,
            spanish=_is_spanish(canonical, False),
        )

    setattr(_ci_lines, _FINAL_LINES_MARKER, True)
    if callable(current):
        setattr(_ci_lines, "_nico_previous", current)
    final_truth._ci_lines = _ci_lines
    return final_truth._ci_lines is _ci_lines


def install_comprehensive_ci_boundary_compat_v74() -> dict[str, Any]:
    """Repair bilingual CI/CD publication after every late report installer."""

    if getattr(ci_truth, _MARKER, False):
        final_lines_bound = _patch_final_truth_lines()
        result = ci_truth.install_ci_operational_truth_v71()
        return {
            "status": "already_installed",
            "version": VERSION,
            "final_truth_lines_bound": final_lines_bound,
            "ci_operational_truth": result,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    ci_truth._is_spanish = _is_spanish
    ci_truth._ci_section = _ci_section
    ci_truth._ci_context = _ci_context
    ci_truth._historical_line = _historical_line
    ci_truth.ci_cd_boundary_lines = ci_cd_boundary_lines
    ci_truth.ci_cd_boundary_markers = ci_cd_boundary_markers
    ci_truth.ci_operational_truth_markdown = ci_operational_truth_markdown
    ci_truth.repair_ci_operational_markdown = repair_ci_operational_markdown
    setattr(ci_truth, _MARKER, True)

    final_lines_bound = _patch_final_truth_lines()
    result = ci_truth.install_ci_operational_truth_v71()
    return {
        "status": "installed",
        "version": VERSION,
        "final_truth_lines_bound": final_lines_bound,
        "friendly_operational_labels_preserved": True,
        "zero_valued_outcomes_preserved": True,
        "missing_ci_evidence_renders_bounded_disclosure": True,
        "english_and_spanish_supported": True,
        "ci_operational_truth": result,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "ci_cd_boundary_lines",
    "ci_cd_boundary_markers",
    "ci_operational_truth_markdown",
    "install_comprehensive_ci_boundary_compat_v74",
    "repair_ci_operational_markdown",
]
