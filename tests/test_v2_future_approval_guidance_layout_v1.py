from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.v2_automated_draft_quality_compat_v1 import _validate_review_pdf
from nico.v2_future_approval_guidance_layout_v1 import (
    VERSION,
    _contains_unapproved_finality,
    _remove_bounded_future_guidance,
    install_future_approval_guidance_layout_v1,
)


RUN_ID = "comprun_layout_guidance_v1"
COMMIT = "b9bb935041d59c9a976a4e2c7271c19235e99fcf"
EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
ES_BOUNDARY = (
    "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
    "ENTREGA AL CLIENTE BLOQUEADA"
)


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        document.drawString(42, y, line)
        y -= 19
    document.showPage()
    document.save()
    return buffer.getvalue()


def _canonical() -> dict:
    return {"identity": {"run_id": RUN_ID, "commit_sha": COMMIT}}


def test_english_future_guidance_allows_bounded_pdf_layout_noise() -> None:
    install_future_approval_guidance_layout_v1()
    value = "\n".join(
        (
            EN_BOUNDARY,
            "Only an authorized reviewer",
            "NICO | exact-artifact review package | automated draft | Page 2",
            "may change the status to APPROVED FINAL",
            "Section footer retained between extracted text fragments",
            "and CLIENT DELIVERY AUTHORIZED.",
        )
    )

    assert _contains_unapproved_finality(value) is False
    scoped = _remove_bounded_future_guidance(value)
    assert "approved final" not in scoped
    assert "client delivery authorized" not in scoped


def test_negative_automation_guidance_allows_bounded_layout_noise() -> None:
    install_future_approval_guidance_layout_v1()
    value = "\n".join(
        (
            EN_BOUNDARY,
            "Automation cannot",
            "NICO footer Page 3",
            "change this package to APPROVED FINAL",
            "AUTOMATED DRAFT footer",
            "or CLIENT DELIVERY AUTHORIZED.",
        )
    )

    assert _contains_unapproved_finality(value) is False


def test_spanish_future_guidance_allows_bounded_layout_noise() -> None:
    install_future_approval_guidance_layout_v1()
    value = "\n".join(
        (
            ES_BOUNDARY,
            "Solo un revisor autorizado puede",
            "NICO | paquete de revisión | Página 2",
            "cambiar el estado a FINAL APROBADO",
            "pie de página intercalado",
            "y ENTREGA AL CLIENTE AUTORIZADA.",
        )
    )

    assert _contains_unapproved_finality(value) is False


def test_second_current_state_assertion_after_guidance_remains_blocked() -> None:
    install_future_approval_guidance_layout_v1()
    value = "\n".join(
        (
            EN_BOUNDARY,
            "Only an authorized reviewer",
            "NICO footer",
            "may change the status to APPROVED FINAL",
            "and CLIENT DELIVERY AUTHORIZED.",
            "Current status: APPROVED FINAL",
        )
    )

    assert _contains_unapproved_finality(value) is True


def test_standalone_delivery_authorization_remains_blocked() -> None:
    install_future_approval_guidance_layout_v1()

    assert _contains_unapproved_finality(
        f"{EN_BOUNDARY}\nCLIENT DELIVERY AUTHORIZED"
    ) is True


def test_overlong_unrecognized_span_fails_closed() -> None:
    install_future_approval_guidance_layout_v1()
    value = (
        f"{EN_BOUNDARY}\nOnly an authorized reviewer may change the status "
        + ("x" * 1000)
        + " APPROVED FINAL and CLIENT DELIVERY AUTHORIZED"
    )

    assert _contains_unapproved_finality(value) is True


def test_pdf_validator_accepts_layout_noise_but_rejects_second_finality() -> None:
    install_future_approval_guidance_layout_v1()
    accepted = _pdf(
        EN_BOUNDARY,
        RUN_ID,
        COMMIT,
        "Only an authorized reviewer",
        "NICO | exact-artifact review package | automated draft | Page 2",
        "may change the status to APPROVED FINAL",
        "Section footer retained between extracted text fragments",
        "and CLIENT DELIVERY AUTHORIZED.",
    )
    _validate_review_pdf(
        accepted,
        _canonical(),
        expected_sections=[],
        spanish=False,
    )

    rejected = _pdf(
        EN_BOUNDARY,
        RUN_ID,
        COMMIT,
        "Only an authorized reviewer",
        "NICO footer",
        "may change the status to APPROVED FINAL",
        "and CLIENT DELIVERY AUTHORIZED.",
        "Current status: APPROVED FINAL",
    )
    with pytest.raises(
        ValueError,
        match="unapproved review PDF retained final-delivery language",
    ):
        _validate_review_pdf(
            rejected,
            _canonical(),
            expected_sections=[],
            spanish=False,
        )


def test_compact_final_report_bootstrap_installs_layout_contract() -> None:
    from nico.comprehensive_final_report_compact_base_v1 import (
        install_comprehensive_final_report_compact_base_v1,
    )

    result = install_comprehensive_final_report_compact_base_v1()

    assert result["bounded_future_guidance_layout_supported"] is True
    assert result["current_finality_gate_preserved"] is True
    assert result["future_approval_guidance_layout"]["version"] == VERSION
    assert result["future_approval_guidance_layout"][
        "second_current_state_assertion_remains_blocked"
    ] is True
    assert result["client_delivery_allowed"] is False
