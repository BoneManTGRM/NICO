from __future__ import annotations

import base64
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = SCRIPTS / "comprehensive_live_report_contract_v1.py"
ACCEPTANCE = SCRIPTS / "two_service_live_acceptance.py"
AUTHORITATIVE = SCRIPTS / "unified_production_acceptance_authoritative.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pdf(*lines: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    y = 750
    for line in lines:
        document.drawString(42, y, line)
        y -= 18
    document.showPage()
    document.save()
    return output.getvalue()


def _payload(*, finality: str = "AUTOMATED DRAFT") -> dict:
    common = (
        "NICO Comprehensive Technical Assessment",
        "Functional QA",
        "Platform Parity",
        "Six-Month Roadmap",
        "Staffing, Sequencing, and Cost",
        "Human Review and Acceptance Gate",
    )
    lifecycle = (
        f"{finality} · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    )
    markdown = "\n\n".join(
        (
            "# NICO Comprehensive Technical Assessment",
            *common[1:],
            "## Evidence Package Summary",
            lifecycle,
            "93/100",
        )
    )
    rendered_html = (
        "<!doctype html><html><body>"
        + " ".join((*common, "Evidence Package Summary", lifecycle, "93/100"))
        + "</body></html>"
    )
    pdf = _pdf(
        *common,
        "Client Evidence Summary",
        lifecycle,
        "93/100",
    )
    canonical = {
        "canonical_truth_sha256": "a" * 64,
        "assessment": {
            "maturity_signal": {
                "level": "Exceptional",
                "score": 93,
            },
            "sections": [
                {
                    "id": "functional_qa",
                    "label": "Functional QA",
                    "score": 93,
                    "status": "strong",
                }
            ],
        },
    }
    package = {
        "service_id": "comprehensive",
        "report_id": "report_compact_live_contract",
        "canonical_truth_sha256": "a" * 64,
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_filename": (
            "nico-comprehensive-comprun_contract-"
            "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
        ),
    }
    return {
        "canonical_truth_sha256": "a" * 64,
        "record": {
            "stage_results": {
                "final_comprehensive_report_generation": {
                    "assessment": canonical["assessment"],
                    "report_package": package,
                }
            }
        },
    }


def test_live_contract_accepts_compact_evidence_summary_without_retired_appendix(
    tmp_path: Path,
) -> None:
    acceptance = _load(ACCEPTANCE, "compact_contract_acceptance")
    contract = _load(CONTRACT, "compact_live_contract")
    payload = _payload()

    result = contract.validate_report(
        acceptance,
        "comprehensive",
        payload,
        tmp_path / "report.pdf",
        fallback=lambda *_args: pytest.fail("comprehensive must not use legacy fallback"),
    )

    assert result["semantic_contract"]["status"] == "passed"
    assert result["semantic_contract"]["compact_evidence_summary_verified"] is True
    assert result["semantic_contract"]["automated_draft_language_verified"] is True
    assert result["semantic_contract"]["unapproved_finality_absent"] is True
    assert "Evidence Appendix" not in payload["record"]["stage_results"][
        "final_comprehensive_report_generation"
    ]["report_package"]["markdown"]


def test_live_contract_rejects_unapproved_final_report_language(tmp_path: Path) -> None:
    acceptance = _load(ACCEPTANCE, "false_finality_acceptance")
    contract = _load(CONTRACT, "false_finality_contract")

    with pytest.raises(AssertionError, match="unapproved finality"):
        contract.validate_report(
            acceptance,
            "comprehensive",
            _payload(finality="FINAL REPORT"),
            tmp_path / "report.pdf",
            fallback=lambda *_args: {},
        )


def test_non_comprehensive_service_preserves_existing_validator(tmp_path: Path) -> None:
    contract = _load(CONTRACT, "fallback_contract")
    sentinel = {"status": "legacy-express-validated"}

    result = contract.validate_report(
        object(),
        "express",
        {},
        tmp_path / "express.pdf",
        fallback=lambda *_args: sentinel,
    )

    assert result == sentinel


def test_authoritative_runner_installs_compact_contract_and_forbids_final_filename() -> None:
    source = AUTHORITATIVE.read_text(encoding="utf-8")

    assert "import comprehensive_live_report_contract_v1 as compact_contract" in source
    assert "compact_contract.validate_report(" in source
    assert '"FINAL-PENDING-APPROVAL" not in upper_filename' in source
    assert 'upper_filename.count("AUTOMATED-DRAFT-PENDING-APPROVAL") <= 1' in source
    assert '"canonical_report_identity_verified": True' in source
    assert 'report["semantic_contract"]["compact_evidence_summary_verified"] is True' in source
    assert 'report["semantic_contract"]["automated_draft_language_verified"] is True' in source
    assert 'report["semantic_contract"]["unapproved_finality_absent"] is True' in source
