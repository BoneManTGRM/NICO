#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "nico/api/production.py"
MODULE = ROOT / "nico/comprehensive_canonical_report_truth_v1.py"
TEST = ROOT / "tests/test_comprehensive_canonical_report_truth_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def patch_production() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")
    if "install_comprehensive_canonical_report_truth_v1" in source:
        return
    source = replace_once(
        source,
        "from nico.correlation_header_exposure import install_correlation_header_exposure\n",
        "from nico.correlation_header_exposure import install_correlation_header_exposure\n"
        "from nico.comprehensive_canonical_report_truth_v1 import (\n"
        "    install_comprehensive_canonical_report_truth_v1,\n"
        ")\n",
        "canonical truth import",
    )
    source = replace_once(
        source,
        "ASSESSMENT_MID_REVIEW_ENFORCEMENT = install_mid_review_enforcement_compat()\n",
        "ASSESSMENT_MID_REVIEW_ENFORCEMENT = install_mid_review_enforcement_compat()\n"
        "ASSESSMENT_COMPREHENSIVE_CANONICAL_TRUTH = install_comprehensive_canonical_report_truth_v1()\n",
        "canonical truth installation",
    )
    source = replace_once(
        source,
        '    "ASSESSMENT_BUILTIN_STATIC_CONTEXT",\n',
        '    "ASSESSMENT_BUILTIN_STATIC_CONTEXT",\n'
        '    "ASSESSMENT_COMPREHENSIVE_CANONICAL_TRUTH",\n',
        "canonical truth export",
    )
    PRODUCTION.write_text(source, encoding="utf-8")


def write_module() -> None:
    MODULE.write_text(r'''from __future__ import annotations

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
        "staffing sequence, and a full evidence appendix. Human review and exact-package approval remain mandatory."
    )
    return output


def _normalize_filename(value: Any) -> str:
    filename = str(value or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf")
    filename = _FINAL_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    filename = _DRAFT_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    return filename


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
    quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
    quality.update(
        {
            "canonical_report_truth_version": VERSION,
            "canonical_score_invariant": invariant,
            "score_values_single_source": invariant["status"] == "passed",
            "obsolete_express_product_language_absent": invariant["obsolete_express_language_absent"],
            "duplicate_finality_suffix_absent": package["pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1,
            "severity_calibration_separates_evidence_blockers": True,
        }
    )
    package["report_quality_contract"] = quality
    output["report_quality_contract"] = dict(quality)
    output["report_package"] = package
    if output.get("status") == "complete" and invariant["status"] != "passed":
        output["status"] = "blocked"
        output["reason"] = "canonical_report_score_invariant_failed"
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
''', encoding="utf-8")


def write_tests() -> None:
    TEST.write_text(r'''from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_canonical_report_truth_v1 import (
    apply_canonical_score_truth,
    finalize_canonical_report_truth,
)


def _assessment() -> dict:
    scores = [
        ("code_audit", 0.20, 92, "VERIFIED"),
        ("dependency_health", 0.15, 92, "LIMITED · CANDIDATE DISPOSITION"),
        ("secrets_review", 0.15, 93, "LIMITED · CANDIDATE DISPOSITION"),
        ("static_analysis", 0.15, 79, "LIMITED · ANALYZER COVERAGE"),
        ("ci_cd", 0.15, 86, "VERIFIED"),
        ("architecture_debt", 0.15, 78, "VERIFIED"),
        ("velocity_complexity", 0.05, 84, "VERIFIED"),
    ]
    return {
        "repository": "BoneManTGRM/NICO",
        "sections": [
            {"id": section_id, "score_value": score, "assurance_label": assurance}
            for section_id, _weight, score, assurance in scores
        ],
        "scoring_weights": [
            {
                "section_id": section_id,
                "control": section_id,
                "weight": weight,
                "technical_score": score,
                "assurance": assurance,
                "included": True,
            }
            for section_id, weight, score, assurance in scores
        ],
        "findings_register": [
            {
                "priority": "P1",
                "category": "architecture",
                "title": "Complexity hotspot: build_report",
                "evidence": "cyclomatic_complexity=94; verified=True",
                "impact": "Concentrated branch logic increases regression risk.",
            },
            {
                "priority": "P1",
                "category": "evidence",
                "title": "bandit evidence unavailable",
                "evidence": "Analyzer status=failed",
                "impact": "Evidence was unavailable.",
            },
        ],
        "executive_risk_register": [],
    }


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.drawString(40, 700, text)
    page.drawString(40, 680, "87/100")
    page.drawString(40, 660, "85/100")
    page.save()
    return buffer.getvalue()


def test_scores_are_derived_as_87_and_85_from_the_control_evidence() -> None:
    result = apply_canonical_score_truth(_assessment())
    contract = result["canonical_score_contract"]

    assert result["technical_score"] == 87
    assert result["evidence_adjusted_score"] == 85
    assert contract["review_limited_scored_controls"] == 3
    assert contract["evidence_penalty_points"] == 2
    assert "87/100" in result["executive_summary"]
    assert "85/100" in result["executive_summary"]
    assert "Express" not in result["executive_summary"]


def test_complexity_and_evidence_limitations_are_not_misrepresented_as_p1_defects() -> None:
    result = apply_canonical_score_truth(_assessment())
    findings = result["findings_register"]

    assert findings[0]["priority"] == "P2"
    assert findings[1]["priority"] == "P2"
    assert findings[1]["release_blocker"] is True
    assert "not proof of a severe client-system defect" in findings[1]["impact"]


def test_final_report_normalizes_filename_and_blocks_cross_format_score_drift() -> None:
    assessment = apply_canonical_score_truth(_assessment())
    summary = assessment["executive_summary"]
    pdf = _pdf(summary)
    source = {
        "status": "complete",
        "report_package": {
            "markdown": f"# NICO Comprehensive Technical Assessment\n\n{summary}\n\n87/100\n85/100",
            "html": f"<h1>NICO Comprehensive Technical Assessment</h1><p>{summary}</p><p>87/100</p><p>85/100</p>",
            "json": {"assessment": assessment},
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_filename": "report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "report_quality_contract": {},
        },
    }

    result = finalize_canonical_report_truth(source)

    assert result["status"] == "complete"
    assert result["report_package"]["pdf_filename"] == "report-FINAL-PENDING-APPROVAL.pdf"
    invariant = result["report_package"]["report_quality_contract"]["canonical_score_invariant"]
    assert invariant["status"] == "passed"


def test_report_fails_closed_when_one_surface_disagrees() -> None:
    assessment = apply_canonical_score_truth(_assessment())
    source = {
        "status": "complete",
        "report_package": {
            "markdown": "# NICO Comprehensive Technical Assessment\n87/100\n85/100",
            "html": "<p>88/100</p><p>76/100</p>",
            "json": {"assessment": assessment},
            "pdf_base64": base64.b64encode(_pdf("NICO Comprehensive Technical Assessment")).decode("ascii"),
            "pdf_filename": "report-DRAFT.pdf",
            "report_quality_contract": {},
        },
    }

    result = finalize_canonical_report_truth(source)

    assert result["status"] == "blocked"
    assert result["reason"] == "canonical_report_score_invariant_failed"
''', encoding="utf-8")


def main() -> int:
    patch_production()
    write_module()
    write_tests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
