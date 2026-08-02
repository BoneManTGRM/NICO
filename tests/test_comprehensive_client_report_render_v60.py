from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_client_report_render_v60 import (
    reconcile_before_existing_report_renderer,
    validate_existing_report_accuracy,
)

ROOT = Path(__file__).resolve().parents[1]


def _pdf(*pages: str) -> bytes:
    stream = io.BytesIO()
    writer = canvas.Canvas(stream, pagesize=letter, invariant=1)
    for text in pages:
        writer.drawString(72, 720, text)
        writer.showPage()
    writer.save()
    return stream.getvalue()


def _scanner(name: str, status: str, findings: int = 0) -> dict[str, object]:
    return {
        "scanner_name": name,
        "status": status,
        "exact_commit_match": True,
        "artifact_retained": True,
        "finding_count": findings,
    }


def _canonical() -> dict[str, object]:
    scanners = [
        _scanner("bandit", "completed"),
        _scanner("eslint", "completed"),
        _scanner("gitleaks", "completed_with_findings", 6),
        _scanner("npm-audit", "completed"),
        _scanner("osv-scanner", "completed_with_findings", 59),
        _scanner("pip-audit", "completed"),
        _scanner("semgrep", "completed"),
        _scanner("trufflehog", "completed_with_findings", 11),
        _scanner("typescript", "completed"),
    ]
    return {
        "requested_analyzers": 9,
        "applicable_analyzers": 9,
        "assessment": {
            "technical_score": 92,
            "maturity_level": "Senior",
            "incomplete_analyzers": ["bandit", "gitleaks"],
            "analyzer_execution_coverage": 78,
        },
        "scorecard": {
            "maturity": "Exceptional",
            "analyzer_execution_coverage": 88,
        },
        "scanner_execution_records": scanners,
        "stage_summaries": [
            {
                "stage_id": "decision_report_generation",
                "status": "complete",
                "report_contract_status": "blocked",
                "report_contract_reason": "executive_decision_brief_page_gate_failed",
            }
        ],
        "canonical_findings": [
            {
                "symbol": "apply_scanner_artifact_scoring",
                "recommendation": "Split `appy_ l scanner_artifact_scoring` safely.",
            }
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_pre_render_reconciliation_preserves_existing_rendered_surfaces() -> None:
    original_pdf = base64.b64encode(_pdf("Existing approved NICO report")).decode("ascii")
    package = {
        "json": _canonical(),
        "markdown": "existing markdown",
        "html": "<p>existing html</p>",
        "pdf_base64": original_pdf,
    }

    result = reconcile_before_existing_report_renderer(package)

    assert result["markdown"] == package["markdown"]
    assert result["html"] == package["html"]
    assert result["pdf_base64"] == original_pdf
    assert result["report_design_contract"]["existing_renderer_preserved"] is True
    assert result["report_design_contract"]["redesign_performed"] is False


def test_pre_render_reconciliation_corrects_truth_and_retains_diagnostics_outside_json() -> None:
    result = reconcile_before_existing_report_renderer({"json": _canonical()})
    canonical = result["json"]

    assert canonical["assessment"]["incomplete_analyzers"] == []
    assert canonical["assessment"]["analyzer_execution_coverage"] == 100
    assert canonical["scorecard"]["analyzer_execution_coverage"] == 100
    assert canonical["assessment"]["maturity_level"] == "Exceptional"
    stage = canonical["stage_summaries"][0]
    assert "report_contract_status" not in stage
    assert "report_contract_reason" not in stage
    audit = result["pre_finalization_audit"]
    assert len(audit["entries"]) == 2
    assert audit["retained_outside_client_facing_canonical_truth"] is True
    assert "appy_ l scanner_artifact_scoring" not in str(canonical)
    assert "apply_scanner_artifact_scoring" in str(canonical)


def test_final_accuracy_validation_accepts_existing_design_with_canonical_truth() -> None:
    canonical_package = reconcile_before_existing_report_renderer({"json": _canonical()})
    markdown = "\n".join(
        (
            "NICO COMPREHENSIVE",
            "Canonical Technical Scorecard",
            "Analyzer execution coverage is 100%",
            "Incomplete applicable analyzers: 0",
            "Maturity Exceptional",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
        )
    )
    canonical_package.update(
        {
            "markdown": markdown,
            "html": f"<main>{markdown}</main>",
            "pdf_base64": base64.b64encode(_pdf(markdown)).decode("ascii"),
        }
    )

    result = validate_existing_report_accuracy(canonical_package)

    assert result["existing_visual_design_preserved"] is True
    assert result["canonical_coverage_value"] == 100
    assert result["canonical_incomplete_analyzer_count"] == 0
    assert result["canonical_maturity_label"] == "Exceptional"
    assert result["production_pdf_validated"] is True


def test_final_accuracy_validation_rejects_stale_report_truth() -> None:
    package = reconcile_before_existing_report_renderer({"json": _canonical()})
    markdown = "\n".join(
        (
            "NICO COMPREHENSIVE",
            "Canonical Technical Scorecard",
            "Analyzer execution coverage is 88%",
            "Incomplete applicable analyzers: 0",
            "Maturity Exceptional",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
        )
    )
    package.update(
        {
            "markdown": markdown,
            "html": f"<main>{markdown}</main>",
            "pdf_base64": base64.b64encode(_pdf(markdown)).decode("ascii"),
        }
    )

    with pytest.raises(ValueError, match="conflicting analyzer coverage"):
        validate_existing_report_accuracy(package)


def test_final_runtime_preserves_renderer_and_binds_phase17_static_aliases() -> None:
    source = (
        ROOT / "nico" / "comprehensive_client_report_render_v60.py"
    ).read_text(encoding="utf-8")
    mobile = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")

    assert "rebuild_premium_client_artifacts_with_appendix" not in source
    assert "rebuild_single_pass_premium_artifacts" not in source
    assert "phase17.prepare_client_report_package = prepare" in source
    assert "phase17.finalize_client_report_package = finalize" in source
    assert '"existing_renderer_preserved": True' in source
    assert '"redesign_performed": False' in source
    assert '"existing_report_renderer_preserved": True' in mobile
    assert '"report_redesign_performed": False' in mobile
