from __future__ import annotations

from copy import deepcopy
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


def localize_section(section: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(section)
    section_id = str(item.get("id") or "")
    item["label"] = SECTION_LABELS.get(section_id, tr(item.get("label") or section_id))
    if section_id in SUMMARY_BY_SECTION:
        item["summary"] = SUMMARY_BY_SECTION[section_id]
    else:
        item["summary"] = tr(item.get("summary"))
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
