from __future__ import annotations

import io

from pypdf import PdfReader

from nico import mid_report_professional_v7 as v8
from nico.mid_report_professional_v7_runtime_fix import _fixed_premium_enhance


def _payload() -> dict:
    return {
        "repository": "example/nico",
        "snapshot_commit_sha": "a" * 40,
        "canonical_weighted_technical_score": 80,
        "evidence_coverage": {"percent": 100},
        "decision_summary": {"review_decision_reason": "Human disposition remains required."},
        "sections": [],
    }


def test_v8_preserves_required_acceptance_navigation_terms() -> None:
    payload = _fixed_premium_enhance(_payload())
    reader = PdfReader(io.BytesIO(v8._premium_pdf(payload)))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)

    for required in (
        "MID TECHNICAL ASSESSMENT",
        "Architecture and Dependency Analysis",
        "Complexity, Churn, Ownership, and Review Latency",
        "CI/CD Failure Classification",
        "Analyzer execution",
        "Parsing acceptance",
        "Finding disposition",
        "Integrity and Approval Boundary",
    ):
        assert required in text
    assert len(reader.pages) == 35
