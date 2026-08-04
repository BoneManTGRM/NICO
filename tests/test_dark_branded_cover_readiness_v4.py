from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_dark_branded_cover_readiness_v4 import (
    install_dark_branded_cover_readiness_v4,
)


COMMIT = "3c4352ae1873c547dd01406da833d2faedb5039b"


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(40, 780, "Original first page")
    document.showPage()
    document.save()
    return buffer.getvalue()


def _package() -> dict:
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": COMMIT,
                "run_id": "comprun_cover_v4",
            },
            "assessment": {
                "technical_score": 93,
                "evidence_adjusted_score": 89,
                "maturity_signal": {"score": 93},
            },
            "canonical_findings": [
                {
                    "finding_id": "NICO-FINDING-1",
                    "priority": "P2",
                    "title": "Reduce complexity in example function",
                }
            ],
        },
        "pdf_base64": base64.b64encode(_pdf()).decode("ascii"),
        "premium_report_renderer": {},
    }


def test_cover_uses_three_truthful_readiness_states_without_redesign() -> None:
    install_dark_branded_cover_readiness_v4()
    result = apply_dark_branded_cover(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    extracted = PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or ""
    normalized = " ".join(extracted.split())

    assert "HUMAN APPROVAL" in extracted
    assert "Pending" in extracted
    assert "REVIEW PACKAGE" in extracted
    assert "Ready" in extracted
    assert "CLIENT-READY" not in extracted
    assert "Client delivery remains blocked until explicit approval" in normalized
    assert "six-month roadmap framework pending stakeholder validation" in normalized
    assert "NICO COMPREHENSIVE" in extracted
    assert "TECHNICAL MATURITY" in extracted
    assert "EVIDENCE-ADJUSTED" in extracted


def test_cover_installation_preserves_automated_delivery_boundary() -> None:
    installation = install_dark_branded_cover_readiness_v4()

    assert installation["premium_design_preserved"] is True
    assert installation["review_package_ready"] is True
    assert installation["human_review_status"] == "pending"
    assert installation["client_delivery_status"] == "blocked"
    assert installation["roadmap_claim"] == "framework_pending_stakeholder_validation"
    assert installation["client_delivery_allowed"] is False
