from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY
from nico.v2_automated_draft_quality_compat_v1 import (
    install_automated_draft_quality_compat,
    repair_rendered_report,
)

RUN_ID = "comprun_automated_draft_quality"
COMMIT = "a" * 40


def _pdf(*pages: list[str]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        y = 730
        for line in lines:
            document.drawString(42, y, line)
            y -= 18
        document.showPage()
    document.save()
    return output.getvalue()


def _canonical() -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "run_id": RUN_ID,
            "commit_sha": COMMIT,
        },
        "assessment": {
            "technical_score": 88,
            "evidence_adjusted_score": 86,
            "sections": [
                {
                    "id": "code_quality",
                    "label": "Code Quality",
                    "score": 88,
                    "presented_score": 88,
                    "status": "strong",
                }
            ],
        },
        "report_finality": "automated_draft",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_quality_gate_accepts_required_automated_draft_boundary() -> None:
    from nico import v2_report_quality_repairs as quality

    installation = install_automated_draft_quality_compat()
    pdf = _pdf(
        ["Canonical Technical Scorecard", "Code Quality", "88/100"],
        [RUN_ID, COMMIT, EN_BOUNDARY],
    )

    quality._validate_final_pdf(
        pdf,
        _canonical(),
        expected_sections=_canonical()["assessment"]["sections"],
        spanish=False,
    )

    assert installation["bound"] is True
    assert installation["automated_draft_is_valid_unapproved_state"] is True
    assert installation["legacy_bare_draft_remains_blocked"] is True
    assert installation["unapproved_finality_remains_blocked"] is True


def test_quality_gate_blocks_legacy_bare_draft_and_unapproved_finality() -> None:
    from nico import v2_report_quality_repairs as quality

    install_automated_draft_quality_compat()
    legacy = _pdf([RUN_ID, COMMIT, "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"])
    misleading_final = _pdf([RUN_ID, COMMIT, "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"])

    with pytest.raises(ValueError, match="legacy bare DRAFT"):
        quality._validate_final_pdf(
            legacy,
            _canonical(),
            expected_sections=[],
            spanish=False,
        )
    with pytest.raises(ValueError, match="final-delivery language"):
        quality._validate_final_pdf(
            misleading_final,
            _canonical(),
            expected_sections=[],
            spanish=False,
        )


def test_spanish_automated_draft_boundary_is_valid() -> None:
    from nico import v2_report_quality_repairs as quality

    install_automated_draft_quality_compat()
    canonical = _canonical()
    canonical["report_language"] = "es-MX"
    pdf = _pdf([RUN_ID, COMMIT, ES_BOUNDARY])

    quality._validate_final_pdf(
        pdf,
        canonical,
        expected_sections=[],
        spanish=True,
    )


def test_runtime_repair_preserves_scorecard_identity_and_draft_posture() -> None:
    package = {
        "json": _canonical(),
        "markdown": f"# NICO\n\n{EN_BOUNDARY}\n",
        "html": f"<html><body><article><p>{EN_BOUNDARY}</p></article></body></html>",
        "pdf_base64": base64.b64encode(
            _pdf(
                ["Canonical Technical Scorecard", "Code Quality", "88/100"],
                [RUN_ID, COMMIT, EN_BOUNDARY],
            )
        ).decode("ascii"),
    }

    result = repair_rendered_report(package)
    pdf = base64.b64decode(result["pdf_base64"])
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert result["report_finality"] == "automated_draft"
    assert result["approval_status"] == "pending_human_approval"
    assert result["delivery_status"] == "blocked_pending_human_approval"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["json"]["report_finality"] == "automated_draft"
    assert "AUTOMATED DRAFT" in extracted
    assert "FINAL REPORT" not in extracted
    assert "Canonical Technical Scorecard" in extracted
    assert "Code Quality" in extracted
    assert "88/100" in extracted
    assert RUN_ID in extracted
    assert COMMIT in extracted
    contract = result["premium_report_renderer"]
    assert contract["automated_draft_is_valid_unapproved_state"] is True
    assert contract["legacy_bare_draft_language_absent"] is True
    assert contract["unapproved_finality_language_absent"] is True
