from __future__ import annotations

import html
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

ES_MX = "es-MX"

SECTION_LABELS = {
    "code_audit": "Auditoría de código",
    "dependency_health": "Dependencias y ecosistema de librerías",
    "secrets_review": "Revisión de exposición de secretos",
    "static_analysis": "Análisis estático",
    "ci_cd": "CI/CD",
    "architecture_debt": "Arquitectura y deuda técnica",
    "velocity_complexity": "Velocidad y complejidad",
    "scanner_worker_evidence": "Evidencia del scanner worker",
    "test_execution": "Ejecución de pruebas",
    "build_execution": "Ejecución de build",
}

STATUS = {
    "green": "verde",
    "yellow": "amarillo",
    "red": "rojo",
    "gray": "gris",
    "passed": "aprobado",
    "failed": "falló",
    "complete": "completo",
    "pending": "pendiente",
    "running": "en ejecución",
    "queued": "en cola",
}

MATURITY = {
    "Senior": "Senior",
    "Mid": "Intermedio",
    "Junior": "Inicial",
    "Senior maturity signal": "Señal de madurez senior",
    "Mid maturity signal": "Señal de madurez intermedia",
    "Junior maturity signal": "Señal de madurez inicial",
    "Early maturity signal": "Señal de madurez temprana",
}

SUMMARY_BY_SECTION = {
    "code_audit": "La auditoría de código usa metadatos recientes de commits/PR y revisión de patrones de código en el repositorio autorizado.",
    "dependency_health": "La revisión de dependencias usa manifiestos, lockfiles, auditorías disponibles y evidencia explícita de datos no disponibles.",
    "secrets_review": "La revisión de secretos usa detección enmascarada de patrones sensibles y evidencia de scanner cuando está disponible.",
    "static_analysis": "El análisis estático usa checks hospedados y evidencia de Bandit/Semgrep cuando los artefactos están disponibles.",
    "ci_cd": "La revisión de CI/CD usa configuración de workflows y runs de GitHub Actions cuando hay acceso autorizado.",
    "architecture_debt": "La revisión de arquitectura usa estructura del repositorio, señales del árbol de archivos, documentación, pruebas y manifiestos de despliegue.",
    "velocity_complexity": "La señal de trabajo contra expectativa estima madurez con velocidad, trazabilidad de PRs y tamaño del código fuente.",
}

PHRASES = {
    "No evidence returned yet.": "Todavía no hay evidencia.",
    "No data yet.": "Todavía no hay datos.",
    "No high-confidence finding was returned by available hosted checks.": "Los checks hospedados disponibles no regresaron hallazgos de alta confianza.",
    "Human review is required before client-facing delivery.": "Se requiere revisión humana antes de entregar esto a cliente.",
    "Missing evidence is disclosed and is not treated as verified.": "La evidencia faltante se muestra claramente y no se trata como verificada.",
    "Defensive-only. Authorized repositories only. Read-only assessment. No exploitation or destructive actions.": "Solo uso defensivo. Solo repositorios autorizados. Evaluación de solo lectura. Sin explotación ni acciones destructivas.",
    "Review evidence.": "Revisar evidencia.",
    "Prioritize repair plan.": "Priorizar plan de reparación.",
    "Approve or reject any high-impact action.": "Aprobar o rechazar cualquier acción de alto impacto.",
}


def wants_es_mx(value: Any) -> bool:
    return str(value or "").strip().lower() in {"es", "es-mx", "es_mx", "spanish", "mexican spanish", "español", "español méxico"}


