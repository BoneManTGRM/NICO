from __future__ import annotations

from typing import Any

from nico.comprehensive_report_scanner_detection_v51 import _text

VERSION = "nico.comprehensive_report_spanish_text.v51"


ES_EXACT = {
    "Code Audit": "Auditoría de código",
    "Dependency / Library Ecosystem": "Ecosistema de dependencias y bibliotecas",
    "Secrets Exposure Review": "Revisión de exposición de secretos",
    "Static Analysis": "Análisis estático",
    "CI/CD Analysis": "Análisis de CI/CD",
    "Architecture & Technical Debt": "Arquitectura y deuda técnica",
    "Velocity / Complexity": "Velocidad y complejidad",
    "Authorization and Scope": "Autorización y alcance",
    "Immutable Repository Snapshot": "Instantánea inmutable del repositorio",
    "Repository and Delivery Evidence": "Evidencia del repositorio y de entrega",
    "Dependency, Security, and Static Analysis": "Dependencias, seguridad y análisis estático",
    "CI/CD, Architecture, Complexity, and Velocity": "CI/CD, arquitectura, complejidad y velocidad",
    "Evidence Reconciliation and Scoring": "Conciliación y puntuación de evidencia",
    "Core Decision Report": "Informe principal para decisiones",
    "Deep Scanner Triage": "Triaje profundo de analizadores",
    "Functional QA": "Control de calidad funcional",
    "Platform Parity": "Paridad entre plataformas",
    "Deployment and Infrastructure": "Despliegue e infraestructura",
    "Architecture and Data Flow": "Arquitectura y flujo de datos",
    "Developer Delivery Process": "Proceso de entrega de desarrollo",
    "Stakeholder and Business Alignment": "Alineación con partes interesadas y negocio",
    "Requirements Traceability": "Trazabilidad de requisitos",
    "Historical Trends and Change Failure": "Tendencias históricas y fallos de cambio",
    "Six-Month Roadmap": "Hoja de ruta de seis meses",
    "Staffing, Sequencing, and Cost": "Personal, secuencia y costo",
    "Risk Reduction and Executive Briefing": "Reducción de riesgo y resumen ejecutivo",
    "Cross-Format Truth Verification": "Verificación de coherencia entre formatos",
    "Human Review Request": "Solicitud de revisión humana",
    "Client Acceptance Pending": "Aceptación del cliente pendiente",
    "Product Engineering Architect": "Arquitecto de ingeniería de producto",
    "Senior Product Engineer": "Ingeniero sénior de producto",
    "Platform Engineer": "Ingeniero de plataforma",
    "Product Quality Engineer": "Ingeniero de calidad de producto",
    "Quick Win": "Mejora rápida",
    "Strategic": "Estratégico",
    "Complete": "Completo",
    "COMPLETE": "COMPLETO",
    "Verified": "Verificado",
    "VERIFIED": "VERIFICADO",
    "Review Limited": "Revisión limitada",
    "REVIEW LIMITED": "REVISIÓN LIMITADA",
    "Not Scored": "Sin puntuación",
    "NOT SCORED": "SIN PUNTUACIÓN",
    "Human Review Required": "Revisión humana requerida",
    "Delivery Blocked": "Entrega bloqueada",
    "Internal Draft": "Borrador interno",
}

