from __future__ import annotations

from typing import Any

from nico.hosted_assessment import build_html, build_markdown, build_pdf_base64
from nico.i18n_es_mx import reports_es_mx, wants_es_mx


def _wants_es_mx(result: dict[str, Any]) -> bool:
    return any(wants_es_mx(result.get(key)) for key in ("report_language", "language", "assessment_mode"))


def _safe_score(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [item for item in result.get("sections", []) if isinstance(item, dict) and item.get("status") != "gray"]
    score = round(sum(int(item.get("score") or 0) for item in sections) / len(sections)) if sections else 0
    if score >= 82:
        level = "Senior"
        summary = "Evidence suggests mature delivery foundations with documented structure, automation, and low-risk signals, pending human validation."
    elif score >= 58:
        level = "Mid"
        summary = "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability, test, dependency, or automation gaps."
    else:
        level = "Junior"
        summary = "Evidence suggests early-stage maturity or missing access to the signals needed for confident assessment."
    result["maturity_signal"] = {"level": level, "score": score, "summary": summary}
    result["maturity_semaphore"] = {item.get("label", item.get("id", "Section")): item.get("status") for item in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level


def _apply_final_score_adjustments(result: dict[str, Any]) -> None:
    for item in result.get("sections", []) or []:
        if not isinstance(item, dict) or item.get("id") != "code_audit":
            continue
        evidence_text = "\n".join(str(note) for note in item.get("evidence", []) or [])
        finding_text = "\n".join(str(note) for note in item.get("findings", []) or [])
        has_clean_marker_evidence = "actionable TODO/FIXME/security markers=0" in evidence_text
        has_actionable_marker_finding = "TODO/FIXME/security-note markers require triage" in finding_text
        has_production_risk = "production-risk=" in evidence_text and "production-risk=0" not in evidence_text
        if has_clean_marker_evidence and not has_actionable_marker_finding and not has_production_risk:
            item["score"] = max(int(item.get("score") or 0), 86)
            item["status"] = _status_from_score(int(item["score"]))
            item["summary"] = "Code audit uses recent commit/PR metadata plus hosted source-pattern review from the authorized repository; generic security wording is excluded from actionable marker scoring."
    _recompute_maturity(result)


def _build_executive_summary(result: dict[str, Any]) -> str:
    maturity = result.get("maturity_signal") or {}
    level = maturity.get("level") or "Unknown"
    score = _safe_score(maturity.get("score"))
    repo = result.get("repository") or result.get("source_scope") or "the authorized repository"
    quality_note = ""
    if result.get("assessment_quality") == "degraded_metadata":
        quality_note = " Some GitHub metadata was unavailable, so affected sections are degraded rather than treated as final negative evidence."
    if _wants_es_mx(result):
        return (
            f"NICO completó una Evaluación Express autorizada de salud técnica para {repo}. "
            f"La señal final de madurez es {level} ({score}/100). "
            "El puntaje se basa en la evidencia final después de aplicar auditoría de código, dependencias, secretos, análisis estático, CI/CD, arquitectura, velocidad, evidencia de artefactos y notas explícitas de datos no disponibles. "
            "La entrega final a cliente todavía requiere revisión humana."
            + (" Algunos metadatos de GitHub no estuvieron disponibles, por lo que las secciones afectadas se degradan en vez de tratarse como evidencia negativa final." if quality_note else "")
        )
    return (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repo}. "
        f"The final maturity signal is {level} ({score}/100). "
        "Scores are generated from the final evidence-bound result after code audit, dependency, secrets, static analysis, CI/CD, architecture, velocity, artifact evidence, and explicit unavailable-data notes have been applied. "
        "Final client delivery still requires human review."
        + quality_note
    )


def _fallback_markdown(result: dict[str, Any]) -> str:
    maturity = result.get("maturity_signal") or {}
    lines = [
        f"# Express Technical Health Assessment — {result.get('repository') or result.get('source_scope') or 'authorized repository'}",
        "",
        "## Executive Summary",
        str(result.get("executive_summary") or "No executive summary returned."),
        "",
        "## Final Maturity Signal",
        f"- Level: {maturity.get('level', 'Unknown')}",
        f"- Score: {_safe_score(maturity.get('score'))}/100",
        "",
        "## Assessment Sections",
    ]
    for item in result.get("sections", []) or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('label') or item.get('id')}: {item.get('status', 'unknown')} {item.get('score', 'N/A')}/100")
    return "\n".join(lines).strip() + "\n"


def _rebuild_reports(result: dict[str, Any]) -> None:
    reports = dict(result.get("reports") or {})
    if _wants_es_mx(result):
        reports.update(reports_es_mx(result))
        pdf_base64, pdf_error = build_pdf_base64(reports["markdown"])
    else:
        try:
            markdown = build_markdown(result)
        except Exception:
            markdown = _fallback_markdown(result)
        reports["markdown"] = markdown
        reports["html"] = build_html(markdown)
        try:
            from nico.assessment_quality import _build_polished_pdf_base64

            pdf_base64, pdf_error = _build_polished_pdf_base64(result)
        except Exception:
            pdf_base64, pdf_error = build_pdf_base64(markdown)
    if pdf_base64:
        reports["pdf_base64"] = pdf_base64
        reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
    elif pdf_error:
        reports["pdf_error"] = pdf_error
    result["reports"] = reports


def finalize_express_result_consistency(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    _apply_final_score_adjustments(result)
    result["executive_summary"] = _build_executive_summary(result)
    result["score_source_of_truth"] = {
        "field": "maturity_signal",
        "level": (result.get("maturity_signal") or {}).get("level"),
        "score": (result.get("maturity_signal") or {}).get("score"),
        "rule": "Executive summary and report exports are rebuilt after final scoring and polishing.",
    }
    _rebuild_reports(result)
    return result
