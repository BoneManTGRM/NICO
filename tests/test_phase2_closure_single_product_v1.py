from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_final_report_semantics_v47 import (
    _clean_string,
    finalize_comprehensive_report_result,
    rewrite_comprehensive_pdf_semantics,
)
from nico.phase17_canonical_artifact_rebuild_v1 import (
    _phase2_review_truth_node,
    _rewrite_phase2_review_truth_pdf,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROXY = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
RUN_REQUESTS = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentRunRequests.ts"
OPERATOR_GUIDE = ROOT / "docs" / "OPERATOR_GUIDE.md"
STALE_TRIAGE = "Score effect: assurance-only until triaged."
CORRECT_TRIAGE = "authorized human disposition remains pending"


def _pdf_with_text(value: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.drawString(72, 720, value)
    document.save()
    return buffer.getvalue()


def test_phase2_report_truth_rewrites_stale_triage_language_in_structured_text() -> None:
    rewritten = _clean_string(STALE_TRIAGE)

    assert STALE_TRIAGE not in rewritten
    assert CORRECT_TRIAGE in rewritten
    assert "technical-triage status is reported separately" in rewritten


def test_phase2_report_truth_rewrites_stale_triage_language_in_pdf() -> None:
    rewritten_pdf, contract = rewrite_comprehensive_pdf_semantics(_pdf_with_text(STALE_TRIAGE))
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(rewritten_pdf)).pages)

    assert STALE_TRIAGE not in extracted
    assert CORRECT_TRIAGE in extracted
    assert contract["stale_draft_language_absent"] is True
    assert contract["status"] == "passed"


def test_phase2_report_truth_is_rewritten_across_legacy_canonical_output_formats() -> None:
    canonical_title = "NICO Comprehensive Technical Assessment"
    final_boundary = "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    source_pdf = _pdf_with_text(f"{canonical_title} {final_boundary} {STALE_TRIAGE}")
    result = {
        "status": "complete",
        "report_package": {
            "markdown": f"# {canonical_title}\n\n{final_boundary}\n\n{STALE_TRIAGE}\n",
            "html": f"<html><body><h1>{canonical_title}</h1><p>{final_boundary}</p><p>{STALE_TRIAGE}</p></body></html>",
            "json": {"section": {"score_effect": STALE_TRIAGE}},
            "findings_csv": f"field,value\nscore_effect,{STALE_TRIAGE}\n",
            "evidence_csv": f"field,value\nscore_effect,{STALE_TRIAGE}\n",
            "pdf_base64": base64.b64encode(source_pdf).decode("ascii"),
        },
    }

    finalized = finalize_comprehensive_report_result(result)
    package = finalized["report_package"]
    extracted_pdf = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"]))).pages
    )

    for text in (
        package["markdown"],
        package["html"],
        package["json"]["section"]["score_effect"],
        package["findings_csv"],
        package["evidence_csv"],
        extracted_pdf,
    ):
        assert STALE_TRIAGE not in text
        assert CORRECT_TRIAGE in text
    assert finalized["status"] == "complete"
    assert package["report_quality_contract"]["stale_draft_language_absent"] is True


def test_phase2_current_v2_artifact_boundary_synchronizes_truth_before_hashing() -> None:
    package = {
        "json": {"assessment": {"sections": [{"evidence": [STALE_TRIAGE]}]}},
        "markdown": STALE_TRIAGE,
        "html": f"<p>{STALE_TRIAGE}</p>",
        "findings_csv": f"field,value\nscore_effect,{STALE_TRIAGE}\n",
        "evidence_csv": f"field,value\nscore_effect,{STALE_TRIAGE}\n",
    }
    synchronized = _phase2_review_truth_node(package)

    for text in (
        synchronized["json"]["assessment"]["sections"][0]["evidence"][0],
        synchronized["markdown"],
        synchronized["html"],
        synchronized["findings_csv"],
        synchronized["evidence_csv"],
    ):
        assert STALE_TRIAGE not in text
        assert CORRECT_TRIAGE in text

    pdf = _rewrite_phase2_review_truth_pdf(_pdf_with_text(STALE_TRIAGE))
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert STALE_TRIAGE not in extracted
    assert CORRECT_TRIAGE in extracted


def test_public_proxy_exposes_only_comprehensive_assessment_product() -> None:
    source = PUBLIC_PROXY.read_text(encoding="utf-8")

    assert 'const COMPREHENSIVE_INTAKE = "/assessment/comprehensive-intake";' in source
    assert 'const ALLOWED_DIAGNOSTIC_PATH = /^\\/diagnostics\\/comprehensive-runtime$/;' in source
    assert "EXPRESS_START" not in source
    assert "EXPRESS_STATUS" not in source
    assert "express-runtime" not in source
    assert "Only NICO Comprehensive lifecycle routes" in source


def test_readiness_retries_only_same_canonical_store_recovery_state() -> None:
    source = RUN_REQUESTS.read_text(encoding="utf-8")

    assert "READINESS_RETRY_DELAYS_MS" in source
    assert '"comprehensive_database_unavailable"' in source
    assert "result.runtime_recovery_supported === true" in source
    assert "result.automatic_cross_store_fallback === false" in source
    assert "readinessCanRecoverOnSameStore(result)" in source
    assert "Continuation is not safely replayable" in source


def test_operator_guide_declares_one_comprehensive_product() -> None:
    guide = OPERATOR_GUIDE.read_text(encoding="utf-8")

    assert "one customer-facing assessment product and one client report" in guide
    assert "NICO Comprehensive Technical Assessment" in guide
    assert "Select Express, Mid, or Full" not in guide
    assert "one NICO Comprehensive client PDF" in guide
