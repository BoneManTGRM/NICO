from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "comprehensive_live_report_contract_v1.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "comprehensive_live_future_approval_guidance",
        CONTRACT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_english_future_state_guidance_is_not_current_finality() -> None:
    contract = _module()

    contract._assert_no_unapproved_finality(
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n"
        "Only an authorized reviewer may change the status to APPROVED FINAL "
        "and CLIENT DELIVERY AUTHORIZED.",
        surface="PDF",
    )


def test_exact_spanish_future_state_guidance_is_not_current_finality() -> None:
    contract = _module()

    contract._assert_no_unapproved_finality(
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · "
        "ENTREGA AL CLIENTE BLOQUEADA\n"
        "Solo un revisor autorizado puede cambiar el estado a FINAL APROBADO "
        "y ENTREGA AL CLIENTE AUTORIZADA.",
        surface="PDF",
    )


def test_standalone_approved_final_status_remains_blocked() -> None:
    contract = _module()

    with pytest.raises(AssertionError, match="unapproved finality: APPROVED FINAL"):
        contract._assert_no_unapproved_finality(
            "Status: APPROVED FINAL",
            surface="Markdown",
        )


def test_guidance_does_not_hide_a_second_current_final_status() -> None:
    contract = _module()

    with pytest.raises(AssertionError, match="unapproved finality: APPROVED FINAL"):
        contract._assert_no_unapproved_finality(
            "Only an authorized reviewer may change the status to APPROVED FINAL "
            "and CLIENT DELIVERY AUTHORIZED.\n"
            "Current status: APPROVED FINAL",
            surface="PDF",
        )


def test_standalone_delivery_authorization_remains_blocked() -> None:
    contract = _module()

    with pytest.raises(
        AssertionError,
        match="unapproved finality: CLIENT DELIVERY AUTHORIZED",
    ):
        contract._assert_no_unapproved_finality(
            "CLIENT DELIVERY AUTHORIZED",
            surface="HTML",
        )


def test_contract_version_records_future_guidance_boundary() -> None:
    contract = _module()

    assert contract.VERSION == "nico.comprehensive-live-report-contract.v4"
