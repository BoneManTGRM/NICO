from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from pypdf import PdfReader

from nico.mid_report_professional_v7 import _premium_enhance as _enhance
from nico.mid_report_professional_v7 import _premium_pdf as _pdf


V4_TEST = Path(__file__).with_name("test_mid_report_professional_v4.py")
SPEC = importlib.util.spec_from_file_location("mid_v4_fixture_for_premium_acceptance", V4_TEST)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture() -> dict:
    payload = MODULE._payload()
    payload["evidence_coverage"] = {"percent": 100, "numerator": 12, "denominator": 12}
    payload["decision_summary"]["primary_score_constraints"] = [
        {
            "section_id": "static_analysis",
            "label": "Static Analysis",
            "score": 49,
            "primary_reason": "Bandit and Semgrep exact-snapshot evidence is incomplete.",
        },
        {
            "section_id": "code_audit",
            "label": "Code Audit",
            "score": 60,
            "primary_reason": "Four sampled risk patterns require exact disposition.",
        },
        {
            "section_id": "dependency_health",
            "label": "Dependency / Library Ecosystem",
            "score": 72,
            "primary_reason": "Scanner execution and accepted structured evidence do not yet align.",
        },
    ]
    return payload


def test_mid_premium_report_has_substantive_depth_when_fixture_evidence_supports_it() -> None:
    result = _enhance(_fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))

    assert 28 <= len(reader.pages) <= 50
    assert all(len(" ".join((page.extract_text() or "").split())) >= 180 for page in reader.pages)


def test_mid_premium_report_contains_decision_grade_sections_and_visual_analysis() -> None:
    result = _enhance(_fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)

    required_sections = (
        "Executive Decision Brief",
        "Repository and Delivery Profile",
        "Evidence Funnel",
        "Risk Matrix",
        "Architecture and Dependency Analysis",
        "Complexity, Churn, Ownership, and Review Latency",
        "CI/CD Failure Classification",
        "Repair Impact Matrix",
        "30 / 60 / 90 Day Roadmap",
        "Evidence Appendix",
        "Integrity and Approval Boundary",
    )
    for section in required_sections:
        assert section in text


def test_mid_premium_report_does_not_misrepresent_evidence_unit_coverage() -> None:
    result = _enhance(_fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)

    assert "Evidence units 100%" not in text
    assert "Evidence availability" in text
    assert "Analyzer execution" in text
    assert "Parsing acceptance" in text
    assert "Finding disposition" in text


def test_mid_premium_report_preserves_review_and_truth_boundaries() -> None:
    result = _enhance(_fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)

    assert "human review required" in text.lower()
    assert "unsupported claims permitted: 0" in text.lower()
    assert "conditional" in text.lower()
    assert "<b>" not in text
    assert "</b>" not in text
