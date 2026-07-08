from __future__ import annotations

import re
from typing import Any

from nico.client_acceptance_evidence import apply_client_acceptance_evidence
from nico.evidence_status import apply_report_evidence_status
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


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(part or "") for part in value)
    if isinstance(value, dict):
        return "\n".join(_list_text(part) for part in value.values())
    return str(value or "")


def _section_text(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return "\n".join(_list_text(item.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _evidence_text(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return "\n".join(_list_text(item.get(key)) for key in ("summary", "evidence"))


def _findings_text(item: dict[str, Any] | None) -> str:
    return _list_text((item or {}).get("findings"))


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _has_blocking_findings(item: dict[str, Any] | None, ignored_markers: tuple[str, ...] = ()) -> bool:
    if not item:
        return False
    for finding in item.get("findings", []) or []:
        text = str(finding or "").lower()
        if not text.strip():
            continue
        if any(marker in text for marker in ignored_markers):
            continue
        return True
    return False


def _has_osv_vulnerability(item: dict[str, Any] | None) -> bool:
    text = (_evidence_text(item) + "\n" + _findings_text(item)).lower()
    return "osv returned" in text and "vulnerability record" in text and "no vulnerability records" not in text


def _has_clean_dependency_audit_artifacts(item: dict[str, Any] | None) -> bool:
    evidence = _evidence_text(item).lower()
    has_zero_audit = "zero dependency vulnerabilities" in evidence and (
        "pip-audit" in evidence or "npm-audit" in evidence or "osv scanner" in evidence or "osv-scanner" in evidence
    )
    return has_zero_audit and not _has_osv_vulnerability(item)


def _has_clean_secret_artifacts(item: dict[str, Any] | None) -> bool:
    evidence = _evidence_text(item).lower()
    has_clean_zero = "zero high-confidence" in evidence or "zero credential findings" in evidence
    return "credential-scan" in evidence and "gitleaks" in evidence and has_clean_zero


def _has_static_review_findings(item: dict[str, Any] | None) -> bool:
    findings = _findings_text(item).lower()
    return any(marker in findings for marker in ("needs_human_review", "bandit triage", "parsed bandit artifact reported", "finding(s)"))


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [
        item for item in result.get("sections", [])
        if isinstance(item, dict)
        and item.get("status") != "gray"
        and item.get("supplemental") is not True
        and int(item.get("scoring_weight", 1) or 0) != 0
    ]
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
    evidence = _evidence_text(item).lower()
    has_manifest_evidence = "requirements.txt found" in text and "package.json found" in text
    has_lockfile_evidence = "lockfile evidence found" in text or "package-lock.json" in text or "pnpm-lock.yaml" in text or "yarn.lock" in text
    has_clean_osv_evidence = "osv returned no vulnerability records" in evidence
    has_clean_audit_artifacts = _has_clean_dependency_audit_artifacts(item)
    has_broad_range_warning = "[standard]>=" in text or "broad-range warnings" in text
    has_osv_vulnerabilities = _has_osv_vulnerability(item)
    if not (has_manifest_evidence and has_lockfile_evidence):
        return
    item.setdefault("evidence", [])
    if has_clean_audit_artifacts:
        item["findings"] = [note for note in item.get("findings", []) or [] if "osv returned" not in str(note).lower()]
        _append_unique(item["evidence"], "Dependency evidence classification: parsed pip-audit and npm-audit artifacts reported zero dependency vulnerabilities for the assessed artifact set.")
        item["score"] = max(int(item.get("score") or 0), 90)
    elif has_clean_osv_evidence and not has_osv_vulnerabilities:
        item["findings"] = [note for note in item.get("findings", []) or [] if "osv returned no vulnerability records" not in str(note).lower()]
        _append_unique(item["evidence"], "Dependency evidence classification: clean OSV no-vulnerability output, Python manifest evidence, npm manifest evidence, and JavaScript lockfile evidence are present.")
        item["score"] = max(int(item.get("score") or 0), 86)
    elif has_osv_vulnerabilities and int(item.get("score") or 0) >= 86:
        _append_unique(item["evidence"], "Dependency evidence classification: OSV API evidence completed with vulnerability records; final scanner-clean status is not claimed without pip-audit, npm audit, and OSV Scanner artifacts.")
        item["score"] = max(int(item.get("score") or 0), 88)
    elif has_broad_range_warning and int(item.get("score") or 0) >= 78:
        _append_unique(item["evidence"], "Dependency evidence classification: manifest and lockfile evidence are present; broad OSV range warnings remain disclosed but are not treated as confirmed installed-package vulnerabilities without audit artifacts.")
        item["score"] = max(int(item.get("score") or 0), 88)
    else:
        return
    if not has_clean_audit_artifacts:
        item.setdefault("unavailable", [])
        _append_unique(item["unavailable"], "Full pip-audit, npm audit, and OSV Scanner CLI artifacts are still required before claiming final scanner-clean dependency status.")
    item["status"] = _status_from_score(int(item["score"]))
    item["summary"] = "Dependency review uses available manifest, lockfile, OSV, and audit-artifact evidence while separating runtime scanner proof from final scanner-clean claims."


def _apply_secret_evidence_adjustment(result: dict[str, Any]) -> None:
    item = _section(result, "secrets_review")
    if not item:
        return
    has_clean_artifacts = _has_clean_secret_artifacts(item)
    blocking_findings = _has_blocking_findings(
        item,
        (
            "generic token-name pattern matches",
            "false-positive",
            "full git-history",
            "requires a sandboxed worker",
            "hosted mode currently scans",
            "not verified",
            "source distinction",
        ),
    )
    if not has_clean_artifacts or blocking_findings:
        return
    item.setdefault("evidence", [])
    _append_unique(item["evidence"], "Secrets evidence classification: parsed credential-scan and gitleaks artifacts reported zero high-confidence credential findings for this run.")
    item["score"] = max(int(item.get("score") or 0), 90)
    item["status"] = _status_from_score(int(item["score"]))
    item["summary"] = "Secrets review uses built-in masked secret-pattern detection plus parsed credential-scan and gitleaks artifacts when available; full git-history limits remain disclosed."


def _apply_static_evidence_adjustment(result: dict[str, Any]) -> None:
    static = _section(result, "static_analysis")
    ci = _section(result, "ci_cd")
    if not static:
        return
    static_text = _section_text(static).lower()
    ci_text = _section_text(ci).lower()
    built_in_clean = "built-in static risk-pattern hits: 0" in static_text
    has_blocking_static_findings = _has_blocking_findings(
        static,
        (
            "semgrep",
            "bandit",
            "eslint",
            "typescript",
            "external analyzer",
            "external scanner",
            "scanner-worker",
            "sandboxed worker",
            "not yet executed",
            "unavailable",
            "source distinction",
            "needs_human_review",
            "triage summary",
        ),
    )
    ci_static_evidence = _section_score(result, "ci_cd") >= 90 or any(
        marker in ci_text
        for marker in ["npm run lint", "eslint", "typescript", "typecheck", "test, lint, or build", "next build", "production build"]
    )
    if not built_in_clean or has_blocking_static_findings:
        return
    static.setdefault("evidence", [])
    if ci_static_evidence:
        _append_unique(static["evidence"], "Static evidence classification: built-in static risk-pattern hits are zero, and CI/CD is green or includes lint/typecheck/build coverage.")
        static.setdefault("unavailable", [])
        _append_unique(static["unavailable"], "External Semgrep/Bandit scanner-worker execution remains unavailable; CI-backed evidence is counted separately from full scanner-worker proof.")
        static["score"] = max(int(static.get("score") or 0), 86)
        static["summary"] = "Static analysis uses clean built-in pattern checks plus green CI/CD or lint/typecheck/build evidence, while keeping unavailable external scanner-worker execution disclosed."
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
    _append_unique(velocity["evidence"], "Velocity interpretation: high PR/commit traceability plus available code, dependency, static-analysis, CI/CD, and architecture evidence supports Express-level maturity scoring while disclosed findings and missing runtime artifacts remain separate from final-clean claims.")
    velocity.setdefault("unavailable", [])
    _append_unique(velocity["unavailable"], "Precise story points, reviewer seniority, project trend history, and client acceptance still require retained history and human review before client-final delivery claims.")
    velocity["score"] = max(int(velocity.get("score") or 0), 82)
    velocity["status"] = _status_from_score(int(velocity["score"]))
    velocity["summary"] = "Work-vs-expected signal uses commit velocity, PR traceability, source footprint, and available supporting evidence from code, dependency, static-analysis, CI/CD, and architecture sections."


def _release_readiness_signals(result: dict[str, Any]) -> dict[str, Any]:
    code = _section_score(result, "code_audit")
    dependency = _section(result, "dependency_health")
    secrets_section = _section(result, "secrets_review")
    static_section = _section(result, "static_analysis")
    ci = _section_score(result, "ci_cd")
    arch = _section_score(result, "architecture_debt")
    velocity = _section(result, "velocity_complexity")
    velocity_text = _section_text(velocity).lower()
    ci_text = _section_text(_section(result, "ci_cd")).lower()
    release_evidence = {
        "code_audit_green": code >= 86,
        "dependency_scanner_clean_artifacts_attached": _section_score(result, "dependency_health") >= 88 and _has_clean_dependency_audit_artifacts(dependency),
        "dependency_no_osv_vulnerabilities": not _has_osv_vulnerability(dependency),
        "secret_evidence_clean": _section_score(result, "secrets_review") >= 90 and _has_clean_secret_artifacts(secrets_section),
        "static_analysis_no_review_findings": _section_score(result, "static_analysis") >= 86 and not _has_static_review_findings(static_section),
        "ci_artifacts_green": ci >= 95 and ("workflow runs returned" in ci_text or "artifact" in ci_text),
        "architecture_green": arch >= 90,
        "pr_traceability_present": "pull request traceability ratio:" in velocity_text and " prs / " in velocity_text,
        "commit_velocity_present": "commit velocity:" in velocity_text,
    }
    passed = [name for name, ok in release_evidence.items() if ok]
    missing = [name for name, ok in release_evidence.items() if not ok]
    return {"ready": len(missing) == 0, "passed": passed, "missing": missing, "signals": release_evidence}


def _remove_untrue_release_clean_claims(velocity: dict[str, Any]) -> None:
    velocity["evidence"] = [
        item
        for item in velocity.get("evidence", []) or []
        if "clean dependency artifacts" not in str(item).lower()
        and "clean secret artifacts" not in str(item).lower()
        and "release-readiness evidence:" not in str(item).lower()
    ]
    velocity["summary"] = "Work-vs-expected signal uses velocity, PR traceability, source footprint, available supporting evidence, disclosed findings, and explicit missing runtime artifacts; it does not claim final release-readiness."


def _apply_release_readiness_adjustment(result: dict[str, Any]) -> None:
    readiness = _release_readiness_signals(result)
    result["release_readiness"] = {
        "status": "provisionally_ready_for_human_review" if readiness["ready"] else "evidence_incomplete",
        "passed_signals": readiness["passed"],
        "missing_signals": readiness["missing"],
        "rule": "Release-readiness can lift Velocity / Complexity only when clean dependency scanner artifacts, no OSV vulnerabilities, clean secret artifacts, static-analysis triage, CI, architecture, commit velocity, and PR traceability evidence are all present.",
    }
    velocity = _section(result, "velocity_complexity")
    if not velocity:
        return
    velocity.setdefault("evidence", [])
    velocity.setdefault("unavailable", [])
    if not readiness["ready"]:
        _remove_untrue_release_clean_claims(velocity)
        _append_unique(
            velocity["unavailable"],
            "Release-readiness lift not applied because required final-clean evidence is incomplete: " + ", ".join(readiness["missing"]),
        )
        return
    _append_unique(velocity["evidence"], "Release-readiness evidence: clean dependency scanner artifacts, no OSV vulnerabilities, clean secret artifacts, static-analysis triage, CI artifact evidence, green architecture, commit velocity, and PR traceability are all present.")
    _append_unique(velocity["evidence"], "Why not higher: precise story-point estimates, reviewer seniority, business-value mapping, and acceptance evidence still require human review.")
    velocity["score"] = max(int(velocity.get("score") or 0), 90)
    velocity["status"] = _status_from_score(int(velocity["score"]))
    velocity["summary"] = "Work-vs-expected signal uses velocity, PR traceability, source footprint, and verified release-readiness evidence from clean dependency, secret, static-analysis, CI, architecture, commit-velocity, and PR-traceability artifacts."


def _apply_truth_guard(result: dict[str, Any]) -> None:
    """Remove final-clean claims that are not supported by the current evidence set."""
    velocity = _section(result, "velocity_complexity")
    readiness = result.get("release_readiness") if isinstance(result.get("release_readiness"), dict) else {}
    if velocity and readiness.get("status") != "provisionally_ready_for_human_review":
        _remove_untrue_release_clean_claims(velocity)
    result["report_truth_guard"] = {
        "status": "applied",
        "rule": "Reports may describe available maturity evidence, but must not claim scanner-clean, release-ready, deployment-ready, or client-ready status unless the required runtime artifacts are attached for this run.",
        "blocked_claims": list((readiness or {}).get("missing_signals", [])),
    }


def _apply_final_score_adjustments(result: dict[str, Any]) -> None:
    _apply_code_audit_adjustment(result)
    _apply_dependency_evidence_adjustment(result)
    _apply_secret_evidence_adjustment(result)
    _apply_static_evidence_adjustment(result)
    _apply_velocity_traceability_adjustment(result)
    _apply_release_readiness_adjustment(result)
    apply_project_trend_evidence(result)
    apply_client_acceptance_evidence(result)
    _apply_secret_evidence_adjustment(result)
    _apply_static_evidence_adjustment(result)
    _apply_velocity_traceability_adjustment(result)
    _apply_release_readiness_adjustment(result)
    apply_report_evidence_status(result)
    _apply_release_readiness_adjustment(result)
    _apply_truth_guard(result)
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
        "rule": "Executive summary and report exports are rebuilt after final scoring, evidence classification, truth-guard checks, and polishing.",
    }
    result = attach_score_details(result)
    _rebuild_reports(result)
    return result