def tr(value: Any) -> str:
    text = str(value or "")
    if text in PHRASES:
        return PHRASES[text]
    out = text
    replacements = {
        "Generated": "Generado",
        "Client": "Cliente",
        "Project": "Proyecto",
        "Repository/source scope": "Repositorio/alcance fuente",
        "Not specified": "No especificado",
        "Evidence": "Evidencia",
        "Findings": "Hallazgos",
        "Unavailable": "No disponible",
        "Unavailable data": "Datos no disponibles",
        "Human review": "Revisión humana",
        "Score": "Puntaje",
        "Confidence": "Confianza",
        "Maturity": "Madurez",
        "Assessment": "Evaluación",
        "Report": "Reporte",
        "Scanner artifacts can affect scores only when current parseable GitHub Actions artifacts are available.": "Los artefactos de scanner solo pueden afectar el puntaje cuando hay artefactos actuales y parseables de GitHub Actions.",
        "GitHub Actions artifact access unavailable": "Acceso a artefactos de GitHub Actions no disponible",
        "Set NICO_GITHUB_TOKEN or GITHUB_TOKEN in the deployed backend": "Configura NICO_GITHUB_TOKEN o GITHUB_TOKEN en el backend desplegado",
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def localize_section(section: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(section)
    section_id = str(item.get("id") or "")
    item["label"] = SECTION_LABELS.get(section_id, tr(item.get("label") or section_id))
    item["summary"] = SUMMARY_BY_SECTION.get(section_id, tr(item.get("summary")))
    item["status_label"] = STATUS.get(str(item.get("status") or "").lower(), str(item.get("status") or "desconocido"))
    for key in ("evidence", "findings", "unavailable", "verified_claims", "unverified_claims"):
        if isinstance(item.get(key), list):
            item[key] = [tr(value) for value in item[key]]
    return item


def localize_result(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    output["report_language"] = ES_MX
    output["language_label"] = "Español (México)"
    maturity = dict(output.get("maturity_signal") or {})
    if maturity.get("level"):
        maturity["level"] = MATURITY.get(str(maturity.get("level")), tr(maturity.get("level")))
    if maturity.get("summary"):
        maturity["summary"] = tr(maturity.get("summary"))
    output["maturity_signal"] = maturity
    output["sections"] = [localize_section(item) if isinstance(item, dict) else item for item in output.get("sections", [])]
    output["maturity_semaphore"] = {SECTION_LABELS.get(str(key), tr(key)): STATUS.get(str(value).lower(), str(value)) for key, value in (output.get("maturity_semaphore") or {}).items()}
    output["executive_summary"] = output.get("executive_summary_es_mx") or tr(output.get("executive_summary"))
    for key in ("findings", "repairs", "quick_wins", "medium_term_plan", "resourcing_recommendation", "risk_register", "verification_checklist", "unavailable_data_notes", "next_steps"):
        if isinstance(output.get(key), list):
            output[key] = [tr(value) for value in output[key]]
    if output.get("safety_boundary"):
        output["safety_boundary"] = tr(output["safety_boundary"])
    return output


def markdown_report_es_mx(result: dict[str, Any]) -> str:
    payload = localize_result(result)
    maturity = payload.get("maturity_signal") or {}
    lines = [
        f"# Paquete de reporte NICO — {payload.get('repository') or payload.get('source_scope') or 'sin repositorio'}",
        "",
        "**Impulsado por Reparodynamics**",
        "",
        f"Generado: {payload.get('generated_at') or _now_iso()}",
        f"Idioma: Español (México)",
        f"Cliente: {payload.get('client_name') or 'No especificado'}",
        f"Proyecto: {payload.get('project_name') or 'No especificado'}",
        f"Repositorio/alcance: {payload.get('repository') or payload.get('source_scope') or 'No especificado'}",
        "",
        "## Resumen ejecutivo",
        payload.get("executive_summary") or "No se recibió resumen ejecutivo.",
        "",
        "## Señal de madurez",
        f"Nivel: **{maturity.get('level', 'Desconocido')}**",
        f"Puntaje: **{maturity.get('score', 'N/A')}/100**",
        maturity.get("summary") or "La madurez depende de evidencia disponible y revisión humana.",
        "",
        "## Revisión humana obligatoria",
        "La entrega final, conclusiones para cliente, decisiones de roadmap, presupuesto, recursos y cambios de código requieren revisión humana. La evidencia faltante se muestra y no se trata como verificada.",
        "",
        "## Semáforo de madurez",
    ]
    for key, value in (payload.get("maturity_semaphore") or {}).items():
        lines.append(f"- **{key}**: {value}")
    lines += ["", "## Secciones de evaluación"]
    for item in payload.get("sections", []) or []:
        if not isinstance(item, dict):
            continue
        status = item.get("status_label") or STATUS.get(str(item.get("status") or "").lower(), item.get("status", "desconocido"))
        lines += [
            f"### {item.get('label') or item.get('id') or 'Sección'} — {str(status).upper()} ({item.get('score', 'N/A')}/100)",
            item.get("summary") or "Sin resumen.",
            "",
            "Evidencia:",
        ]
        for evidence in item.get("evidence", []) or ["No se recibió evidencia."]:
            lines.append(f"- {_clean(evidence)}")
        if item.get("findings"):
            lines.append("Hallazgos:")
            for finding in item.get("findings", []):
                lines.append(f"- {_clean(finding)}")
        if item.get("unavailable"):
            lines.append("Datos no disponibles:")
            for unavailable in item.get("unavailable", []):
                lines.append(f"- {_clean(unavailable)}")
        lines.append("")
    for title, key in [
        ("Acciones rápidas", "quick_wins"),
        ("Plan de mediano plazo", "medium_term_plan"),
        ("Recomendación de recursos", "resourcing_recommendation"),
        ("Registro de riesgos", "risk_register"),
        ("Checklist de verificación", "verification_checklist"),
    ]:
        lines.append(f"## {title}")
        values = payload.get(key) or []
        prefix = "- [ ]" if key == "verification_checklist" else "-"
        for item in values or ["Revisión humana requerida."]:
            lines.append(f"{prefix} {_clean(item)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def html_report_es_mx(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html><html lang=\"es-MX\"><head><meta charset=\"utf-8\"><title>Reporte NICO</title><style>body{{font-family:Arial,sans-serif;background:#f8fafc;color:#111827;margin:0}}main{{max-width:980px;margin:34px auto;padding:0 20px 50px}}.hero{{background:#0f172a;color:white;border-radius:28px;padding:30px;margin-bottom:22px}}.hero b{{color:#67e8f9;text-transform:uppercase;letter-spacing:.14em}}pre{{white-space:pre-wrap;background:white;border:1px solid #e5e7eb;border-radius:18px;padding:24px;line-height:1.55}}</style></head><body><main><section class=\"hero\"><b>NICO - Impulsado por Reparodynamics</b><h1>Paquete de reporte para cliente</h1><p>Salida basada en evidencia. Revisión humana requerida.</p></section><pre>{safe}</pre></main></body></html>"""


def reports_es_mx(result: dict[str, Any]) -> dict[str, str]:
    markdown = markdown_report_es_mx(result)
    return {"markdown": markdown, "html": html_report_es_mx(markdown)}
