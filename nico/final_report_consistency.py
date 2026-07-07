from __future__ import annotations

import re
from typing import Any

from nico.client_acceptance_evidence import apply_client_acceptance_evidence
from nico.hosted_assessment import build_html, build_markdown, build_pdf_base64
from nico.i18n_es_mx import reports_es_mx, wants_es_mx
from nico.project_trend_evidence import apply_project_trend_evidence
from nico.score_details import attach_score_details


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


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next((item for item in result.get("sections", []) or [] if isinstance(item, dict) and item.get("id") == section_id), None)


def _section_score(result: dict[str, Any], section_id: str) -> int:
    item = _section(result, section_id)
    return int(item.get("score") or 0) if item else 0


def _section_text(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    values = []
    for key in ("summary", "evidence", "findings", "unavailable"):
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value)
        else:
            values.append(str(value or ""))
    return "\n".join(values)


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


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


def _apply_code_audit_adjustment(result: dict[str, Any]) -> None:
    item = _section(result, "code_audit")
    if not item:
        return
    evidence_text = "\n".join(str(note) for note in item.get("evidence", []) or [])
    finding_text = "\n".join(str(note) for note in item.get("findings", []) or [])
    has_clean_marker_evidence = "actionable TODO/FIXME/security markers=0" in evidence_text
    has_actionable_marker_finding = "TODO/FIXME/security-note markers require triage" in finding_text
    has_production_risk = "production-risk=" in evidence_text and "production-risk=0" not in evidence_text
    if has_clean_marker_evidence and not has_actionable_marker_finding and not has_production_risk:
        item["score"] = max(int(item.get("score") or 0), 86)
        item["status"] = _status_from_score(int(item["score"]))
        item["summary"] = "Code audit uses recent commit/PR metadata plus hosted source-pattern review from the authorized repository; generic security wording is excluded from actionable marker scoring."


def _apply_dependency_evidence_adjustment(result: dict[str, Any]) -> None:
    item = _section(result, "dependency_health")
    if not item:
        return
    text = _section_text(item).lower()
    has_manifest_evidence = "requirements.txt found" in text and "package.json found" in text
    has_lockfile_evidence = "lockfile evidence found" in text or "package-lock.json" in text or "pnpm-lock.yaml" in text or "yarn.lock" in text
    has_clean_osv_evidence = "osv returned no vulnerability records" in text
    has_broad_range_warning = "[standard]>=" in text or "broad-range warnings" in text
    if not (has_manifest_evidence and has_lockfile_evidence):
        return
    item.setdefault("evidence", [])
    if has_clean_osv_evidence:
        item["findings"] = [note for note in item.get("findings", []) or [] if "osv returned no vulnerability records" not in str(note).lower()]
        _append_unique(item["evidence"], "Dependency evidence classification: clean OSV no-vulnerability output, Python manifest evidence, npm manifest evidence, and JavaScript lockfile evidence are present.")
        item["score"] = max(int(item.get("score") or 0), 86)
    elif has_broad_range_warning and int(item.get("score") or 0) >= 78:
        _append_unique(item["evidence"], "Dependency evidence classification: manifest and lockfile evidence are present; broad OSV range warnings remain disclosed but are not treated as confirmed installed-package vulnerabilities without audit artifacts.")
        item["score"] = max(int(item.get("score") or 0), 88)
    else:
        return
    _append_unique(item["unavailable"], "Full pip-audit, npm audit, and OSV Scanner CLI artifacts are still required before claiming final scanner-clean dependency status.")
    item["status"] = _status_from_score(int(item["score"]))
    item["summary"] = "Dependency review uses manifest evidence, JavaScript lockfile evidence, and OSV evidence while keeping scanner-worker limitations disclosed."


def _apply_static_evidence_adjustment(result: dict[str, Any]) -> None:
    static = _section(result, "static_analysis")
    ci = _section(result, "ci_cd")
    if not static:
        return
    static_text = _section_text(static).lower()
    ci_text = _section_text(ci).lower()
    built_in_clean = "built-in static risk-pattern hits: 0" in static_text and not static.get("findings")
    ci_static_evidence = any(marker in ci_text for marker in ["npm run lint", "eslint", "typescript", "typecheck", "test, lint, or build", "next build", "production build"])
    if not built_in_clean:
        return
    static.setdefault("evidence", [])
    if ci_static_evidence:
        _append_unique(static["evidence"], "Static evidence classification: built-in static risk-pattern hits are zero, and CI workflow evidence includes lint/typecheck/build coverage.")
        _append_unique(static["unavailable"], "External Semgrep/Bandit scanner-worker execution remains unavailable; CI-backed lint/typecheck/build evidence is counted separately from full scanner-worker proof.")
        static["score"] = max(int(static.get("score") or 0), 86)
        static["summary"] = "Static analysis uses clean built-in pattern checks plus CI-backed lint/typecheck/build evidence, while keeping unavailable external scanner-worker execution disclosed."
    else:
        _append_unique(static["evidence"], "Static evidence classification: built-in static risk-pattern hits are zero, but external analyzer proof is still unavailable.")
        static["score"] = max(int(static.get("score") or 0), 75)
    static["status"] = _status_from_score(int(static["score"]))


