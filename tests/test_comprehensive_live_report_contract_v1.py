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


def _payload(
    *,
    finality: str = "AUTOMATED DRAFT",
    incomplete_count: int = 7,
    retired_appendix: bool = False,
    identity: str = "legacy",
) -> dict:
    identities = {
        "legacy": ("NICO Comprehensive Technical Assessment",),
        "decision_grade": (
            "NICO COMPREHENSIVE",
            "Decision-Grade Technical Assessment",
        ),
        "missing": ("Unrelated Technical Report",),
    }
    identity_lines = identities[identity]
    sections = (
        "Functional QA",
        "Platform Parity",
        "Six-Month Roadmap",
        "Staffing, Sequencing, and Cost",
        "Human Review and Acceptance Gate",
    )
    lifecycle = (
        f"{finality} · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    )
    incomplete = f"Incomplete applicable analyzers: {incomplete_count}"
    appendix = "## Evidence Appendix" if retired_appendix else ""
    markdown = "\n\n".join(
        value
        for value in (
            "\n".join(f"# {line}" for line in identity_lines),
            *sections,
            "## Evidence Package Summary",
            incomplete,
            appendix,
            lifecycle,
            "93/100",
        )
        if value
    )
    rendered_html = (
        "<!doctype html><html><body>"
        + " ".join(
            value
            for value in (
                *identity_lines,
                *sections,
                "Evidence Package Summary",
                incomplete,
                "Evidence Appendix" if retired_appendix else "",
                lifecycle,
                "93/100",
            )
            if value
        )
        + "</body></html>"
    )
    pdf = _pdf(
        *identity_lines,
        *sections,
        "Client Evidence Summary",
        incomplete,
        *("Evidence Appendix",) if retired_appendix else (),
        lifecycle,
        "93/100",
    )
    canonical = {
        "canonical_truth_sha256": "a" * 64,
        "assessment": {
            "client_delivery_allowed": False,
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
        "human_review_required": True,
        "client_delivery_allowed": False,
        "record": {
            "human_review_required": True,
            "client_delivery_allowed": False,
            "stage_results": {
                "final_comprehensive_report_generation": {
                    "assessment": canonical["assessment"],
                    "report_package": package,
                }
            },
        },
    }


def _validate(payload: dict, tmp_path: Path, name: str) -> dict:
    acceptance = _load(ACCEPTANCE, f"{name}_acceptance")
    contract = _load(CONTRACT, f"{name}_contract")
    return contract.validate_report(
        acceptance,
        "comprehensive",
        payload,
        tmp_path / f"{name}.pdf",
        fallback=lambda *_args: pytest.fail("comprehensive must not use legacy fallback"),
    )


def test_live_contract_accepts_compact_evidence_summary_without_retired_appendix(
    tmp_path: Path,
) -> None:
    payload = _payload(incomplete_count=7)
    result = _validate(payload, tmp_path, "compact_live")

    semantic = result["semantic_contract"]
    assert semantic["status"] == "passed"
    assert semantic["canonical_report_identity_verified"] is True
    assert semantic["compact_evidence_summary_verified"] is True
    assert semantic["canonical_incomplete_analyzer_count_verified"] is True
    assert semantic["retired_evidence_appendix_absent"] is True
    assert semantic["automated_draft_language_verified"] is True
    assert semantic["unapproved_finality_absent"] is True
    markdown = payload["record"]["stage_results"][
        "final_comprehensive_report_generation"
    ]["report_package"]["markdown"]
    assert "Incomplete applicable analyzers: 7" in markdown
    assert "Evidence Appendix" not in markdown


def test_live_contract_accepts_approved_decision_grade_cover_identity(
    tmp_path: Path,
) -> None:
    result = _validate(
        _payload(identity="decision_grade"),
        tmp_path,
        "decision_grade_identity",
    )

    assert result["semantic_contract"]["canonical_report_identity_verified"] is True


def test_live_contract_rejects_missing_comprehensive_identity(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="canonical report identity"):
        _validate(_payload(identity="missing"), tmp_path, "missing_identity")


def test_live_contract_rejects_unapproved_final_report_language(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="unapproved finality"):
        _validate(_payload(finality="FINAL REPORT"), tmp_path, "false_finality")


def test_live_contract_rejects_restored_raw_evidence_appendix(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="retired raw Evidence Appendix"):
        _validate(_payload(retired_appendix=True), tmp_path, "retired_appendix")


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


def test_synthetic_comprehensive_fixture_preserves_existing_validator(tmp_path: Path) -> None:
    contract = _load(CONTRACT, "synthetic_fallback_contract")
    acceptance = type(
        "Acceptance",
        (),
        {
            "report_package": staticmethod(lambda *_args: {"json": {}}),
            "assessment_payload": staticmethod(lambda *_args: {}),
        },
    )()
    sentinel = {"status": "synthetic-semantic-fixture"}

    result = contract.validate_report(
        acceptance,
        "comprehensive",
        {},
        tmp_path / "synthetic.pdf",
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
