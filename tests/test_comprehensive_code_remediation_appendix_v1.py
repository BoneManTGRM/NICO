from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

from nico.comprehensive_code_remediation_appendix_v1 import (
    VERSION,
    _append_code_pages,
    build_code_remediation_plan,
    code_remediation_csv,
    install_comprehensive_code_remediation_appendix_v1,
)
from nico.comprehensive_premium_pdf_v6 import _build_pdf

ROOT = Path(__file__).resolve().parents[1]


def _assessment() -> dict:
    return {
        "maturity_signal": {
            "score": 84,
            "presented_score": 84,
            "score_band_label": "STRONG",
            "evidence_readiness_score": 80,
        },
        "sections": [],
        "scoring_weights": [],
        "executive_risk_register": [],
        "findings_register": [
            {
                "priority": "P1",
                "title": "Complexity hotspot: AssessmentWorkspace module",
                "category": "architecture",
                "location": "apps/web/app/assessment/AssessmentWorkspace.tsx:1",
                "evidence": "cyclomatic_complexity=180; loc=742; grade=F",
                "impact": "Concentrated branch logic increases regression risk.",
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
                "recommendation": "Decompose the hotspot into bounded modules and add characterization tests.",
                "acceptance_criteria": "Target functions fall below the approved complexity threshold and behavior remains covered.",
            },
            {
                "priority": "P2",
                "title": "Analyzer evidence unavailable",
                "category": "evidence",
                "location": "Scanner execution boundary",
                "evidence": "timeout",
                "impact": "Assurance remains limited.",
            },
        ],
    }


def _identity() -> dict:
    return {
        "run_id": "comprun_code_plan",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_code_plan",
        "customer_id": "customer_code_plan",
        "project_id": "project_code_plan",
    }


def test_code_plan_requires_exact_file_and_line_and_is_implementation_ready() -> None:
    plan = build_code_remediation_plan(_assessment())

    assert len(plan) == 1
    item = plan[0]
    assert item["remediation_id"] == "NICO-CODE-001"
    assert item["file_path"] == "apps/web/app/assessment/AssessmentWorkspace.tsx"
    assert item["line"] == 1
    assert "bounded responsibilities" in item["specific_code_update"]
    assert len(item["implementation_steps"]) == 5
    assert item["automatic_merge_allowed"] is False
    assert item["human_review_required"] is True

    csv_text = code_remediation_csv(plan)
    assert "NICO-CODE-001" in csv_text
    assert "specific_code_update" in csv_text
    assert "automatic_merge_allowed" in csv_text


def test_pdf_appendix_adds_code_specific_pages_and_reconciles_page_count() -> None:
    assessment = _assessment()
    assessment["code_remediation_plan"] = build_code_remediation_plan(assessment)
    base = _build_pdf(
        _identity(),
        assessment,
        [],
        [],
        [],
        {"individual_limitation_records": 1},
        "2026-07-24T00:00:00Z",
        1,
    )
    combined, page_count = _append_code_pages(
        base,
        identity=_identity(),
        assessment=assessment,
        limitations={"individual_limitation_records": 1},
    )

    reader = PdfReader(io.BytesIO(combined))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert page_count == len(reader.pages)
    assert page_count > len(PdfReader(io.BytesIO(base)).pages)
    assert "Code Remediation Plan" in text
    assert "apps/web/app/assessment/AssessmentWorkspace.tsx:1" in text
    assert "Specific code update" in text
    assert f"Final PDF pages: {page_count}" in text
    assert "\x7f" not in text


def test_installer_binds_report_appendix_and_blocks_automatic_merge() -> None:
    status = install_comprehensive_code_remediation_appendix_v1()
    source = (ROOT / "nico" / "comprehensive_code_remediation_appendix_v1.py").read_text(
        encoding="utf-8"
    )

    assert status["version"] == VERSION
    assert status["exact_location_code_plan"] is True
    assert status["pdf_code_pages"] is True
    assert status["machine_readable_code_plan"] is True
    assert status["automatic_merge_allowed"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
    assert '"markdown_code_section": True' in source
    assert '"html_code_section": True' in source
    assert '"code_remediation_csv": True' in source


def test_decision_grade_binding_installs_code_appendix_before_provider_binding() -> None:
    source = (ROOT / "nico" / "comprehensive_decision_grade_v5.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_code_remediation_appendix_v1" in source
    assert "code_remediation_bound" in source
    assert "exact_location_code_remediation_plan" in source
    assert "pdf_code_remediation_appendix" in source
    assert '"automatic_code_merge_allowed": False' in source
