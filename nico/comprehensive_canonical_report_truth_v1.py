from __future__ import annotations

import base64
import hashlib
import io
import math
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_canonical_report_truth.v1"
_PATCH_MARKER = "_nico_comprehensive_canonical_report_truth_v1"
PRODUCT_NAME = "NICO Comprehensive Technical Assessment"

_PRODUCT_REPLACEMENTS = (
    ("Why this is broader than Express", "Why this assessment is comprehensive"),
    ("retains the Express technical-health baseline and adds", "combines repository health with"),
    ("The Comprehensive package retains the Express technical-health baseline and adds", "The Comprehensive assessment combines repository health with"),
    ("to the Express baseline", "within the Comprehensive assessment"),
    ("Express and Comprehensive complete", "The Comprehensive assessment completes"),
    ("Express and Comprehensive", "Comprehensive"),
    ("Express technical-health baseline", "repository technical-health baseline"),
)

_FINAL_SUFFIX_RE = re.compile(r"(?:-FINAL-PENDING-APPROVAL)+\.pdf$", re.IGNORECASE)
_DRAFT_SUFFIX_RE = re.compile(r"(?:-DRAFT)?\.pdf$", re.IGNORECASE)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_product_text(value: str) -> str:
    output = value
    for old, new in _PRODUCT_REPLACEMENTS:
        output = output.replace(old, new)
    return output


