from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_final_report_semantics_v47 import (
    _clean_string,
    rewrite_comprehensive_pdf_semantics,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROXY = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
RUN_REQUESTS = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentRunRequests.ts"
OPERATOR_GUIDE = ROOT / "docs" / "OPERATOR_GUIDE.md"


def _pdf_with_text(value: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.drawString(72, 720, value)
    document.save()
    return buffer.getvalue()


def test_phase2_report_truth_rewrites_stale_triage_language_in_structured_text() -> None:
    stale = "Score effect: assurance-only until triaged."
    rewritten = _clean_string(stale)

    assert stale not in rewritten
    assert "authorized human disposition remains pending" in rewritten
    assert "technical-triage status is reported separately" in rewritten


def test_phase2_report_truth_rewrites_stale_triage_language_in_pdf() -> None:
    stale = "Score effect: assurance-only until triaged."
    rewritten_pdf, contract = rewrite_comprehensive_pdf_semantics(_pdf_with_text(stale))
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(rewritten_pdf)).pages)

    assert stale not in extracted
    assert "authorized human disposition remains pending" in extracted
    assert contract["stale_draft_language_absent"] is True
    assert contract["status"] == "passed"


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
