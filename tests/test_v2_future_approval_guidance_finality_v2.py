from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.v2_automated_draft_quality_compat_v1 import (
    VERSION,
    _contains_unapproved_finality,
    _current_state_finality_scope,
    _validate_review_pdf,
)


RUN_ID = "comprun_future_guidance_v2"
COMMIT = "96de8556466ccc51e5a7c8a88dc3844d305d9adc"
EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
ES_BOUNDARY = (
    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
    "ENTREGA AL CLIENTE BLOQUEADA"
)
EN_GUIDANCE = (
    "Only an authorized reviewer may change the status to APPROVED FINAL "
    "and CLIENT DELIVERY AUTHORIZED."
)
ES_GUIDANCE = (
    "Solo un revisor autorizado puede cambiar el estado a FINAL APROBADO "
    "y ENTREGA AL CLIENTE AUTORIZADA."
)


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        document.drawString(42, y, line)
        y -= 20
    document.showPage()
    document.save()
    return buffer.getvalue()


def _canonical() -> dict:
    return {
        "identity": {
            "run_id": RUN_ID,
            "commit_sha": COMMIT,
        }
    }


def test_exact_english_future_guidance_is_not_current_finality() -> None:
    value = f"{EN_BOUNDARY}\n{EN_GUIDANCE}"

    assert _contains_unapproved_finality(value) is False
    assert "approved final" not in _current_state_finality_scope(value)
    assert "client delivery authorized" not in _current_state_finality_scope(value)


def test_exact_spanish_future_guidance_is_not_current_finality() -> None:
    value = f"{ES_BOUNDARY}\n{ES_GUIDANCE}"

    assert _contains_unapproved_finality(value) is False
    assert "final aprobado" not in _current_state_finality_scope(value)
    assert "entrega al cliente autorizada" not in _current_state_finality_scope(value)


def test_review_pdf_accepts_future_guidance_with_current_automated_draft_status() -> None:
    _validate_review_pdf(
        _pdf(EN_BOUNDARY, RUN_ID, COMMIT, EN_GUIDANCE),
        _canonical(),
        expected_sections=[],
        spanish=False,
    )


def test_spanish_review_pdf_accepts_future_guidance_with_blocked_delivery() -> None:
    _validate_review_pdf(
        _pdf(ES_BOUNDARY, RUN_ID, COMMIT, ES_GUIDANCE),
        _canonical(),
        expected_sections=[],
        spanish=True,
    )


def test_future_guidance_does_not_hide_second_current_final_status() -> None:
    value = f"{EN_BOUNDARY}\n{EN_GUIDANCE}\nCurrent status: APPROVED FINAL"

    assert _contains_unapproved_finality(value) is True
    with pytest.raises(
        ValueError,
        match="unapproved review PDF retained final-delivery language",
    ):
        _validate_review_pdf(
            _pdf(EN_BOUNDARY, RUN_ID, COMMIT, EN_GUIDANCE, "Current status: APPROVED FINAL"),
            _canonical(),
            expected_sections=[],
            spanish=False,
        )


def test_standalone_delivery_authorization_remains_blocked() -> None:
    value = f"{EN_BOUNDARY}\nCLIENT DELIVERY AUTHORIZED"

    assert _contains_unapproved_finality(value) is True


def test_current_final_report_language_remains_blocked() -> None:
    value = f"{EN_BOUNDARY}\nFINAL REPORT"

    assert _contains_unapproved_finality(value) is True


def test_contract_version_records_context_aware_finality_scope() -> None:
    assert VERSION == "nico.v2.automated-draft-quality-compat.v2"
