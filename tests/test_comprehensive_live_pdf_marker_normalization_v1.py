from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "comprehensive_live_report_contract_v1.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "comprehensive_live_pdf_marker_normalization",
        CONTRACT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pdf_extraction_line_break_preserves_comprehensive_report_identity() -> None:
    contract = _module()

    contract._assert_marker(
        "NICO\nComprehensive Technical Assessment",
        "NICO Comprehensive Technical Assessment",
        surface="PDF",
    )


def test_html_element_boundaries_preserve_comprehensive_report_identity() -> None:
    contract = _module()

    contract._assert_marker(
        "<h1>NICO</h1><p>Comprehensive Technical Assessment</p>",
        "NICO Comprehensive Technical Assessment",
        surface="HTML",
    )


def test_normalized_marker_matching_remains_fail_closed_when_identity_is_missing() -> None:
    contract = _module()

    with pytest.raises(
        AssertionError,
        match="Comprehensive PDF omitted NICO Comprehensive Technical Assessment",
    ):
        contract._assert_marker(
            "NICO Express Technical Assessment",
            "NICO Comprehensive Technical Assessment",
            surface="PDF",
        )


def test_contract_version_records_normalized_marker_boundary() -> None:
    contract = _module()

    assert contract.VERSION == "nico.comprehensive-live-report-contract.v5"