ES_REPLACEMENTS = {
    "NICO completed an authorized Comprehensive Technical Assessment for": "NICO completó una Evaluación Técnica Integral autorizada para",
    "Weighted technical maturity is": "La madurez técnica ponderada es",
    "independently evidence-adjusted readiness is": "la preparación ajustada de forma independiente por evidencia es",
    "Human review and exact-package approval remain mandatory": "La revisión humana y la aprobación del paquete exacto siguen siendo obligatorias",
    "Complexity hotspot": "Punto crítico de complejidad",
    "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change": "La lógica ramificada concentrada aumenta el riesgo de regresión, el costo de revisión y la dificultad de realizar cambios seguros",
    "Decompose the hotspot into bounded modules, add characterization tests, and enforce complexity and change-size thresholds in CI": "Dividir el punto crítico en módulos acotados, agregar pruebas de caracterización y aplicar umbrales de complejidad y tamaño de cambio en CI",
    "The affected control cannot reach verified assurance because the required analyzer did not complete": "El control afectado no puede alcanzar una garantía verificada porque el analizador requerido no terminó",
    "Repair the analyzer or worker resource boundary and rerun two consecutive exact-SHA evidence passes": "Reparar el analizador o el límite de recursos del trabajador y ejecutar dos pasadas consecutivas de evidencia sobre el SHA exacto",
    "The retained analyzer record is not a confirmed defect": "El registro conservado del analizador no es un defecto confirmado",
    "requires human triage": "requiere triaje humano",
    "require human triage": "requieren triaje humano",
    "candidate volume is not a confirmed defect count": "el volumen de candidatos no equivale a un conteo de defectos confirmados",
    "Failed static analyzers": "Analizadores estáticos fallidos",
    "Completed static tools": "Herramientas estáticas completadas",
    "Evidence limitations": "Limitaciones de evidencia",
    "Findings": "Hallazgos",
    "Recommendation": "Recomendación",
    "Business impact": "Impacto empresarial",
    "Cost of inaction": "Costo de no actuar",
    "Residual risk": "Riesgo residual",
    "Acceptance criteria": "Criterios de aceptación",
    "Owner / effort": "Responsable / esfuerzo",
    "Remaining likelihood": "Probabilidad restante",
    "remaining impact": "impacto restante",
    "The fix does not eliminate": "La corrección no elimina",
    "Future regressions, adjacent unassessed paths, operational misuse, and evidence outside the assessed commit remain possible": "Siguen siendo posibles regresiones futuras, rutas adyacentes no evaluadas, uso operativo incorrecto y evidencia fuera del commit evaluado",
    "Unclassified failures obscure release reliability and can hide recurring operational defects": "Los fallos sin clasificar ocultan la confiabilidad de las versiones y pueden esconder defectos operativos recurrentes",
    "Classify non-success runs by cause": "Clasificar por causa las ejecuciones no exitosas",
    "No structured scanner completion record retained": "No se conservó un registro estructurado de finalización de analizadores",
    "The assessment completed": "La evaluación terminó",
    "completed against the assessed snapshot": "se completó contra la instantánea evaluada",
    "current-run": "de la ejecución actual",
    "exact-SHA": "SHA exacto",
    "evidence": "evidencia",
    "Evidence": "Evidencia",
    "unavailable": "no disponible",
    "Unavailable": "No disponible",
    "partial": "parcial",
    "failed": "fallido",
    "timed out": "agotó el tiempo",
    "open": "abierto",
    "moderate": "moderada",
    "high": "alta",
    "low": "baja",
    "Severe qualitative exposure over 90 days": "Exposición cualitativa grave durante 90 días",
    "Limited qualitative exposure over 90 days": "Exposición cualitativa limitada durante 90 días",
    "Material if the control regresses or related unassessed conditions exist": "Material si el control retrocede o existen condiciones relacionadas no evaluadas",
    "The repository-validation workflow completes successfully": "El flujo de validación del repositorio termina correctamente",
    "The exact-SHA": "El SHA exacto",
    "against the same immutable revision": "contra la misma revisión inmutable",
    "Human intent, team dynamics, requirements quality, and governance require stakeholder evidence": "La intención humana, la dinámica del equipo, la calidad de los requisitos y la gobernanza requieren evidencia de las partes interesadas",
    "Not verified unless production telemetry was explicitly supplied and retained": "No verificado salvo que se haya proporcionado y conservado telemetría de producción de forma explícita",
    "Repository analysis is not a penetration test and does not prove exploitability or absence of vulnerabilities": "El análisis del repositorio no es una prueba de penetración y no demuestra explotabilidad ni ausencia de vulnerabilidades",
    "Technical evidence does not constitute legal or regulatory certification": "La evidencia técnica no constituye una certificación legal ni regulatoria",
}


