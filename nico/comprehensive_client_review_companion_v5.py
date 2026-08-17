from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v2 import (
    MAX_CLIENT_REVIEW_PAGES,
    MIN_CLIENT_REVIEW_PAGES,
    review_sections as _legacy_review_sections,
)

VERSION = "nico.comprehensive-client-review-companion.v5"
COMPANION_PAGE_COUNT = 16
SECTION_COUNT = 8
_MARKER = "__nico_comprehensive_review_companion_v5__"

# These sentences are renderer-owned presentation copy.  Spanish is derived
# from the English section contract so both locales always retain the same
# fields, list cardinality, and decision boundary.  Missing translations fail
# closed instead of silently publishing English or a shortened Spanish shape.
_SPANISH_REVIEW_DETAIL_TEXT = {
    "Not assessed — runtime evidence required": "No evaluado — se requiere evidencia de ejecución",
    "Repository tests and static evidence were retained, but critical user journeys were not executed in an approved client runtime environment.": "Se conservaron las pruebas del repositorio y la evidencia estática, pero los recorridos críticos de usuario no se ejecutaron en un entorno de ejecución aprobado por el cliente.",
    "Repository-level test assets and technical controls can be reviewed.": "Pueden revisarse los activos de prueba y los controles técnicos del repositorio.",
    "No terminal scanner execution failure is being treated as functional acceptance.": "Ningún fallo terminal de ejecución de analizadores se trata como aceptación funcional.",
    "Production user journeys, browser and device behavior, integration behavior, and stakeholder acceptance are not proven.": "No se han demostrado los recorridos de usuario en producción, el comportamiento de navegadores y dispositivos, el comportamiento de las integraciones ni la aceptación de las partes interesadas.",
    "Approved critical journeys, runtime environment, browser and device scope, integration endpoints, and acceptance criteria.": "Recorridos críticos aprobados, entorno de ejecución, alcance de navegadores y dispositivos, endpoints de integración y criterios de aceptación.",
    "Keep functional acceptance open. Execute the approved journey matrix and retain results before authorizing client delivery.": "Mantener abierta la aceptación funcional. Ejecutar la matriz de recorridos aprobada y conservar los resultados antes de autorizar la entrega al cliente.",
    "Repository indicators assessed — runtime parity not assessed": "Indicadores del repositorio evaluados — paridad de ejecución no evaluada",
    "Repository configuration and implementation indicators were reviewed. Actual feature, runtime, device, permission, and localization parity were not demonstrated.": "Se revisaron los indicadores de configuración e implementación del repositorio. No se demostró la paridad real de funciones, ejecución, dispositivos, permisos y localización.",
    "Repository-level platform indicators can identify likely shared and platform-specific implementation areas.": "Los indicadores de plataforma del repositorio pueden identificar áreas de implementación probablemente compartidas y específicas de cada plataforma.",
    "Runtime platform parity, device parity, permission parity, and content or localization parity are not established.": "No se ha establecido la paridad de plataformas en ejecución, dispositivos, permisos, contenido o localización.",
    "Platforms in scope, runnable builds, device matrix, feature matrix, permission matrix, and approved parity acceptance criteria.": "Plataformas incluidas en el alcance, compilaciones ejecutables, matriz de dispositivos, matriz de funciones, matriz de permisos y criterios de aceptación de paridad aprobados.",
    "Record repository indicators as assessed and leave runtime platform parity not assessed until device evidence is supplied.": "Registrar los indicadores del repositorio como evaluados y mantener la paridad de plataformas en ejecución como no evaluada hasta que se aporte evidencia de dispositivos.",
    "Limited — workflow history is operational context only": "Limitado — el historial de flujos de trabajo es solo contexto operativo",
    "Historical workflow outcomes were retained separately from immutable technical scoring. Incident, rollback, deployment, and recovery-time evidence remain incomplete unless supplied directly.": "Los resultados históricos de los flujos de trabajo se conservaron separados de la puntuación técnica inmutable. La evidencia de incidentes, reversiones, despliegues y tiempos de recuperación permanece incompleta salvo que se aporte directamente.",
    "Observed workflow outcome counts can be described as mutable operational context.": "Los conteos observados de resultados de flujos de trabajo pueden describirse como contexto operativo mutable.",
    "Immutable CI configuration maturity remains separate from historical outcomes.": "La madurez de la configuración inmutable de CI permanece separada de los resultados históricos.",
    "Change-failure rate, incident severity, rollback effectiveness, and recovery time cannot be confirmed from workflow counts alone.": "La tasa de fallos de cambio, la severidad de los incidentes, la eficacia de las reversiones y el tiempo de recuperación no pueden confirmarse solo con los conteos de flujos de trabajo.",
    "Incident records, deployment records, cancellation reasons, rollback records, and measured recovery times.": "Registros de incidentes, registros de despliegues, motivos de cancelación, registros de reversiones y tiempos de recuperación medidos.",
    "Do not score historical activity as immutable maturity. Review the complete outcome taxonomy and request incident evidence for operational conclusions.": "No puntuar la actividad histórica como madurez inmutable. Revisar la taxonomía completa de resultados y solicitar evidencia de incidentes para formular conclusiones operativas.",
    "Not assessed — authoritative requirements not supplied": "No evaluado — no se aportaron requisitos autoritativos",
    "No approved specification, ADR set, contractual acceptance matrix, or authoritative roadmap commitment was retained as client evidence.": "No se conservó como evidencia del cliente ninguna especificación aprobada, conjunto de ADR, matriz de aceptación contractual ni compromiso autoritativo de hoja de ruta.",
    "Findings can be tied to exact source locations and technical verification criteria.": "Los hallazgos pueden vincularse con ubicaciones exactas del código fuente y criterios técnicos de verificación.",
    "Findings cannot be claimed as contractual requirement failures or roadmap breaches without an authoritative requirements source.": "Los hallazgos no pueden declararse incumplimientos de requisitos contractuales ni de la hoja de ruta sin una fuente autoritativa de requisitos.",
    "Approved specifications, ADRs, acceptance criteria, contractual requirements, and requirement owners.": "Especificaciones aprobadas, ADR, criterios de aceptación, requisitos contractuales y responsables de los requisitos.",
    "Treat current findings as technical observations. Build a requirement-to-finding matrix after the client supplies the authoritative requirements source.": "Tratar los hallazgos actuales como observaciones técnicas. Crear una matriz de requisitos a hallazgos cuando el cliente aporte la fuente autoritativa de requisitos.",
    "Not assessed — stakeholder authority and objectives not supplied": "No evaluado — no se aportaron la autoridad ni los objetivos de las partes interesadas",
    "Business priorities, deadline authority, budget authority, success measures, and residual-risk ownership were not retained in the repository evidence package.": "Las prioridades comerciales, la autoridad sobre plazos y presupuesto, las medidas de éxito y la responsabilidad del riesgo residual no se conservaron en el paquete de evidencia del repositorio.",
    "Technical evidence can support a stakeholder decision once the business context is supplied.": "La evidencia técnica puede respaldar una decisión de las partes interesadas cuando se aporte el contexto comercial.",
    "The system cannot approve priorities, budget, delivery dates, or residual risk on behalf of the client.": "El sistema no puede aprobar prioridades, presupuesto, fechas de entrega ni riesgo residual en nombre del cliente.",
    "Decision owner, technical acceptance owner, budget owner, deadlines, constraints, success measures, and residual-risk authority.": "Responsable de la decisión, responsable de la aceptación técnica, responsable del presupuesto, plazos, restricciones, medidas de éxito y autoridad sobre el riesgo residual.",
    "Keep recommendations advisory until authorized stakeholders confirm objectives, constraints, and acceptance authority.": "Mantener las recomendaciones como asesoría hasta que las partes interesadas autorizadas confirmen los objetivos, las restricciones y la autoridad de aceptación.",
    "Complete automated briefing — human disposition pending": "Resumen automatizado completo — disposición humana pendiente",
    "The exact-source finding register and bounded executive priorities are retained for human review. Automated prioritization is not client acceptance.": "El registro de hallazgos con ubicaciones exactas del código fuente y las prioridades ejecutivas acotadas se conservan para revisión humana. La priorización automatizada no constituye aceptación del cliente.",
    "Exact-source technical findings and verification criteria are available for review.": "Los hallazgos técnicos con ubicaciones exactas del código fuente y los criterios de verificación están disponibles para revisión.",
    "The executive brief can prioritize review work without authorizing remediation or delivery.": "El resumen ejecutivo puede priorizar el trabajo de revisión sin autorizar la remediación ni la entrega.",
    "Residual risk, finding acceptance, remediation ownership, and delivery authorization remain human decisions.": "El riesgo residual, la aceptación de hallazgos, la responsabilidad de la remediación y la autorización de entrega siguen siendo decisiones humanas.",
    "Finding disposition, residual-risk owner, remediation owner, target window, and acceptance evidence for each accepted priority.": "Disposición del hallazgo, responsable del riesgo residual, responsable de la remediación, ventana objetivo y evidencia de aceptación para cada prioridad aceptada.",
    "Disposition each executive finding and retain the reviewer, rationale, owner, and verification artifact before approval.": "Determinar la disposición de cada hallazgo ejecutivo y conservar el revisor, el fundamento, el responsable y el artefacto de verificación antes de la aprobación.",
    "Framework only — pending stakeholder validation": "Solo marco — pendiente de validación de las partes interesadas",
    "A six-month sequencing framework may be derived from technical evidence, but dates, owners, dependencies, commitments, and budget are not approved automatically.": "Puede derivarse de la evidencia técnica un marco de secuenciación de seis meses, pero las fechas, los responsables, las dependencias, los compromisos y el presupuesto no se aprueban automáticamente.",
    "Technical work can be grouped into 0–30, 31–90, and 91–180 day planning windows.": "El trabajo técnico puede agruparse en ventanas de planificación de 0–30, 31–90 y 91–180 días.",
    "Calendar dates, named owners, contractual commitments, labor rates, and budget cannot be finalized without stakeholder approval.": "Las fechas de calendario, los responsables designados, los compromisos contractuales, las tarifas laborales y el presupuesto no pueden finalizarse sin la aprobación de las partes interesadas.",
    "Approved priorities, dependencies, owner roles, acceptance criteria, target dates, capacity, and budget authority.": "Prioridades aprobadas, dependencias, roles responsables, criterios de aceptación, fechas objetivo, capacidad y autoridad presupuestaria.",
    "Label the output a six-month roadmap framework until an authorized stakeholder approves sequencing, dates, owners, and acceptance criteria.": "Etiquetar el resultado como marco de hoja de ruta de seis meses hasta que una parte interesada autorizada apruebe la secuenciación, las fechas, los responsables y los criterios de aceptación.",
    "Framework only — scope and commercial inputs required": "Solo marco — se requieren el alcance y los insumos comerciales",
    "Role sequencing can be suggested from the technical work, but named people, capacity, contract structure, geographic mix, rates, and budget ceilings were not supplied.": "La secuenciación de roles puede sugerirse a partir del trabajo técnico, pero no se aportaron personas designadas, capacidad, estructura contractual, distribución geográfica, tarifas ni límites presupuestarios.",
    "Required role types and technical sequencing can be proposed as planning inputs.": "Los tipos de roles requeridos y la secuenciación técnica pueden proponerse como insumos de planificación.",
    "Headcount, vendor selection, labor rates, total cost, and budget approval cannot be inferred from repository evidence.": "La dotación, la selección de proveedores, las tarifas laborales, el costo total y la aprobación del presupuesto no pueden inferirse de la evidencia del repositorio.",
    "Approved scope, capacity, delivery model, geographic constraints, rates, budget ceiling, and procurement authority.": "Alcance aprobado, capacidad, modelo de entrega, restricciones geográficas, tarifas, límite presupuestario y autoridad de adquisiciones.",
    "Keep staffing and cost values uncommitted until the client supplies commercial inputs and approves the roadmap scope.": "Mantener sin compromiso los valores de personal y costo hasta que el cliente aporte los insumos comerciales y apruebe el alcance de la hoja de ruta.",
}