def _extract_ratio(text: str) -> float | None:
    match = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_count(label: str, text: str) -> int | None:
    match = re.search(label + r"\s*:\s*([0-9]+)", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _apply_velocity_traceability_adjustment(result: dict[str, Any]) -> None:
    velocity = _section(result, "velocity_complexity")
    if not velocity:
        return
    text = _section_text(velocity)
    lower = text.lower()
    commits = _extract_count("commit velocity", lower)
    ratio = _extract_ratio(lower) if "pull request traceability ratio" in lower else None
    strong_traceability = (commits or 0) >= 50 and (ratio or 0) >= 0.5
    supporting_sections_green = (
        _section_score(result, "code_audit") >= 86
        and _section_score(result, "dependency_health") >= 86
        and _section_score(result, "static_analysis") >= 86
        and _section_score(result, "ci_cd") >= 90
        and _section_score(result, "architecture_debt") >= 90
    )
    if not (strong_traceability and supporting_sections_green):
        return
    velocity.setdefault("evidence", [])
    _append_unique(velocity["evidence"], "Velocity interpretation: high PR/commit traceability plus green code, dependency, static-analysis, CI/CD, and architecture evidence mitigates the large source footprint for Express-level maturity scoring.")
    _append_unique(velocity["unavailable"], "Precise story points, reviewer seniority, project trend history, and client acceptance still require retained history and human review before client-final delivery claims.")
    velocity["score"] = max(int(velocity.get("score") or 0), 82)
    velocity["status"] = _status_from_score(int(velocity["score"]))
    velocity["summary"] = "Work-vs-expected signal uses commit velocity, PR traceability, source footprint, and supporting green evidence from code, dependency, static-analysis, CI/CD, and architecture sections."


def _release_readiness_signals(result: dict[str, Any]) -> dict[str, Any]:
    code = _section_score(result, "code_audit")
    deps = _section_score(result, "dependency_health")
    secrets = _section_score(result, "secrets_review")
    static = _section_score(result, "static_analysis")
    ci = _section_score(result, "ci_cd")
    arch = _section_score(result, "architecture_debt")
    velocity = _section(result, "velocity_complexity")
    velocity_text = _section_text(velocity)
    text = "\n".join(_section_text(_section(result, section_id)) for section_id in [
        "code_audit", "dependency_health", "secrets_review", "static_analysis", "ci_cd", "architecture_debt", "velocity_complexity"
    ]).lower()
    release_evidence = {
        "code_audit_green": code >= 86,
        "dependency_evidence_clean": deps >= 88 and "pip-audit" in text and "npm-audit" in text,
        "secret_evidence_clean": secrets >= 90 and "gitleaks" in text and "credential-scan" in text,
        "static_analysis_green": static >= 86,
        "ci_artifacts_green": ci >= 95 and ("artifact" in text or "workflow runs returned" in text),
        "architecture_green": arch >= 90,
        "pr_traceability_present": "pull request traceability ratio:" in velocity_text.lower() and " prs / " in velocity_text.lower(),
        "commit_velocity_present": "commit velocity:" in velocity_text.lower(),
    }
    passed = [name for name, ok in release_evidence.items() if ok]
    missing = [name for name, ok in release_evidence.items() if not ok]
    return {"ready": len(missing) == 0, "passed": passed, "missing": missing, "signals": release_evidence}


def _apply_release_readiness_adjustment(result: dict[str, Any]) -> None:
    readiness = _release_readiness_signals(result)
    result["release_readiness"] = {
        "status": "provisionally_ready_for_human_review" if readiness["ready"] else "evidence_incomplete",
        "passed_signals": readiness["passed"],
        "missing_signals": readiness["missing"],
        "rule": "Release-readiness can lift Velocity / Complexity only when code, dependency, secret, static, CI, architecture, commit velocity, and PR traceability evidence are present and green.",
    }
    velocity = _section(result, "velocity_complexity")
    if not velocity or not readiness["ready"]:
        return
    velocity.setdefault("evidence", [])
    _append_unique(velocity["evidence"], "Release-readiness evidence: clean code markers, clean dependency artifacts, clean secret artifacts, static-analysis evidence, CI artifact evidence, green architecture, commit velocity, and PR traceability are all present.")
    _append_unique(velocity["evidence"], "Why not higher: precise story-point estimates, reviewer seniority, business-value mapping, and acceptance evidence still require human review.")
    velocity["score"] = max(int(velocity.get("score") or 0), 90)
    velocity["status"] = _status_from_score(int(velocity["score"]))
    velocity["summary"] = "Work-vs-expected signal uses velocity, PR traceability, source footprint, and final release-readiness evidence from clean CI/security/dependency artifacts."


def _apply_final_score_adjustments(result: dict[str, Any]) -> None:
    _apply_code_audit_adjustment(result)
    _apply_dependency_evidence_adjustment(result)
    _apply_static_evidence_adjustment(result)
    _apply_velocity_traceability_adjustment(result)
    _apply_release_readiness_adjustment(result)
    apply_project_trend_evidence(result)
    apply_client_acceptance_evidence(result)
    _apply_static_evidence_adjustment(result)
    _apply_velocity_traceability_adjustment(result)
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
            "El puntaje se basa en la evidencia final después de aplicar auditoría de código, dependencias, secretos, análisis estático, CI/CD, arquitectura, velocidad, evidencia de artefactos, historial de proyecto cuando está disponible, aceptación cuando existe y notas explícitas de datos no disponibles. "
            "La entrega final a cliente todavía requiere revisión humana."
            + (" Algunos metadatos de GitHub no estuvieron disponibles, por lo que las secciones afectadas se degradan en vez de tratarse como evidencia negativa final." if quality_note else "")
        )
    return (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repo}. "
        f"The final maturity signal is {level} ({score}/100). "
        "Scores are generated from the final evidence-bound result after code audit, dependency, secrets, static analysis, CI/CD, architecture, velocity, artifact evidence, retained project history when available, acceptance when approved, and explicit unavailable-data notes have been applied. "
        "Final delivery still requires human review."
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
    result = attach_score_details(result)
    _rebuild_reports(result)
    return result
