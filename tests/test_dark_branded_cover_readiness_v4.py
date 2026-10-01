from __future__ import annotations

import base64
import io

import pytest

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_dark_branded_cover_readiness_v4 import (
    install_dark_branded_cover_readiness_v4,
)
from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY


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


def test_cover_uses_truthful_readiness_states_without_redesign() -> None:
    install_dark_branded_cover_readiness_v4()
    result = apply_dark_branded_cover(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    extracted = PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or ""
    normalized = " ".join(extracted.split())
    lowered = normalized.casefold()

    assert "HUMAN REVIEW" in extracted
    assert "Pending" in extracted
    assert "evidence-bound technical review package" in lowered
    assert "CLIENT DELIVERY" in extracted
    assert "Blocked" in extracted
    assert "CLIENT-READY" not in extracted
    assert "Client delivery remains blocked until explicit authorized human approval" in normalized
    assert "six-month roadmap framework pending stakeholder validation" in lowered
    assert "completed an authorized" not in lowered
    assert "generated an automated Comprehensive Technical Assessment draft" in normalized
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


def test_quality_repair_does_not_overlay_duplicate_cover_boundary() -> None:
    from nico import v2_report_quality_repairs as quality
    from nico.v2_automated_draft_quality_compat_v1 import (
        install_automated_draft_quality_compat,
    )

    install_automated_draft_quality_compat()
    covered = apply_dark_branded_cover(_package())
    source = base64.b64decode(covered["pdf_base64"])

    repaired, _ = quality._replace_pdf_text(source, spanish=False)
    first_page = PdfReader(io.BytesIO(repaired)).pages[0].extract_text() or ""

    assert first_page.count(EN_BOUNDARY) == 1

@pytest.mark.parametrize("language,unscored", (("en", "NOT SCORED"), ("es-MX", "SIN PUNTUACIÓN")))
@pytest.mark.parametrize("technical,adjusted,expected", (
    (None, None, (None, None)),
    (False, True, (None, None)),
    (83, None, ("83/100", None)),
    (None, 71, (None, "71/100")),
    (83, 71, ("83/100", "71/100")),
))
def test_dark_cover_localizes_unscored_values_without_changing_scores(
    language, unscored, technical, adjusted, expected,
) -> None:
    from nico.v2_dark_branded_cover import _cover

    canonical = {
        "identity": {"repository": "owned/report-control", "commit_sha": COMMIT,
                     "run_id": "owned-report-control", "generated_at": "2026-10-01T16:00:00Z"},
        "assessment": {"technical_score": technical, "canonical_evidence_adjusted_score": adjusted},
        "canonical_findings": [],
    }
    pdf = _cover(canonical, spanish=language == "es-MX")
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or ""
    normalized = " ".join(text.split())
    labels = tuple(value if value is not None else unscored for value in expected)

    for value in labels:
        assert value in normalized
    if language == "es-MX":
        assert "NOT SCORED" not in text
        assert "Pendiente" in text and "Bloqueada" in text
    else:
        assert "SIN PUNTUACIÓN" not in text
        assert "Pending" in text and "Blocked" in text
    if technical is None or isinstance(technical, bool):
        assert labels[0] == unscored
    if adjusted is None or isinstance(adjusted, bool):
        assert labels[1] == unscored
    assert COMMIT in text
    assert "owned/report-control" in text


@pytest.mark.parametrize("spanish,label", ((False, "NOT SCORED"), (True, "SIN PUNTUACIÓN")))
def test_dark_cover_unscored_card_values_fit_existing_card_width(spanish, label) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from nico.v2_dark_branded_cover import _cover

    pdf = _cover({"identity": {"repository": "owned/report-control"}, "assessment": {}}, spanish=spanish)
    reader = PdfReader(io.BytesIO(pdf))
    card_values = []

    def inspect(text, cm, tm, font, font_size):
        if text.strip() == label and tm[5] > 600:
            card_values.append((font_size, text.strip()))

    reader.pages[0].extract_text(visitor_text=inspect)
    card_width = (letter[0] - 84 - 9 * 3) / 4

    assert len(card_values) == 2
    for font_size, text in card_values:
        assert 10 <= font_size <= 15
        assert stringWidth(text, "Helvetica-Bold", font_size) <= card_width - 20 + 0.01
