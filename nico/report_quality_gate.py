from __future__ import annotations

import base64
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.storage import utc_now

REPORT_QUALITY_GATE_VERSION = "nico.report_quality_gate.v1"
_EXPRESS_MARKER = "_nico_report_quality_gate_express_v1"
_MID_MARKER = "_nico_report_quality_gate_mid_v1"
_FULL_MARKER = "_nico_report_quality_gate_full_v1"
_PLACEHOLDER_RE = re.compile(
    r"\b(?:lorem ipsum|todo(?:\b|:)|tbd(?:\b|:)|insert (?:text|summary|finding)|placeholder text|coming soon)\b",
    re.IGNORECASE,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    return [" ".join(str(item or "").split()) for item in _list(value) if str(item or "").strip()]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return " ".join(str(value or "").split())


def _score(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    section_id: str = "",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "section_id": section_id,
    }


def _summary_text(payload: dict[str, Any]) -> str:
    return _text(payload.get("decision_summary") or payload.get("executive_summary"))


def _sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(payload.get("sections")) if isinstance(item, dict)]


def evaluate_report_payload(payload: dict[str, Any], tier: str) -> dict[str, Any]:
    """Evaluate evidence truth, completeness, consistency, and presentation readiness.

    The gate is deterministic and never invents missing evidence. Critical issues
    block the draft package. Warnings remain visible to the human reviewer and
    lower the quality score without converting unavailable evidence into a pass.
    """

    normalized_tier = str(tier or "unknown").strip().lower()
    issues: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    run_id = str(payload.get("run_id") or payload.get("assessment_id") or payload.get("report_run_id") or "")
    repository = str(payload.get("repository") or payload.get("source_scope") or "")
    snapshot = str(payload.get("snapshot_commit_sha") or payload.get("commit_sha") or "")
    checks["identity"] = {
        "run_id": bool(run_id),
        "repository": bool(repository),
        "snapshot_commit": bool(snapshot),
    }
    if not run_id:
        issues.append(_issue("critical", "missing_run_identity", "The report is not bound to an exact assessment run."))
    if not repository:
        issues.append(_issue("critical", "missing_repository_identity", "The report does not identify the assessed repository."))
    if normalized_tier in {"mid", "full"} and not snapshot:
        issues.append(_issue("critical", "missing_snapshot_identity", "Mid and Full reports must identify the exact assessed commit."))

    summary = _summary_text(payload)
    checks["decision_summary_length"] = len(summary)
    if len(summary) < 40:
        issues.append(_issue("critical", "missing_decision_summary", "A decision-ready executive summary was not generated."))
    elif len(summary) < 160:
        issues.append(_issue("warning", "thin_decision_summary", "The executive summary is shorter than the professional decision-support target."))

    sections = _sections(payload)
    checks["section_count"] = len(sections)
    if not sections:
        issues.append(_issue("critical", "missing_assessment_sections", "No evidence-bound assessment sections were retained."))
    expected_minimum = 7 if normalized_tier in {"mid", "full"} else 4
    if sections and len(sections) < expected_minimum:
        issues.append(_issue("warning", "limited_section_coverage", f"{normalized_tier.title()} report contains {len(sections)} section(s); expected at least {expected_minimum} for normal depth."))

    scored_sections = 0
    evidence_bearing_sections = 0
    limitation_bearing_sections = 0
    for index, section in enumerate(sections):
        section_id = str(section.get("id") or f"section_{index + 1}")
        label = str(section.get("label") or "").strip()
        section_summary = _text(section.get("summary"))
        evidence = _texts(section.get("evidence")) + _texts(section.get("verified_claims"))
        findings = _texts(section.get("findings"))
        limitations = (
            _texts(section.get("unavailable"))
            + _texts(section.get("missing_evidence_sources"))
            + _texts(section.get("failed_evidence_tools"))
            + _texts(section.get("unverified_claims"))
        )
        score = section.get("score")
        if score is not None:
            scored_sections += 1
            if _score(score) is None:
                issues.append(_issue("critical", "invalid_section_score", "Section score is outside the 0–100 range.", section_id=section_id))
        if evidence:
            evidence_bearing_sections += 1
        if limitations:
            limitation_bearing_sections += 1
        if not label:
            issues.append(_issue("warning", "missing_section_label", "Section label is missing.", section_id=section_id))
        if len(section_summary) < 35:
            issues.append(_issue("warning", "thin_section_summary", "Section summary is too short for a professional evidence interpretation.", section_id=section_id))
        if not evidence and not limitations:
            issues.append(_issue("critical", "unsupported_section_conclusion", "Section contains neither retained evidence nor an explicit unavailable-evidence disclosure.", section_id=section_id))
        if findings and not evidence and not limitations:
            issues.append(_issue("critical", "finding_without_evidence_boundary", "A finding was retained without evidence or an explicit limitation boundary.", section_id=section_id))
        truth_status = str(section.get("truth_status") or section.get("status") or "")
        if not truth_status:
            issues.append(_issue("warning", "missing_truth_status", "Section does not disclose its evidence/truth status.", section_id=section_id))
        if _PLACEHOLDER_RE.search(_text(section)):
            issues.append(_issue("critical", "placeholder_content", "Placeholder language remains in a client-visible section.", section_id=section_id))

    checks["scored_section_count"] = scored_sections
    checks["evidence_bearing_section_count"] = evidence_bearing_sections
    checks["limitation_bearing_section_count"] = limitation_bearing_sections

    coverage = _dict(payload.get("evidence_coverage"))
    coverage_percent = coverage.get("percent")
    numerator = coverage.get("numerator")
    denominator = coverage.get("denominator")
    checks["evidence_coverage"] = deepcopy(coverage)
    if coverage:
        try:
            percent = float(coverage_percent)
            num = int(numerator)
            den = int(denominator)
            if not 0 <= percent <= 100 or num < 0 or den < 0 or num > den:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(_issue("critical", "invalid_evidence_coverage", "Evidence coverage values are internally inconsistent."))
    else:
        issues.append(_issue("warning", "missing_evidence_coverage", "The report does not disclose automated evidence coverage."))

    integrity = _dict(payload.get("score_integrity"))
    checks["score_integrity"] = deepcopy(integrity)
    if integrity.get("score_match") is False:
        issues.append(_issue("critical", "score_integrity_mismatch", "Reported technical score does not match the retained weighted calculation."))
    technical_score = payload.get("technical_score") or _dict(payload.get("maturity_signal")).get("score")
    if technical_score is not None and _score(technical_score) is None:
        issues.append(_issue("critical", "invalid_technical_score", "Technical score is outside the 0–100 range."))

    decision = _dict(payload.get("decision_summary"))
    recommended_actions = _texts(decision.get("recommended_actions")) + _texts(payload.get("next_steps"))
    checks["recommended_action_count"] = len(recommended_actions)
    if normalized_tier in {"mid", "full"} and not recommended_actions:
        issues.append(_issue("warning", "missing_recommended_actions", "No prioritized evidence-bound next actions were generated."))

    unsupported = int(payload.get("unsupported_claims_permitted") or 0)
    human_review = bool(payload.get("human_review_required", True))
    delivery_allowed = bool(payload.get("client_delivery_allowed", payload.get("client_ready", False)))
    checks["safety_boundary"] = {
        "unsupported_claims_permitted": unsupported,
        "human_review_required": human_review,
        "client_delivery_allowed": delivery_allowed,
    }
    if unsupported != 0:
        issues.append(_issue("critical", "unsupported_claims_permitted", "The report contract permits unsupported claims."))
    if not human_review:
        issues.append(_issue("critical", "human_review_gate_missing", "Human review is not required by the draft report contract."))
    if delivery_allowed:
        issues.append(_issue("critical", "premature_client_delivery", "A draft report is marked as client-deliverable before human approval."))
    if _PLACEHOLDER_RE.search(_text(payload)):
        issues.append(_issue("critical", "placeholder_content", "Placeholder language remains in the report package."))

    critical = [item for item in issues if item["severity"] == "critical"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    quality_score = max(0, min(100, 100 - len(critical) * 24 - len(warnings) * 4))
    status = "blocked" if critical else "ready_for_human_review" if quality_score >= 84 else "review_required"
    return {
        "version": REPORT_QUALITY_GATE_VERSION,
        "status": status,
        "tier": normalized_tier,
        "quality_score": quality_score,
        "critical_issue_count": len(critical),
        "warning_count": len(warnings),
        "issues": issues,
        "checks": checks,
        "generated_at": utc_now(),
        "claims_invented": False,
        "missing_evidence_converted_to_pass": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def evaluate_rendered_formats(formats: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    markdown = str(formats.get("markdown") or "")
    html = str(formats.get("html") or "")
    pdf_value = formats.get("pdf") or formats.get("pdf_base64") or ""
    try:
        pdf = base64.b64decode(str(pdf_value), validate=True) if pdf_value else b""
    except Exception:
        pdf = b""
    if len(markdown.strip()) < 500 or "#" not in markdown:
        issues.append(_issue("critical", "invalid_markdown_export", "Markdown export is missing or materially incomplete."))
    if len(html.strip()) < 500 or "<html" not in html.lower() or "</html>" not in html.lower():
        issues.append(_issue("critical", "invalid_html_export", "HTML export is missing or materially incomplete."))
    if not pdf.startswith(b"%PDF") or len(pdf) < 1500:
        issues.append(_issue("critical", "invalid_pdf_export", "PDF export is missing, truncated, or invalid."))
    if "<script" in html.lower():
        issues.append(_issue("critical", "unsafe_html_export", "Client-visible HTML contains executable script content."))
    return {
        "status": "blocked" if issues else "verified",
        "issues": issues,
        "markdown_chars": len(markdown),
        "html_chars": len(html),
        "pdf_bytes": len(pdf),
        "pdf_signature_valid": pdf.startswith(b"%PDF"),
    }


def _report_parts(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    package = _dict(report.get("report_package"))
    package_formats = _dict(package.get("formats"))
    direct_formats = _dict(report.get("formats"))
    reports = _dict(report.get("reports"))
    if package_formats:
        formats = package_formats
        payload = _dict(package_formats.get("json")) or package
    elif direct_formats:
        formats = direct_formats
        payload = _dict(direct_formats.get("json")) or report
    elif reports:
        formats = reports
        payload = _dict(reports.get("json")) or package or report
    else:
        formats = {}
        payload = package or report
    return payload, formats


def audit_report_record(report: dict[str, Any], tier: str) -> dict[str, Any]:
    payload, formats = _report_parts(report)
    manifest = evaluate_report_payload(payload, tier)
    rendered = evaluate_rendered_formats(formats)
    manifest["rendered_formats"] = rendered
    rendered_issues = _list(rendered.get("issues"))
    if rendered_issues:
        manifest["issues"] = _list(manifest.get("issues")) + rendered_issues
        manifest["critical_issue_count"] = int(manifest.get("critical_issue_count") or 0) + len(rendered_issues)
        manifest["quality_score"] = max(0, int(manifest.get("quality_score") or 0) - len(rendered_issues) * 24)
        manifest["status"] = "blocked"
    return manifest


def _attach_manifest(payload: dict[str, Any], tier: str) -> dict[str, Any]:
    output = deepcopy(payload)
    manifest = evaluate_report_payload(output, tier)
    output["report_quality_manifest"] = manifest
    output["human_review_required"] = True
    output["client_ready"] = False
    if manifest["status"] == "blocked":
        output["report_quality_blocked"] = True
    return output


def install_report_quality_gate() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import full_assessment_idempotent_handlers as full_handlers
    from nico import mid_assessment_api
    from nico import mid_assessment_report

    express_current: Callable[..., dict[str, Any]] = assessment_quality.polish_express_result
    if not getattr(express_current, _EXPRESS_MARKER, False):
        @wraps(express_current)
        def express_with_quality(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return _attach_manifest(express_current(*args, **kwargs), "express")

        setattr(express_with_quality, _EXPRESS_MARKER, True)
        setattr(express_with_quality, "_nico_previous", express_current)
        assessment_quality.polish_express_result = express_with_quality

    mid_current: Callable[..., dict[str, Any]] = mid_assessment_report.generate_mid_draft_report
    if not getattr(mid_current, _MID_MARKER, False):
        @wraps(mid_current)
        def mid_with_quality(*args: Any, **kwargs: Any) -> dict[str, Any]:
            report = mid_current(*args, **kwargs)
            if report.get("status") != "complete":
                return report
            audited = deepcopy(report)
            manifest = audit_report_record(audited, "mid")
            audited["report_quality_manifest"] = manifest
            formats = _dict(audited.get("formats"))
            json_payload = _dict(formats.get("json"))
            if json_payload:
                json_payload["report_quality_manifest"] = deepcopy(manifest)
                formats["json"] = json_payload
                audited["formats"] = formats
            audited["human_review_required"] = True
            audited["client_delivery_allowed"] = False
            if manifest["status"] == "blocked":
                audited["status"] = "blocked"
                audited["error"] = "Report quality gate blocked the Mid draft because required identity, evidence, score integrity, or rendered-format checks failed."
            active = kwargs.get("store") or mid_assessment_report.STORE
            report_id = str(audited.get("report_id") or "")
            if report_id:
                active.put("reports", report_id, audited)
            return audited

        setattr(mid_with_quality, _MID_MARKER, True)
        setattr(mid_with_quality, "_nico_previous", mid_current)
        mid_assessment_report.generate_mid_draft_report = mid_with_quality
        # mid_assessment_api imports the renderer directly, so update the bound
        # symbol used by automatic same-run report generation as well.
        mid_assessment_api.generate_mid_draft_report = mid_with_quality

    full_current: Callable[..., dict[str, Any]] = full_handlers._reports_handler
    if not getattr(full_current, _FULL_MARKER, False):
        @wraps(full_current)
        def full_with_quality(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = full_current(*args, **kwargs)
            if result.get("status") != "complete":
                return result
            output = deepcopy(result)
            reports = _dict(output.get("reports"))
            package = _dict(output.get("report_package"))
            manifest = audit_report_record({"reports": reports, "report_package": package}, "full")
            output["report_quality_manifest"] = manifest
            package["report_quality_manifest"] = deepcopy(manifest)
            reports["report_quality_manifest"] = deepcopy(manifest)
            output["report_package"] = package
            output["reports"] = reports
            if manifest["status"] == "blocked":
                output["status"] = "blocked"
                output["error"] = "Report quality gate blocked the Full draft because required identity, evidence, score integrity, or rendered-format checks failed."
            report_id = str(package.get("report_id") or "")
            if report_id:
                from nico.storage import STORE

                STORE.put("reports", report_id, package)
            return output

        setattr(full_with_quality, _FULL_MARKER, True)
        setattr(full_with_quality, "_nico_previous", full_current)
        full_handlers._reports_handler = full_with_quality

    return {
        "status": "installed",
        "version": REPORT_QUALITY_GATE_VERSION,
        "express_quality_manifest": True,
        "mid_rendered_format_gate": True,
        "mid_automatic_report_binding": True,
        "full_rendered_format_gate": True,
        "unsupported_claims_blocked": True,
        "score_integrity_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "REPORT_QUALITY_GATE_VERSION",
    "audit_report_record",
    "evaluate_rendered_formats",
    "evaluate_report_payload",
    "install_report_quality_gate",
]
