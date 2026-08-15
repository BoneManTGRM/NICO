from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive-ci-operational-truth.v71"
_MARKER = "_nico_comprehensive_ci_operational_truth_v71"

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

_EN_LABELS = {
    "successful_workflow_runs": "Successful workflow runs",
    "non_successful_workflow_runs": "Non-success workflow runs",
    "failed_workflow_runs": "Failed workflow runs",
    "cancelled_workflow_runs": "Cancelled workflow runs",
    "skipped_workflow_runs": "Skipped workflow runs",
    "unknown_workflow_runs": "Unknown workflow runs",
    "workflow_runs_observed": "Workflow runs observed",
    "observed_workflow_runs": "Workflow runs observed",
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
    "skipped_workflow_runs": "Ejecuciones de flujo omitidas",
    "unknown_workflow_runs": "Ejecuciones de flujo con estado desconocido",
    "workflow_runs_observed": "Ejecuciones de flujo observadas",
    "observed_workflow_runs": "Ejecuciones de flujo observadas",
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
    return " ".join(str(value or "").split()).strip()


def _is_spanish(canonical: Mapping[str, Any], spanish: bool) -> bool:
    if spanish:
        return True
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return language.startswith("es")


def _ci_context(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    context = canonical.get("ci_operational_context")
    if not isinstance(context, Mapping):
        context = assessment.get("ci_operational_context")
    return dict(context) if isinstance(context, Mapping) else {}


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
        return "Sí" if spanish and value else "No" if spanish else "Yes" if value else "No"
    if value is None:
        return "No suministrado" if spanish else "Not supplied"
    if isinstance(value, float) and "rate" in key.casefold() and 0 <= value <= 1:
        return f"{value * 100:.1f}%"
    return _text(value)


def _label(key: str, *, spanish: bool) -> str:
    leaf = key.rsplit(".", 1)[-1]
    labels = _ES_LABELS if spanish else _EN_LABELS
    if leaf in labels:
        return labels[leaf]
    return f"`{key}`"


def ci_operational_truth_markdown(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    context = _ci_context(canonical)
    if not context:
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
        else "CI/CD configuration maturity is immutable exact-commit technical evidence. "
        "The operational health below is mutable workflow, job, and deployment context; it remains separate from configuration maturity and does not substitute for production acceptance."
    )
    lines = [heading, "", separation, ""]
    items = _flatten_scalars(context)
    if items:
        for key, value in items:
            lines.append(
                f"- {_label(key, spanish=spanish)}: {_format_value(key, value, spanish=spanish)}"
            )
    else:
        lines.append(
            "- Contexto operativo conservado: Sí"
            if spanish
            else "- Operational context retained: Yes"
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


def _replace_or_insert_ci_section(markdown: str, replacement: str) -> str:
    lines = str(markdown or "").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() in _CI_HEADINGS),
        None,
    )
    if start is not None:
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].startswith("## ")
            ),
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


def repair_ci_operational_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    """Render canonical operational health separately from immutable CI configuration maturity."""

    replacement = ci_operational_truth_markdown(canonical, spanish=spanish)
    if not replacement:
        return str(markdown or "")
    return _replace_or_insert_ci_section(str(markdown or ""), replacement)


def install_ci_operational_truth_v71() -> dict[str, Any]:
    """Bind CI/CD operational truth to the real compact client Markdown producer."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection

    current: Callable[..., str] = completion.compact_client_markdown
    if getattr(current, _MARKER, False):
        projection.compact_client_markdown = current
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "english_and_spanish_supported": True,
            "configuration_and_operational_health_separated": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def compact_client_markdown(
        existing: str,
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current(existing, canonical, register, spanish=spanish)
        return repair_ci_operational_markdown(
            rendered,
            canonical,
            spanish=spanish,
        )

    setattr(compact_client_markdown, _MARKER, True)
    setattr(compact_client_markdown, "_nico_previous", current)
    completion.compact_client_markdown = compact_client_markdown
    projection.compact_client_markdown = compact_client_markdown
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion.compact_client_markdown is compact_client_markdown,
        "english_heading": "CI/CD Operational Readiness and Historical Health",
        "spanish_heading": "Preparación operativa y salud histórica de CI/CD",
        "canonical_operational_values_rendered": True,
        "configuration_and_operational_health_separated": True,
        "english_and_spanish_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "ci_operational_truth_markdown",
    "install_ci_operational_truth_v71",
    "repair_ci_operational_markdown",
]