def _spanish_review_detail(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _spanish_review_detail(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_spanish_review_detail(item) for item in value]
    if isinstance(value, str):
        try:
            return _SPANISH_REVIEW_DETAIL_TEXT[value]
        except KeyError as exc:
            raise ValueError(f"missing Spanish review-detail translation: {value}") from exc
    return deepcopy(value)


def _text(value: Any, limit: int = 1400) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _values(value: Any, *, limit: int = 8, item_limit: int = 850) -> list[str]:
    if isinstance(value, Mapping):
        values: Iterable[Any] = (
            f"{key}: {item}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        )
    elif isinstance(value, (list, tuple, set)):
        values = value
    elif value not in (None, ""):
        values = (value,)
    else:
        values = ()
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = _text(raw, item_limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _spanish_planning_values(
    value: Any,
    *,
    kind: str,
    limit: int = 6,
    item_limit: int = 850,
) -> list[str]:
    """Render retained planning mappings as client prose, never Python reprs."""

    from nico.comprehensive_spanish_canonical_report_v87 import (
        _translate_presentation,
    )

    if isinstance(value, Mapping):
        records = [value]
    elif isinstance(value, (list, tuple)):
        records = list(value)
    else:
        records = [value] if value not in (None, "") else []

    output: list[str] = []
    for raw in records:
        if not isinstance(raw, Mapping):
            text = _text(_translate_presentation(raw), item_limit)
            if text:
                output.append(text)
            continue

        if kind == "roadmap":
            parts: list[str] = []
            window = _text(raw.get("window") or raw.get("title"), 160)
            objective = _text(raw.get("objective") or raw.get("summary"), 360)
            if window:
                parts.append(f"Ventana: {_translate_presentation(window)}")
            if objective:
                parts.append(f"Objetivo: {_translate_presentation(objective)}")
            packages: list[str] = []
            for work in raw.get("work_packages") or []:
                if not isinstance(work, Mapping):
                    translated = _text(_translate_presentation(work), 320)
                    if translated:
                        packages.append(translated)
                    continue
                work_id = _text(
                    work.get("work_package_id")
                    or work.get("id")
                    or work.get("finding_id"),
                    120,
                )
                aliases = [
                    _text(item, 120)
                    for item in work.get("finding_aliases") or []
                    if _text(item, 120)
                ]
                title = _text(work.get("title") or work.get("objective"), 300)
                location = _text(
                    work.get("exact_source")
                    or work.get("location")
                    or work.get("path"),
                    240,
                )
                status = {
                    "open": "abierto",
                    "blocked": "bloqueado",
                    "closed": "cerrado",
                    "review_required": "requiere revisión",
                }.get(_text(work.get("status"), 80).casefold(), _translate_presentation(work.get("status")))
                category = {
                    "architecture": "arquitectura",
                    "code": "código",
                    "dependency": "dependencias",
                    "security": "seguridad",
                    "secrets": "secretos",
                    "static_analysis": "análisis estático",
                    "velocity": "velocidad",
                }.get(
                    _text(work.get("category"), 80).casefold(),
                    _translate_presentation(work.get("category")),
                )
                fields = [
                    f"ID: {work_id}" if work_id else "",
                    f"Alias: {', '.join(aliases)}" if aliases else "",
                    f"Prioridad: {_text(work.get('priority'), 40)}" if work.get("priority") else "",
                    f"Categoría: {category}" if category else "",
                    f"Estado: {status}" if status else "",
                    f"Título: {_translate_presentation(title)}" if title else "",
                    f"Fuente exacta: {location}" if location else "",
                    f"Ruta: {_text(work.get('path'), 240)}" if work.get("path") else "",
                    f"Línea: {work.get('line')}" if work.get("line") not in (None, "") else "",
                    f"ID de regla: {_text(work.get('rule_id'), 120)}" if work.get("rule_id") else "",
                    f"Familia: {_text(work.get('finding_family'), 120)}" if work.get("finding_family") else "",
                    f"Hecho: {_translate_presentation(work.get('fact'))}" if work.get("fact") else "",
                    f"Interpretación: {_translate_presentation(work.get('interpretation'))}" if work.get("interpretation") else "",
                    f"Impacto: {_translate_presentation(work.get('business_impact'))}" if work.get("business_impact") else "",
                    f"Recomendación: {_translate_presentation(work.get('recommendation'))}" if work.get("recommendation") else "",
                ]
                descriptor = " · ".join(item for item in fields if item)
                if descriptor:
                    packages.append(descriptor)
            if packages:
                parts.append(
                    ("Paquete de trabajo: " if len(packages) == 1 else "Paquetes de trabajo: ")
                    + "; ".join(packages)
                )
            rendered = " · ".join(parts)
        else:
            role = _text(raw.get("role") or raw.get("owner_role"), 200)
            focus = _text(
                raw.get("focus")
                or raw.get("responsibility")
                or raw.get("objective"),
                420,
            )
            sequence = raw.get("sequence")
            parts = []
            if role:
                parts.append(f"Rol: {_translate_presentation(role)}")
            if sequence not in (None, ""):
                parts.append(f"Secuencia: {sequence}")
            if focus:
                parts.append(f"Enfoque: {_translate_presentation(focus)}")
            rendered = " · ".join(parts)

        if len(rendered) > item_limit:
            rendered = rendered[: item_limit - 3].rstrip()
            clause_boundary = max(rendered.rfind("; "), rendered.rfind(". "))
            if clause_boundary >= item_limit // 2:
                rendered = rendered[:clause_boundary].rstrip(" ·;,:-")
            elif " " in rendered:
                rendered = rendered.rsplit(" ", 1)[0].rstrip(" ·;,:-")
            rendered += "..."
        else:
            rendered = rendered.strip()
        if rendered:
            output.append(rendered)
        if len(output) >= limit:
            break
    return output


def _assessment(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    value = canonical.get("assessment")
    return value if isinstance(value, Mapping) else {}


def _register_summary(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    assessment = _assessment(canonical)
    register = assessment.get("canonical_scanner_finding_register")
    if not isinstance(register, Mapping):
        register = canonical.get("canonical_scanner_finding_register")
    if not isinstance(register, Mapping):
        return {}
    summary = register.get("totals")
    return summary if isinstance(summary, Mapping) else {}


def _finding_summary(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    register = canonical.get("client_finding_remediation_register")
    if not isinstance(register, Mapping):
        return {}
    summary = register.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _top_findings(canonical: Mapping[str, Any]) -> list[str]:
    register = canonical.get("client_finding_remediation_register")
    if not isinstance(register, Mapping):
        return []
    output: list[str] = []
    for raw in register.get("code_findings") or []:
        if not isinstance(raw, Mapping):
            continue
        priority = _text(raw.get("priority") or "P2", 20).upper()
        identifier = _text(raw.get("finding_id") or raw.get("id"), 120)
        title = _text(raw.get("title") or raw.get("decision_title"), 320)
        location = _text(raw.get("location") or raw.get("path"), 420)
        impact = _text(raw.get("business_impact") or raw.get("impact"), 420)
        output.append(
            " · ".join(
                value
                for value in (
                    priority,
                    identifier,
                    title,
                    location,
                    impact,
                )
                if value
            )
        )
        if len(output) >= 5:
            break
    return output


def _base_section_details(section_id: str, *, spanish: bool) -> dict[str, Any]:
    en: dict[str, dict[str, Any]] = {
        "functional_qa": {
            "status": "Not assessed — runtime evidence required",
            "summary": "Repository tests and static evidence were retained, but critical user journeys were not executed in an approved client runtime environment.",
            "can_conclude": [
                "Repository-level test assets and technical controls can be reviewed.",
                "No terminal scanner execution failure is being treated as functional acceptance.",
            ],
            "cannot_conclude": [
                "Production user journeys, browser and device behavior, integration behavior, and stakeholder acceptance are not proven.",
            ],
            "required_input": [
                "Approved critical journeys, runtime environment, browser and device scope, integration endpoints, and acceptance criteria.",
            ],
            "recommended_decision": "Keep functional acceptance open. Execute the approved journey matrix and retain results before authorizing client delivery.",
        },
        "platform_parity": {
            "status": "Repository indicators assessed — runtime parity not assessed",
            "summary": "Repository configuration and implementation indicators were reviewed. Actual feature, runtime, device, permission, and localization parity were not demonstrated.",
            "can_conclude": [
                "Repository-level platform indicators can identify likely shared and platform-specific implementation areas.",
            ],
            "cannot_conclude": [
                "Runtime platform parity, device parity, permission parity, and content or localization parity are not established.",
            ],
            "required_input": [
                "Platforms in scope, runnable builds, device matrix, feature matrix, permission matrix, and approved parity acceptance criteria.",
            ],
            "recommended_decision": "Record repository indicators as assessed and leave runtime platform parity not assessed until device evidence is supplied.",
        },
        "historical_trends_and_change_failure": {
            "status": "Limited — workflow history is operational context only",
            "summary": "Historical workflow outcomes were retained separately from immutable technical scoring. Incident, rollback, deployment, and recovery-time evidence remain incomplete unless supplied directly.",
            "can_conclude": [
                "Observed workflow outcome counts can be described as mutable operational context.",
                "Immutable CI configuration maturity remains separate from historical outcomes.",
            ],
            "cannot_conclude": [
                "Change-failure rate, incident severity, rollback effectiveness, and recovery time cannot be confirmed from workflow counts alone.",
            ],
            "required_input": [
                "Incident records, deployment records, cancellation reasons, rollback records, and measured recovery times.",
            ],
            "recommended_decision": "Do not score historical activity as immutable maturity. Review the complete outcome taxonomy and request incident evidence for operational conclusions.",
        },
        "requirements_traceability": {
            "status": "Not assessed — authoritative requirements not supplied",
            "summary": "No approved specification, ADR set, contractual acceptance matrix, or authoritative roadmap commitment was retained as client evidence.",
            "can_conclude": [
                "Findings can be tied to exact source locations and technical verification criteria.",
            ],
            "cannot_conclude": [
                "Findings cannot be claimed as contractual requirement failures or roadmap breaches without an authoritative requirements source.",
            ],
            "required_input": [
                "Approved specifications, ADRs, acceptance criteria, contractual requirements, and requirement owners.",
            ],
            "recommended_decision": "Treat current findings as technical observations. Build a requirement-to-finding matrix after the client supplies the authoritative requirements source.",
        },
        "stakeholder_and_business_alignment": {
            "status": "Not assessed — stakeholder authority and objectives not supplied",
            "summary": "Business priorities, deadline authority, budget authority, success measures, and residual-risk ownership were not retained in the repository evidence package.",
            "can_conclude": [
                "Technical evidence can support a stakeholder decision once the business context is supplied.",
            ],
            "cannot_conclude": [
                "The system cannot approve priorities, budget, delivery dates, or residual risk on behalf of the client.",
            ],
            "required_input": [
                "Decision owner, technical acceptance owner, budget owner, deadlines, constraints, success measures, and residual-risk authority.",
            ],
            "recommended_decision": "Keep recommendations advisory until authorized stakeholders confirm objectives, constraints, and acceptance authority.",
        },
        "risk_reduction_and_executive_briefing": {
            "status": "Complete automated briefing — human disposition pending",
            "summary": "The exact-source finding register and bounded executive priorities are retained for human review. Automated prioritization is not client acceptance.",
            "can_conclude": [
                "Exact-source technical findings and verification criteria are available for review.",
                "The executive brief can prioritize review work without authorizing remediation or delivery.",
            ],
            "cannot_conclude": [
                "Residual risk, finding acceptance, remediation ownership, and delivery authorization remain human decisions.",
            ],
            "required_input": [
                "Finding disposition, residual-risk owner, remediation owner, target window, and acceptance evidence for each accepted priority.",
            ],
            "recommended_decision": "Disposition each executive finding and retain the reviewer, rationale, owner, and verification artifact before approval.",
        },
        "six_month_roadmap": {
            "status": "Framework only — pending stakeholder validation",
            "summary": "A six-month sequencing framework may be derived from technical evidence, but dates, owners, dependencies, commitments, and budget are not approved automatically.",
            "can_conclude": [
                "Technical work can be grouped into 0–30, 31–90, and 91–180 day planning windows.",
            ],
            "cannot_conclude": [
                "Calendar dates, named owners, contractual commitments, labor rates, and budget cannot be finalized without stakeholder approval.",
            ],
            "required_input": [
                "Approved priorities, dependencies, owner roles, acceptance criteria, target dates, capacity, and budget authority.",
            ],
            "recommended_decision": "Label the output a six-month roadmap framework until an authorized stakeholder approves sequencing, dates, owners, and acceptance criteria.",
        },
        "staffing_sequencing_and_cost": {
            "status": "Framework only — scope and commercial inputs required",
            "summary": "Role sequencing can be suggested from the technical work, but named people, capacity, contract structure, geographic mix, rates, and budget ceilings were not supplied.",
            "can_conclude": [
                "Required role types and technical sequencing can be proposed as planning inputs.",
            ],
            "cannot_conclude": [
                "Headcount, vendor selection, labor rates, total cost, and budget approval cannot be inferred from repository evidence.",
            ],
            "required_input": [
                "Approved scope, capacity, delivery model, geographic constraints, rates, budget ceiling, and procurement authority.",
            ],
            "recommended_decision": "Keep staffing and cost values uncommitted until the client supplies commercial inputs and approves the roadmap scope.",
        },
    }
    if not spanish:
        return deepcopy(en[section_id])
    return _spanish_review_detail(en[section_id])


def substantive_review_sections(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> list[dict[str, Any]]:
    legacy = _legacy_review_sections(canonical, spanish=spanish)
    output: list[dict[str, Any]] = []
    scanner_totals = _register_summary(canonical)
    decision_summary = _finding_summary(canonical)
    top_findings = _top_findings(canonical)
    for index, raw in enumerate(legacy, start=1):
        section = deepcopy(dict(raw))
        details = _base_section_details(str(section["id"]), spanish=spanish)
        evidence = _values(section.get("evidence"), limit=6)
        findings = _values(section.get("findings"), limit=5)
        limitations = _values(section.get("limitations"), limit=6)

        if section["id"] == "risk_reduction_and_executive_briefing":
            findings = top_findings or findings
            evidence = _values(
                [
                    f"Decision findings: {decision_summary.get('decision_finding_count', 0)}",
                    f"Exact-source findings: {decision_summary.get('exact_source_code_finding_count', 0)}",
                    f"Confirmed material scanner findings: {scanner_totals.get('material', 0)}",
                    f"Review-required scanner candidates: {scanner_totals.get('review_required', 0)}",
                ],
                limit=6,
            )
        elif section["id"] == "historical_trends_and_change_failure":
            assessment = _assessment(canonical)
            operational = assessment.get("ci_cd_operational_health")
            if isinstance(operational, Mapping):
                taxonomy = operational.get("outcome_taxonomy")
                evidence = _values(
                    [
                        f"Observed workflow runs: {operational.get('workflow_run_count', operational.get('observed_run_count', 0))}",
                        f"Outcome taxonomy: {taxonomy}" if isinstance(taxonomy, Mapping) else "",
                        "Workflow outcomes are operational context only and do not change immutable CI configuration maturity.",
                    ],
                    limit=6,
                )
        elif section["id"] == "six_month_roadmap":
            roadmap = canonical.get("roadmap") or _assessment(canonical).get("roadmap") or []
            evidence = (
                _spanish_planning_values(roadmap, kind="roadmap", limit=6)
                if spanish
                else _values(roadmap, limit=6)
            ) or evidence
        elif section["id"] == "staffing_sequencing_and_cost":
            staffing = canonical.get("staffing_plan") or _assessment(canonical).get("staffing_plan") or []
            evidence = (
                _spanish_planning_values(staffing, kind="staffing", limit=6)
                if spanish
                else _values(staffing, limit=6)
            ) or evidence

        if not evidence:
            evidence = [
                (
                    "No additional client-supplied evidence was retained for this section; the limitation and required input below are authoritative."
                    if not spanish
                    else "No se conservó evidencia adicional del cliente; la limitación y los insumos requeridos que siguen son autoritativos."
                )
            ]
        if not limitations:
            limitations = list(details["cannot_conclude"])

        section.update(
            {
                "section_number": index,
                "section_count": SECTION_COUNT,
                "status": details["status"],
                "summary": details["summary"],
                "evidence": evidence,
                "findings": findings,
                "limitations": limitations,
                "can_conclude": list(details["can_conclude"]),
                "cannot_conclude": list(details["cannot_conclude"]),
                "required_input": list(details["required_input"]),
                "recommended_decision": details["recommended_decision"],
            }
        )
        output.append(section)
    return output


def _remove_heading_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start < 0:
        return markdown
    level = len(heading) - len(heading.lstrip("#"))
    match = re.compile(rf"(?m)^#{{1,{level}}}\s+.+$").search(
        markdown,
        start + len(heading),
    )
    end = match.start() if match else len(markdown)
    return markdown[:start].rstrip() + "\n\n" + markdown[end:].lstrip()


def merge_substantive_review_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    output = str(markdown or "")
    sections = substantive_review_sections(canonical, spanish=spanish)
    for section in sections:
        heading = f"## {section['title']}"
        while heading in output:
            output = _remove_heading_section(output, heading)

    lines = [
        "## Revisión integral del cliente" if spanish else "## Comprehensive Client Review",
        "",
        (
            "Cada sección separa evidencia retenida, conclusiones permitidas, límites, insumos requeridos y la decisión humana pendiente."
            if spanish
            else "Each section separates retained evidence, permitted conclusions, limitations, required input, and the pending human decision."
        ),
        "",
    ]
    labels = {
        "status": "Estado" if spanish else "Status",
        "summary": "Resumen" if spanish else "Summary",
        "evidence": "Evidencia retenida" if spanish else "Retained evidence",
        "can": "Puede concluirse" if spanish else "What can be concluded",
        "cannot": "No puede concluirse" if spanish else "What cannot be concluded",
        "input": "Insumos requeridos del cliente" if spanish else "Required client input",
        "decision": "Decisión recomendada" if spanish else "Recommended decision",
        "review": "Disposición del revisor" if spanish else "Reviewer disposition",
    }
    for section in sections:
        lines.extend(
            [
                f"## {section['title']}",
                "",
                f"- {labels['status']}: {section['status']}",
                f"- {labels['summary']}: {section['summary']}",
                "",
                f"### {labels['evidence']}",
                "",
                *[f"- {item}" for item in section["evidence"]],
                "",
                f"### {labels['can']}",
                "",
                *[f"- {item}" for item in section["can_conclude"]],
                "",
                f"### {labels['cannot']}",
                "",
                *[f"- {item}" for item in section["cannot_conclude"]],
                "",
                f"### {labels['input']}",
                "",
                *[f"- {item}" for item in section["required_input"]],
                "",
                f"### {labels['decision']}",
                "",
                f"- {section['recommended_decision']}",
                "",
                f"### {labels['review']}",
                "",
                *[f"- [ ] {item}" for item in section["questions"]],
                "",
            ]
        )
    companion = "\n".join(lines).strip() + "\n"
    for marker in (
        "## Compact Finding and Remediation Register",
        "## Registro compacto de hallazgos y remediación",
        "## Evidence Package Summary",
        "## Resumen del paquete de evidencia",
    ):
        if marker in output:
            return output.replace(marker, companion + "\n" + marker, 1)
    return output.rstrip() + "\n\n" + companion


def render_substantive_review_pdf(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    sections = substantive_review_sections(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NICOReviewV5Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18.5,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "NICOReviewV5Heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.7,
        leading=13,
        textColor=colors.HexColor("#075985"),
        spaceBefore=5,
        spaceAfter=3,
    )
    body = ParagraphStyle(
        "NICOReviewV5Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.7,
        leading=9.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=3,
    )
    small = ParagraphStyle(
        "NICOReviewV5Small",
        parent=body,
        fontSize=7,
        leading=8.8,
        textColor=colors.HexColor("#475569"),
        spaceAfter=2,
    )
    warning = ParagraphStyle(
        "NICOReviewV5Warning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.7,
        borderPadding=6,
        spaceAfter=7,
    )
    boundary = ParagraphStyle(
        "NICOReviewV5Boundary",
        parent=small,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=.5,
        borderPadding=5,
        spaceBefore=4,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 1000) -> Paragraph:
        if not spanish:
            return Paragraph(html.escape(_text(value, limit)), style)
        rendered = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
        if len(rendered) > limit:
            rendered = rendered[: limit - 3].rstrip()
            clause_boundary = max(rendered.rfind("; "), rendered.rfind(". "))
            if clause_boundary >= limit // 2:
                rendered = rendered[:clause_boundary].rstrip(" ·;,:-")
            elif " " in rendered:
                rendered = rendered.rsplit(" ", 1)[0].rstrip(" ·;,:-")
            rendered += "..."
        return Paragraph(html.escape(rendered), style)

    page_labels: dict[int, tuple[int, int]] = {}
    for section in sections:
        page_labels[(section["section_number"] - 1) * 2 + 1] = (
            section["section_number"],
            1,
        )
        page_labels[(section["section_number"] - 1) * 2 + 2] = (
            section["section_number"],
            2,
        )

    def footer(canvas: Any, doc: Any) -> None:
        section_number, section_page = page_labels.get(doc.page, (0, 0))
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            .55 * inch,
            .35 * inch,
            (
                "NICO | revisión integral del cliente | borrador automatizado"
                if spanish
                else "NICO | Comprehensive client review | automated draft"
            ),
        )
        canvas.drawRightString(
            7.95 * inch,
            .35 * inch,
            (
                f"Sección {section_number} de {SECTION_COUNT} | Página {section_page} de 2"
                if spanish
                else f"Section {section_number} of {SECTION_COUNT} | Page {section_page} of 2"
            ),
        )
        canvas.restoreState()

    story: list[Any] = []
    total_pages = len(sections) * 2
    current_page = 0
    for section in sections:
        current_page += 1
        story.extend(
            [
                p(section["title"], title),
                p(
                    "BORRADOR AUTOMATIZADO | REVISION HUMANA REQUERIDA"
                    if spanish
                    else "AUTOMATED DRAFT | HUMAN REVIEW REQUIRED",
                    warning,
                ),
            ]
        )
        status_table = Table(
            [
                [p("Estado" if spanish else "Status", small), p(section["status"], small)],
                [p("Resumen" if spanish else "Summary", small), p(section["summary"], small)],
            ],
            colWidths=[1.2 * inch, 6.2 * inch],
        )
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([status_table, p("Evidencia retenida" if spanish else "Retained evidence", heading)])
        for item in section["evidence"][:6]:
            story.append(p(f"- {item}", body, 900 if spanish else 650))
        if section["findings"]:
            story.append(p("Observaciones prioritarias" if spanish else "Priority observations", heading))
            for item in section["findings"][:4]:
                story.append(p(f"- {item}", small, 620))
        story.append(p("Puede concluirse" if spanish else "What can be concluded", heading))
        for item in section["can_conclude"]:
            story.append(p(f"- {item}", body, 650))
        story.extend(
            [
                Spacer(1, .04 * inch),
                p(
                    "Esta página conserva evidencia y conclusiones limitadas; no representa aceptación del cliente."
                    if spanish
                    else "This page retains evidence and bounded conclusions; it does not represent client acceptance.",
                    boundary,
                ),
            ]
        )
        if current_page < total_pages:
            story.append(PageBreak())

        current_page += 1
        story.extend(
            [
                p(
                    f"{section['title']}: "
                    + ("límites y disposición" if spanish else "Limits and disposition"),
                    title,
                ),
                p(
                    "DECISION HUMANA PENDIENTE | ENTREGA BLOQUEADA"
                    if spanish
                    else "HUMAN DECISION PENDING | DELIVERY BLOCKED",
                    warning,
                ),
                p("No puede concluirse" if spanish else "What cannot be concluded", heading),
            ]
        )
        for item in section["cannot_conclude"]:
            story.append(p(f"- {item}", body, 650))
        if section["limitations"]:
            story.append(p("Limitaciones retenidas" if spanish else "Retained limitations", heading))
            for item in section["limitations"][:5]:
                story.append(p(f"- {item}", body, 650))
        story.append(p("Insumos requeridos del cliente" if spanish else "Required client input", heading))
        for item in section["required_input"]:
            story.append(p(f"- {item}", body, 650))
        story.extend(
            [
                p("Decisión recomendada" if spanish else "Recommended decision", heading),
                p(section["recommended_decision"], boundary),
                p("Disposición del revisor" if spanish else "Reviewer disposition", heading),
            ]
        )
        for item in section["questions"]:
            story.append(p(f"[ ] {item}", body, 650))
        story.extend(
            [
                p(
                    "Resultado: [ ] aceptar evidencia  [ ] solicitar evidencia  [ ] rechazar conclusión  [ ] diferir"
                    if spanish
                    else "Outcome: [ ] accept evidence  [ ] request evidence  [ ] reject conclusion  [ ] defer",
                    body,
                ),
                p(
                    "Responsable / fecha / evidencia de aceptación: ______________________________________________"
                    if spanish
                    else "Reviewer / date / acceptance evidence: _________________________________________________",
                    body,
                ),
                p(
                    "La disposición de esta sección no autoriza por sí sola la entrega del paquete."
                    if spanish
                    else "Disposition of this section alone does not authorize delivery of the package.",
                    boundary,
                ),
            ]
        )
        if current_page < total_pages:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Comprehensive Client Review",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    if page_count != COMPANION_PAGE_COUNT:
        raise ValueError(
            f"Substantive Comprehensive review companion must be exactly {COMPANION_PAGE_COUNT} pages, got {page_count}."
        )
    return pdf


def install_comprehensive_review_companion_v5() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4

    if getattr(completion.render_comprehensive_review_companion_pdf, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "page_count": COMPANION_PAGE_COUNT,
            "continuous_section_numbering": True,
        }

    setattr(render_substantive_review_pdf, _MARKER, True)
    for module in (v2, v3, v4):
        module.review_sections = substantive_review_sections
        module.merge_review_companion_markdown = merge_substantive_review_markdown
        module.render_comprehensive_review_companion_pdf = render_substantive_review_pdf
    completion.merge_review_companion_markdown = merge_substantive_review_markdown
    completion.render_comprehensive_review_companion_pdf = render_substantive_review_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "section_count": SECTION_COUNT,
        "continuous_section_numbering": True,
        "filler_only_pages_allowed": False,
        "roadmap_claim": "framework_pending_stakeholder_validation",
        "platform_parity_claim": "repository_indicators_assessed_runtime_not_assessed",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "COMPANION_PAGE_COUNT",
    "MAX_CLIENT_REVIEW_PAGES",
    "MIN_CLIENT_REVIEW_PAGES",
    "SECTION_COUNT",
    "VERSION",
    "install_comprehensive_review_companion_v5",
    "merge_substantive_review_markdown",
    "render_substantive_review_pdf",
    "substantive_review_sections",
]
