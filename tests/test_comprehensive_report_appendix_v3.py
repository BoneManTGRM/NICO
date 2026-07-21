from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

from nico.comprehensive_report_appendix_v3 import (
    APPENDIX_HEADING,
    LEGACY_REVIEW_HEADING,
    REVIEW_HEADING,
    VERSION,
    build_comprehensive_report_package,
    install_native_provider_binding,
)


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "nico" / "api" / "comprehensive_production_bootstrap.py"

IDENTITY = {
    "run_id": "comprun_appendix_v3_001",
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger_appendix_v3_001",
    "customer_id": "customer_appendix",
    "project_id": "project_appendix",
}


def _assessment() -> dict:
    return {
        "status": "complete",
        "service_id": "comprehensive",
        "executive_summary": "Evidence-bound technical assessment requires human review.",
        "maturity_signal": {
            "level": "Senior",
            "score": 88,
            "presented_score": 88,
            "evidence_readiness_score": 81,
        },
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 88,
                "presented_score": 88,
                "status": "green",
                "presented_status": "green",
                "summary": "Snapshot-bound code evidence was reviewed.",
                "evidence": ["Exact immutable commit was captured."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "functional_qa",
                "label": "Functional QA",
                "score": None,
                "presented_score": None,
                "status": "gray",
                "presented_status": "gray",
                "summary": "Runtime user journeys require human-supplied evidence.",
                "evidence": ["Repository test paths were inventoried."],
                "findings": [],
                "unavailable": ["No stakeholder acceptance run was supplied."],
            },
        ],
        "unavailable_data_notes": [
            "Stakeholder acceptance evidence was not supplied."
        ],
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }


def _stages() -> dict[str, dict]:
    stages = {
        "authorization_and_scope": {
            "status": "complete",
            "summary": "Authorization and scope were verified.",
            "evidence": {
                "authorized": True,
                "repository": IDENTITY["repository"],
            },
        },
        "immutable_repository_snapshot": {
            "status": "complete",
            "summary": "One immutable commit was captured.",
            "evidence": {
                "snapshot_commit_sha": IDENTITY["commit_sha"],
                "snapshot_id": "snapshot_appendix_001",
            },
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "summary": "Canonical evidence and scoring were reconciled.",
            "assessment": _assessment(),
            "evidence": {"technical_score": 88},
        },
        "functional_qa": {
            "status": "complete",
            "summary": "Functional QA evidence was bounded to repository proof.",
            "evidence": {"test_path_count": 533},
            "unavailable_data_notes": [
                "Runtime acceptance requires human-supplied evidence."
            ],
        },
        "six_month_roadmap": {
            "status": "complete",
            "summary": "A six-month roadmap was sequenced.",
            "roadmap": [
                {
                    "window": "0-30 days",
                    "objective": "Close material evidence gaps.",
                }
            ],
            "evidence": {"roadmap_window_count": 3},
        },
        "staffing_sequencing_and_cost": {
            "status": "complete",
            "summary": "A role-based staffing plan was generated.",
            "staffing_plan": [
                {
                    "role": "Product Engineering Architect",
                    "sequence": 1,
                }
            ],
            "evidence": {"recommended_role_count": 3},
        },
    }
    return stages


def _package() -> dict:
    return build_comprehensive_report_package(
        identity=IDENTITY,
        stage_results=_stages(),
    )


def test_markdown_and_html_include_the_same_evidence_appendix() -> None:
    result = _package()
    report = result["report_package"]

    assert result["status"] == "complete"
    assert APPENDIX_HEADING in report["markdown"]
    assert "<h2>Evidence Appendix</h2>" in report["html"]
    assert "### A1. Authorization and Scope — COMPLETE" in report["markdown"]
    assert "Stage ID: `authorization_and_scope`" in report["markdown"]
    assert "snapshot_commit_sha" in report["markdown"]
    assert "Runtime acceptance requires human-supplied evidence." in report["markdown"]
    assert report["evidence_appendix_present"] is True
    assert report["appendix_contract_schema"] == VERSION
    assert len(report["markdown_sha256"]) == 64
    assert len(report["html_sha256"]) == 64


def test_appendix_precedes_human_review_acceptance_gate_and_preserves_boundary() -> None:
    report = _package()["report_package"]
    markdown = report["markdown"]

    assert markdown.index(APPENDIX_HEADING) < markdown.index(REVIEW_HEADING)
    assert LEGACY_REVIEW_HEADING not in markdown
    assert "<h2>Human Review and Acceptance Gate</h2>" in report["html"]
    assert report["human_review_acceptance_gate_present"] is True
    assert "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED" in markdown
    assert report["human_review_required"] is True
    assert report["client_delivery_allowed"] is False


def test_pdf_remains_valid_and_contains_matching_chapter_headings() -> None:
    report = _package()["report_package"]
    raw = base64.b64decode(report["pdf_base64"], validate=True)
    reader = PdfReader(io.BytesIO(raw))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert raw.startswith(b"%PDF")
    assert "Evidence Appendix" in text
    assert "Human Review and Acceptance Gate" in text
    assert "NICO MID TECHNICAL" not in text.upper()


def test_quality_contract_requires_both_chapters_in_readable_formats() -> None:
    result = _package()
    quality = result["report_quality_contract"]

    assert quality["appendix_contract_schema"] == VERSION
    assert quality["full_evidence_appendix"] is True
    assert quality["markdown_evidence_appendix"] is True
    assert quality["html_evidence_appendix"] is True
    assert quality["markdown_human_review_acceptance_gate"] is True
    assert quality["html_human_review_acceptance_gate"] is True
    assert quality["human_review_required"] is True
    assert quality["client_delivery_allowed"] is False


def test_native_provider_binding_replaces_the_report_builder() -> None:
    from nico import comprehensive_native_providers as providers

    status = install_native_provider_binding()

    assert status["bound"] is True
    assert providers.build_comprehensive_report_package is build_comprehensive_report_package
    assert status["markdown_evidence_appendix"] is True
    assert status["html_evidence_appendix"] is True
    assert status["pdf_evidence_appendix"] is True
    assert status["markdown_human_review_acceptance_gate"] is True
    assert status["html_human_review_acceptance_gate"] is True
    assert status["pdf_human_review_acceptance_gate"] is True


def test_production_bootstrap_binds_appendix_before_provider_install() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    binding = source.index("report_binding = install_native_provider_binding()")
    providers = source.index("native_providers = install_native_comprehensive_providers(target)")
    executors = source.index("executors = build_production_capability_executors(target)")

    assert binding < providers < executors
    assert '"report_binding_before_provider_install": True' in source
    assert 'if COMPREHENSIVE_PRODUCTION_RUNTIME["report_binding"].get("bound") is not True:' in source
