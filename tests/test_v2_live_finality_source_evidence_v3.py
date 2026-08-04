from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.v2_automated_draft_quality_compat_v1 import _validate_review_pdf
from nico.v2_future_approval_guidance_layout_v1 import (
    VERSION,
    _contains_unapproved_finality,
    install_future_approval_guidance_layout_v1,
)


RUN_ID = "comprun_live_finality_source_evidence_v3"
COMMIT = "f797305adb61ca43c1ae61cfe2788dd8301ad3c8"
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


def test_live_repository_evidence_can_name_final_report_work_without_asserting_finality() -> None:
    install_future_approval_guidance_layout_v1()
    evidence = (
        "technical_analysis.activity.sample_pull_requests[6].title: "
        "Inspect current final report blocker after deployment"
    )
    second = (
        "technical_analysis.activity.sample_pull_requests[7].title: "
        "Diagnose and repair current Comprehensive final report blocker"
    )

    assert _contains_unapproved_finality(evidence) is False
    assert _contains_unapproved_finality(second) is False
    _validate_review_pdf(
        _pdf(EN_BOUNDARY, RUN_ID, COMMIT, evidence, second),
        _canonical(),
        expected_sections=[],
        spanish=False,
    )


def test_source_paths_and_function_names_with_final_report_are_not_status_claims() -> None:
    install_future_approval_guidance_layout_v1()
    values = (
        "nico/comprehensive_final_report_execution_v1.py:88",
        "Reduce complexity in final_report_generation",
        "report_contract_reason: comprehensive_final_report_semantic_contract_failed",
    )

    for value in values:
        assert _contains_unapproved_finality(value) is False


def test_standalone_final_report_status_remains_blocked() -> None:
    install_future_approval_guidance_layout_v1()

    assert _contains_unapproved_finality(f"{EN_BOUNDARY}\nFINAL REPORT") is True
    with pytest.raises(
        ValueError,
        match="unapproved review PDF retained final-delivery language",
    ):
        _validate_review_pdf(
            _pdf(EN_BOUNDARY, RUN_ID, COMMIT, "FINAL REPORT"),
            _canonical(),
            expected_sections=[],
            spanish=False,
        )


def test_final_report_lifecycle_sentence_remains_blocked() -> None:
    install_future_approval_guidance_layout_v1()
    value = "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"

    assert _contains_unapproved_finality(value) is True


def test_explicit_current_report_status_remains_blocked() -> None:
    install_future_approval_guidance_layout_v1()

    assert _contains_unapproved_finality("Current report status: FINAL REPORT") is True
    assert _contains_unapproved_finality("Report finality: final") is True


def test_spanish_final_report_status_remains_blocked_but_source_evidence_is_allowed() -> None:
    install_future_approval_guidance_layout_v1()
    evidence = "actividad.pull_request.title: Reparar el bloqueador del informe final"

    assert _contains_unapproved_finality(evidence) is False
    assert _contains_unapproved_finality(f"{ES_BOUNDARY}\nINFORME FINAL") is True


def test_contract_records_source_evidence_and_status_scoping() -> None:
    result = install_future_approval_guidance_layout_v1()

    assert VERSION == "nico.v2.future-approval-guidance-layout.v1.3"
    assert result["source_evidence_final_report_wording_allowed"] is True
    assert result["status_scoped_final_report_detection"] is True
    assert result["standalone_final_report_status_remains_blocked"] is True
    assert result["current_finality_gate_preserved"] is True
    assert result["client_delivery_allowed"] is False