def _clean_product_language(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_product_text(value)
    if isinstance(value, list):
        return [_clean_product_language(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clean_product_language(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _clean_product_language(item) for key, item in value.items()}
    return value


def _priority_rank(value: Any) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(str(value or "").upper(), 9)


def _confirmed_material_event(item: dict[str, Any]) -> bool:
    text = " ".join(
        _text(item.get(key)).casefold()
        for key in ("evidence", "fact", "impact", "business_impact", "interpretation")
    )
    confirmed = any(token in text for token in ("verified production incident", "confirmed outage", "confirmed exploit", "verified data loss"))
    return confirmed or item.get("release_blocker") is True and item.get("verified") is True


def _calibrate_finding(item: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(item)
    category = _text(output.get("category")).casefold()
    title = _text(output.get("title")).casefold()
    evidence = _text(output.get("evidence") or output.get("fact")).casefold()
    priority = str(output.get("priority") or "P3").upper()

    unverified = "verified=false" in evidence or str(output.get("verified")).casefold() == "false"
    complexity = category == "architecture" and "complexity hotspot" in title
    unclassified_ci = category == "ci_cd" and "historical" in title and "non-success" in title
    evidence_limitation = category == "evidence" or "evidence unavailable" in title or "did not produce a complete result" in title

    if (complexity or unclassified_ci or unverified) and priority in {"P0", "P1"} and not _confirmed_material_event(output):
        output["priority"] = "P2"
        output["severity_calibration_reason"] = "No verified production incident, exploit, outage, or data-loss event supports executive P1 classification."

    if evidence_limitation and priority in {"P0", "P1"}:
        output["priority"] = "P2"
        output["release_blocker"] = True
        output["assessment_blocker"] = True
        output["impact"] = (
            "This is an assessment-evidence limitation, not proof of a severe client-system defect. "
            "Dependent assurance and delivery remain blocked until the analyzer completes."
        )
        output["business_impact"] = output["impact"]
        output["severity_calibration_reason"] = "Required evidence failure is represented as a delivery blocker separately from technical severity."

    return output


def _calibrate_risks(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    for key in ("findings_register", "decision_grade_findings_register", "executive_risk_register"):
        records = [item for item in output.get(key) or [] if isinstance(item, dict)]
        calibrated = [_calibrate_finding(item) for item in records]
        calibrated.sort(key=lambda item: (_priority_rank(item.get("priority")), _text(item.get("title"))))
        output[key] = calibrated
    return output


def _weighted_technical_score(assessment: dict[str, Any]) -> tuple[int | None, list[dict[str, Any]]]:
    rows = [item for item in assessment.get("scoring_weights") or [] if isinstance(item, dict)]
    weighted_sum = 0.0
    active_weight = 0.0
    normalized: list[dict[str, Any]] = []
    if rows:
        for row in rows:
            score = row.get("technical_score")
            weight = row.get("weight")
            included = isinstance(score, (int, float)) and isinstance(weight, (int, float)) and float(weight) > 0
            normalized.append({**row, "included": included})
            if included:
                weighted_sum += float(score) * float(weight)
                active_weight += float(weight)
    else:
        sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
        weights = {
            "code_audit": 0.20,
            "dependency_health": 0.15,
            "secrets_review": 0.15,
            "static_analysis": 0.15,
            "ci_cd": 0.15,
            "architecture_debt": 0.15,
            "velocity_complexity": 0.05,
        }
        for section in sections:
            section_id = _text(section.get("id"))
            score = section.get("score_value", section.get("technical_score", section.get("score")))
            weight = weights.get(section_id, 0.0)
            included = isinstance(score, (int, float)) and weight > 0
            row = {
                "control": section.get("label") or section_id,
                "section_id": section_id,
                "weight": weight,
                "weight_percent": round(weight * 100),
                "technical_score": int(score) if included else None,
                "weighted_contribution": round(float(score) * weight, 2) if included else None,
                "assurance": section.get("assurance_label"),
                "included": included,
            }
            normalized.append(row)
            if included:
                weighted_sum += float(score) * weight
                active_weight += weight
    if active_weight <= 0:
        return None, normalized
    return round(weighted_sum / active_weight), normalized


def _review_limited_count(assessment: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    sections = {
        _text(item.get("id")): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict)
    }
    count = 0
    for row in rows:
        if not row.get("included"):
            continue
        section = sections.get(_text(row.get("section_id")), {})
        assurance = _text(row.get("assurance") or section.get("assurance_label")).upper()
        if assurance and assurance not in {"VERIFIED", "COMPLETE"}:
            count += 1
    return count


def _percent(completed: int, total: int) -> int | None:
    if total <= 0:
        return None
    return max(0, min(100, round((completed / total) * 100)))


def _evidence_completion_contract(
    assessment: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sections = {
        _text(item.get("id")): item
        for item in assessment.get("sections") or []
        if isinstance(item, dict)
    }
    controls = [
        row for row in rows
        if isinstance(row, dict) and float(row.get("weight") or 0) > 0
    ]
    processed = 0
    disposed = 0
    for row in controls:
        section = sections.get(_text(row.get("section_id")), {})
        score = row.get("technical_score")
        assurance = _text(row.get("assurance") or section.get("assurance_label"))
        unavailable = [item for item in section.get("unavailable") or [] if _text(item)]
        findings = [item for item in section.get("findings") or [] if _text(item)]
        has_machine_result = isinstance(score, (int, float)) or bool(assurance)
        has_explicit_disposition = has_machine_result or bool(unavailable) or bool(findings)
        processed += int(has_machine_result)
        disposed += int(has_explicit_disposition)

    health = assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {}
    completed_scanners = [item for item in health.get("completed_scanners") or [] if _text(item)]
    incomplete_scanners = [item for item in health.get("incomplete_scanners") or [] if isinstance(item, dict) or _text(item)]
    scanner_total = len(completed_scanners) + len(incomplete_scanners)

    legacy = assessment.get("evidence_coverage") if isinstance(assessment.get("evidence_coverage"), dict) else {}
    raw_overall = legacy.get("overall_percent", legacy.get("percent"))
    overall = int(round(float(raw_overall))) if isinstance(raw_overall, (int, float)) else None
    if overall is not None:
        overall = max(0, min(100, overall))

    automatable_percent = _percent(processed, len(controls))
    disposition_percent = _percent(disposed, len(controls))
    analyzer_percent = _percent(len(completed_scanners), scanner_total)
    gap = None if overall is None else max(0, 100 - overall)

    contract = {
        "version": VERSION,
        "automatable_repository_evidence": {
            "label": "Automatable repository evidence processed",
            "completed": processed,
            "total": len(controls),
            "percent": automatable_percent,
            "definition": "Standard repository evidence controls with a normalized machine result. This does not mean every analyzer succeeded.",
        },
        "required_evidence_disposition": {
            "label": "Required evidence disposition",
            "completed": disposed,
            "total": len(controls),
            "percent": disposition_percent,
            "definition": "Required repository controls with collected evidence or an explicit limitation, failure, or not-applicable disposition.",
        },
        "analyzer_completion": {
            "label": "Successful analyzer completion",
            "completed": len(completed_scanners),
            "total": scanner_total,
            "percent": analyzer_percent,
            "definition": "Configured analyzers that completed successfully. Failed or partial analyzers remain visible and can block approval.",
        },
        "overall_engagement_evidence": {
            "label": "Overall engagement evidence",
            "percent": overall,
            "gap_percent": gap,
            "definition": "Repository, runtime, infrastructure, stakeholder, business, and client-provided evidence available for this engagement.",
        },
        "full_automation_claim_allowed": bool(automatable_percent == 100 and processed == len(controls) and len(controls) > 0),
        "full_required_disposition_claim_allowed": bool(disposition_percent == 100 and disposed == len(controls) and len(controls) > 0),
        "full_engagement_coverage_claim_allowed": overall == 100,
        "missing_evidence_never_treated_as_clean": True,
        "single_source_of_truth": True,
    }
    return contract


def _evidence_contract_valid(contract: Any) -> bool:
    if not isinstance(contract, dict):
        return False
    for key in ("automatable_repository_evidence", "required_evidence_disposition", "analyzer_completion"):
        metric = contract.get(key)
        if not isinstance(metric, dict):
            return False
        completed = metric.get("completed")
        total = metric.get("total")
        percent = metric.get("percent")
        if not isinstance(completed, int) or not isinstance(total, int) or completed < 0 or total < 0 or completed > total:
            return False
        expected = _percent(completed, total)
        if percent != expected:
            return False
        if percent == 100 and not (total > 0 and completed == total):
            return False
    overall = contract.get("overall_engagement_evidence")
    if not isinstance(overall, dict):
        return False
    percent = overall.get("percent")
    if percent is not None and (not isinstance(percent, int) or not 0 <= percent <= 100):
        return False
    if contract.get("full_engagement_coverage_claim_allowed") is True and percent != 100:
        return False
    return contract.get("missing_evidence_never_treated_as_clean") is True


def apply_canonical_score_truth(assessment: dict[str, Any]) -> dict[str, Any]:
    output = _calibrate_risks(_clean_product_language(deepcopy(assessment)))
    technical, rows = _weighted_technical_score(output)
    limited_count = _review_limited_count(output, rows)
    penalty = min(10, math.ceil(limited_count * 2 / 3)) if technical is not None else 0
    adjusted = max(0, technical - penalty) if technical is not None else None

    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity.update(
        {
            "score": technical,
            "source_score": technical,
            "presented_score": technical,
            "technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "scoring_method": "canonical_weighted_controls_v1",
            "evidence_adjustment_method": "ceil(review_limited_scored_controls * 2 / 3), capped at 10 points",
        }
    )
    output["maturity_signal"] = maturity
    output["technical_score"] = technical
    output["evidence_adjusted_score"] = adjusted
    output["scoring_weights"] = rows
    evidence_contract = _evidence_completion_contract(output, rows)
    output["evidence_completion_contract"] = evidence_contract
    legacy_coverage = output.get("evidence_coverage") if isinstance(output.get("evidence_coverage"), dict) else {}
    overall_metric = evidence_contract["overall_engagement_evidence"]
    output["evidence_coverage"] = {
        **legacy_coverage,
        "calculated": True,
        "label": "Overall engagement evidence",
        "percent": overall_metric.get("percent"),
        "overall_percent": overall_metric.get("percent"),
        "automatable_percent": evidence_contract["automatable_repository_evidence"].get("percent"),
        "required_disposition_percent": evidence_contract["required_evidence_disposition"].get("percent"),
        "analyzer_completion_percent": evidence_contract["analyzer_completion"].get("percent"),
        "contract_version": VERSION,
    }
    output["canonical_score_contract"] = {
        "version": VERSION,
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "review_limited_scored_controls": limited_count,
        "evidence_penalty_points": penalty,
        "technical_formula": "round(sum(control_score * configured_weight) / sum(active_configured_weight))",
        "evidence_formula": "technical_score - ceil(review_limited_scored_controls * 2 / 3), capped at 10 points",
        "single_source_of_truth": True,
    }
    repository = output.get("repository") or "the authorized repository"
    technical_text = "not scored" if technical is None else f"{technical}/100"
    adjusted_text = "not scored" if adjusted is None else f"{adjusted}/100"
    output["executive_summary"] = (
        f"NICO completed an authorized Comprehensive Technical Assessment for {repository}. "
        f"Weighted technical maturity is {technical_text}; independently evidence-adjusted readiness is {adjusted_text}. "
        "The assessment combines repository health, exact-location findings, deeper architecture evidence, a six-month execution roadmap, "
        "staffing sequence, and a full evidence appendix. Internal technical review and exact-package authorization remain mandatory before client delivery."
    )
    return output


def _normalize_filename(value: Any) -> str:
    filename = str(value or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf")
    if _FINAL_SUFFIX_RE.search(filename):
        return _FINAL_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    if re.search(r"-DRAFT\.pdf$", filename, re.IGNORECASE):
        return re.sub(r"-DRAFT\.pdf$", "-FINAL-PENDING-APPROVAL.pdf", filename, flags=re.IGNORECASE)
    if filename.casefold().endswith(".pdf"):
        return filename[:-4] + "-FINAL-PENDING-APPROVAL.pdf"
    return filename + "-FINAL-PENDING-APPROVAL.pdf"


def _replace_pdf_text(pdf_bytes: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        stream = ContentStream(page.get_contents(), reader)
        for operands, operator in stream.operations:
            targets = operands if operator in {b"Tj", b"'", b'"'} else operands[0] if operator == b"TJ" and operands else []
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                elif isinstance(operand, ByteStringObject):
                    original = bytes(operand).decode("latin-1", errors="ignore")
                else:
                    continue
                updated = _clean_product_text(original)
                if updated != original:
                    targets[index] = TextStringObject(updated)
        page.replace_contents(stream)
    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _score_invariant(result: dict[str, Any]) -> dict[str, Any]:
    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    technical = assessment.get("technical_score")
    adjusted = assessment.get("evidence_adjusted_score")
    expected_technical = f"{int(technical)}/100" if isinstance(technical, (int, float)) else ""
    expected_adjusted = f"{int(adjusted)}/100" if isinstance(adjusted, (int, float)) else ""
    markdown = str(package.get("markdown") or "")
    html = str(package.get("html") or "")
    pdf_text = ""
    encoded = str(package.get("pdf_base64") or "")
    if encoded:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(base64.b64decode(encoded, validate=True)))
            pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages[:3])
        except Exception:
            pdf_text = ""
    passed = bool(
        expected_technical
        and expected_adjusted
        and expected_technical in markdown
        and expected_adjusted in markdown
        and expected_technical in html
        and expected_adjusted in html
        and expected_technical in pdf_text
        and expected_adjusted in pdf_text
        and "Why this is broader than Express" not in markdown
        and "Why this is broader than Express" not in html
        and "Why this is broader than Express" not in pdf_text
    )
    return {
        "status": "passed" if passed else "failed",
        "version": VERSION,
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "expected_technical_display": expected_technical,
        "expected_adjusted_display": expected_adjusted,
        "markdown_matches": expected_technical in markdown and expected_adjusted in markdown,
        "html_matches": expected_technical in html and expected_adjusted in html,
        "pdf_matches": expected_technical in pdf_text and expected_adjusted in pdf_text,
        "obsolete_express_language_absent": all("Why this is broader than Express" not in value for value in (markdown, html, pdf_text)),
    }


def finalize_canonical_report_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = _clean_product_language(deepcopy(result))
    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    package["pdf_filename"] = _normalize_filename(package.get("pdf_filename"))
    encoded = str(package.get("pdf_base64") or "")
    if encoded:
        try:
            pdf_bytes = _replace_pdf_text(base64.b64decode(encoded, validate=True))
            package["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
            package["pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
        except Exception:
            pass
    output["report_package"] = package
    invariant = _score_invariant(output)
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    evidence_contract = assessment.get("evidence_completion_contract")
    evidence_invariant_passed = _evidence_contract_valid(evidence_contract)
    quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
    quality.update(
        {
            "canonical_report_truth_version": VERSION,
            "canonical_score_invariant": invariant,
            "score_values_single_source": invariant["status"] == "passed",
            "obsolete_express_product_language_absent": invariant["obsolete_express_language_absent"],
            "duplicate_finality_suffix_absent": package["pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1,
            "severity_calibration_separates_evidence_blockers": True,
            "evidence_completion_contract_valid": evidence_invariant_passed,
            "evidence_completion_contract": evidence_contract if isinstance(evidence_contract, dict) else {},
            "full_evidence_claims_require_exact_counts": True,
        }
    )
    package["report_quality_contract"] = quality
    output["report_quality_contract"] = dict(quality)
    output["report_package"] = package
    if output.get("status") == "complete" and invariant["status"] != "passed":
        output["status"] = "blocked"
        output["reason"] = "canonical_report_score_invariant_failed"
    if output.get("status") == "complete" and not evidence_invariant_passed:
        output["status"] = "blocked"
        output["reason"] = "canonical_evidence_completion_invariant_failed"
    if output.get("status") == "complete" and not evidence_invariant_passed:
        output["status"] = "blocked"
        output["reason"] = "canonical_evidence_completion_invariant_failed"
    return output


def install_comprehensive_canonical_report_truth_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report_module

    if getattr(report_module.build_comprehensive_report_package, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    current_reconcile = report_module.reconcile_comprehensive_assessment

    @wraps(current_reconcile)
    def reconcile(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return apply_canonical_score_truth(current_reconcile(*args, **kwargs))

    report_module.reconcile_comprehensive_assessment = reconcile

    current_risk = report_module.reconcile_executive_risk_truth

    @wraps(current_risk)
    def reconcile_risk(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _calibrate_risks(current_risk(*args, **kwargs))

    report_module.reconcile_executive_risk_truth = reconcile_risk

    current_build: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package

    @wraps(current_build)
    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return finalize_canonical_report_truth(current_build(*args, **kwargs))

    setattr(build, _PATCH_MARKER, True)
    setattr(build, "_nico_previous", current_build)
    report_module.build_comprehensive_report_package = build
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "canonical_product": PRODUCT_NAME,
        "score_values_derived_not_hardcoded": True,
        "cross_format_score_invariant": True,
        "severity_calibration_enabled": True,
    }


__all__ = [
    "VERSION",
    "PRODUCT_NAME",
    "apply_canonical_score_truth",
    "finalize_canonical_report_truth",
    "install_comprehensive_canonical_report_truth_v1",
]