def _es(value: Any) -> str:
    text = _text(value, 10000)
    if not text:
        return ""
    if text in ES_EXACT:
        return ES_EXACT[text]
    for source, target in sorted(ES_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(source, target)
    return text


def _md_escape(value: Any) -> str:
    return _es(value).replace("|", "\\|")


def _md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_md_escape(value) for value in row) + " |")
    return lines


def _spanish_markdown(canonical: dict[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = assessment.get("technical_score", maturity.get("score"))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in canonical.get("findings_register") or [] if isinstance(item, dict)]
    stages = [item for item in canonical.get("stage_summaries") or [] if isinstance(item, dict)]
    roadmap = [item for item in canonical.get("roadmap") or [] if isinstance(item, dict)]
    staffing = [item for item in canonical.get("staffing_plan") or [] if isinstance(item, dict)]
    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}

    lines = [
        f"# Evaluación Técnica Integral NICO — {_text(identity.get('repository'))}",
        "",
        f"ID de ejecución: {_text(identity.get('run_id'))}",
        f"SHA inmutable evaluado: {_text(identity.get('commit_sha'))}",
        f"ID del libro mayor de evidencia: {_text(identity.get('evidence_ledger_id'))}",
        "Idioma del informe: Español (México)",
        "",
        "## Resumen ejecutivo para decisiones",
        _es(assessment.get("executive_summary") or "La evaluación automatizada terminó y conserva las limitaciones de evidencia de forma explícita."),
        "",
        "## Estado de la evaluación",
        *_md_table(
            ["Dimensión", "Estado"],
            [
                ["Ejecución de la evaluación", "COMPLETA"],
                ["Generación de artefactos", "COMPLETA"],
                ["Madurez técnica", f"{technical}/100" if isinstance(technical, (int, float)) else "SIN PUNTUACIÓN"],
                ["Ajuste por evidencia", f"{adjusted}/100" if isinstance(adjusted, (int, float)) else "SIN PUNTUACIÓN"],
                ["Ejecución de analizadores", "PARCIAL" if health.get("incomplete_scanners") else "COMPLETA"],
                ["Verificación entre formatos", "Se ejecuta automáticamente antes de la revisión humana"],
                ["Aprobación", "PENDIENTE DE REVISIÓN HUMANA"],
                ["Entrega al cliente", "BLOQUEADA HASTA LA APROBACIÓN DEL PAQUETE EXACTO"],
            ],
        ),
        "",
        "## Cuadro de puntuación técnica",
        *_md_table(
            ["Control", "Puntuación técnica", "Ejecución", "Garantía de evidencia", "Disposición de hallazgos"],
            [
                [
                    section.get("label") or section.get("id"),
                    f"{section.get('score_value')}/100" if isinstance(section.get("score_value"), (int, float)) else "SIN PUNTUACIÓN",
                    str(section.get("execution_status") or "pendiente").upper(),
                    section.get("assurance_label") or "REVISIÓN LIMITADA",
                    section.get("finding_disposition") or "PENDIENTE",
                ]
                for section in sections
            ],
        ),
        "",
        "## Salud de la evidencia y analizadores",
        _es(health.get("confidence_effect") or "Las limitaciones de los analizadores se muestran por control."),
        "",
        *_md_table(
            ["Analizador", "Estado", "Requerido", "Controles afectados", "Acción"],
            [
                [
                    item.get("scanner_name") or item.get("scanner"),
                    str(item.get("status") or "desconocido").upper(),
                    "Sí" if item.get("required") else "No",
                    ", ".join(item.get("score_controls_affected") or item.get("affected_controls") or []),
                    item.get("remediation_guidance") or item.get("remediation") or "Ninguna",
                ]
                for item in assessment.get("scanner_execution_records") or health.get("incomplete_scanners") or []
                if isinstance(item, dict)
            ],
        ),
        "",
        "## Registro detallado de hallazgos",
    ]

    if not findings:
        lines.append("- No se conservó un registro de hallazgos.")
    for finding in findings:
        lines += [
            "",
            f"### {finding.get('priority') or 'P2'} · {_es(finding.get('title'))} · {finding.get('finding_id') or finding.get('id')}",
            f"- **Categoría / estado:** {_es(finding.get('category'))} · {_es(finding.get('status'))}",
            f"- **Ubicación:** {_text(finding.get('location'))}",
            f"- **Hecho observado:** {_es(finding.get('fact') or finding.get('evidence'))}",
            f"- **Interpretación:** {_es(finding.get('interpretation'))}",
            f"- **Impacto empresarial:** {_es(finding.get('business_impact') or finding.get('impact'))}",
            f"- **Recomendación:** {_es(finding.get('recommendation'))}",
            f"- **Responsable / esfuerzo:** {_es(finding.get('owner_role'))} · {_text(finding.get('effort'))}",
            f"- **Costo de no actuar:** {_es(finding.get('cost_of_inaction'))}",
            f"- **Riesgo residual:** {_es(finding.get('residual_risk'))}",
        ]
        criteria = finding.get("acceptance_criteria") or []
        if isinstance(criteria, str):
            criteria = [criteria]
        if criteria:
            lines.append("- **Criterios de aceptación:**")
            lines.extend(f"  - {_es(item)}" for item in criteria)

    lines += ["", "## Hoja de ruta de seis meses"]
    for window in roadmap:
        lines += ["", f"### {_es(window.get('window'))} — {_es(window.get('objective'))}"]
        for package in window.get("work_packages") or []:
            if not isinstance(package, dict):
                continue
            lines += [
                f"- **{package.get('work_package_id') or package.get('id')} · {_es(package.get('title'))}**",
                f"  - Responsable: {_es(package.get('owner_role') or package.get('owner'))}",
                f"  - Esfuerzo: {_text(package.get('effort') or package.get('effort_range'))}",
                f"  - Impacto esperado: {_es(package.get('expected_impact'))}",
                f"  - Riesgo residual: {_es(package.get('residual_risk'))}",
            ]

    lines += ["", "## Personal y secuencia"]
    lines += _md_table(
        ["Secuencia", "Rol", "Enfoque", "Capacidad indicativa"],
        [
            [item.get("sequence"), item.get("role"), item.get("focus"), item.get("indicative_capacity") or item.get("capacity")]
            for item in staffing
        ],
    )

    lines += ["", "## Límites de alcance y riesgo no evaluado"]
    lines += _md_table(
        ["Área", "Límite"],
        [[item.get("area"), item.get("boundary")] for item in assessment.get("scope_boundaries") or [] if isinstance(item, dict)],
    )

    lines += ["", "## Apéndice de evidencia"]
    for stage in stages:
        lines += [
            "",
            f"### {_es(stage.get('title'))} — {_es(str(stage.get('status') or '').upper())}",
            _es(stage.get("summary")),
        ]
        if stage.get("evidence"):
            lines.append("**Evidencia conservada:**")
            lines.extend(f"- {_es(item)}" for item in stage.get("evidence") or [])
        if stage.get("findings"):
            lines.append("**Hallazgos:**")
            lines.extend(f"- {_es(item)}" for item in stage.get("findings") or [])
        if stage.get("unavailable"):
            lines.append("**Evidencia no disponible o limitada:**")
            lines.extend(f"- {_es(item)}" for item in stage.get("unavailable") or [])

    lines += [
        "",
        "## Puerta de revisión y aceptación humana",
        "La evaluación automatizada terminó como borrador. Antes de cualquier entrega al cliente, una persona autorizada debe verificar la identidad, disponer los hallazgos, confirmar la coherencia entre JSON, CSV, Markdown, HTML y PDF, y aprobar o rechazar el paquete inmutable exacto.",
        "",
        "**ENTREGA AL CLIENTE BLOQUEADA · APROBACIÓN HUMANA PENDIENTE**",
        "<!-- CLIENT DELIVERY BLOCKED · PENDING HUMAN APPROVAL -->",
        "",
    ]
    return "\n".join(lines)



__all__ = ["VERSION", "_es", "_spanish_markdown"]
