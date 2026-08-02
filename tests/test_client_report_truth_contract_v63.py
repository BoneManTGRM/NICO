from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.client_report_completion_v2 import _replace_pdf_status_terms
from nico.client_report_truth_contract_v63 import (
    ANALYZER_STATUSES,
    apply_client_report_truth_contract,
    report_truth_markdown,
)


def _fixture() -> dict:
    return {
        "technical_score": 92,
        "sections": [
            {
                "id": "dependency_library_ecosystem",
                "label": "Dependency / Library Ecosystem",
                "status": "strong",
                "score": 96,
                "verified_material": 0,
                "review_required": 59,
                "evidence": ["OSV scanner artifact retained at the exact commit."],
                "unavailable": ["59 candidates require human triage."],
            },
            {
                "id": "secrets_exposure_review",
                "label": "Secrets Exposure Review",
                "status": "strong",
                "score": 96,
                "verified_material": 0,
                "review_required": 17,
                "evidence": ["Gitleaks and TruffleHog artifacts retained."],
            },
            {
                "id": "ci_cd_analysis",
                "label": "CI/CD Analysis",
                "score": 100,
                "evidence": ["Workflow configuration matched the exact commit."],
                "assessed_commit_required_check_health": "not_observed",
                "current_default_branch_required_check_health": False,
            },
        ],
        "canonical_findings": [
            {
                "finding_id": "NICO-FINDING-1",
                "location": "nico/example.py:10",
                "observed_evidence": "cyclomatic_complexity=61",
                "evidence_quality": "review required; exact commit match=True",
                "disposition": "PROPOSED · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED",
            }
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "osv-scanner",
                "status": "completed_with_findings",
                "completed": True,
                "exact_commit_match": True,
                "findings": [{"id": "GHSA-example"}],
            },
            {
                "scanner_name": "bandit",
                "status": "failed",
                "completed": False,
                "exact_commit_match": True,
            },
        ],
    }


def test_automated_report_is_draft_and_delivery_blocked() -> None:
    output = apply_client_report_truth_contract(_fixture())
    truth = output["canonical_report_truth"]
    assert truth["automated_status"] == "automated_draft"
    assert truth["human_review_status"] == "pending_human_approval"
    assert truth["client_delivery_status"] == "blocked_pending_human_approval"
    assert output["report_finality"] == "automated_draft"
    assert output["client_delivery_allowed"] is False
    assert output["human_review_required"] is True


def test_dependency_and_secret_scores_are_provisional_until_triage() -> None:
    output = apply_client_report_truth_contract(_fixture())
    dependency, secrets, _ci = output["sections"]
    assert dependency["status_display"] == "Provisional Strong"
    assert dependency["review_required_candidates"] == 59
    assert dependency["score_status"] == "assurance_only_until_triaged"
    assert secrets["status_display"] == "Provisional Strong"
    assert secrets["review_required_candidates"] == 17
    assert secrets["score_effect"] == "assurance_only_until_triaged"


def test_ci_configuration_score_is_not_operational_readiness() -> None:
    output = apply_client_report_truth_contract(_fixture())
    ci = output["sections"][2]["ci_status"]
    assert ci["configuration_maturity_score"] == 100
    assert ci["operational_readiness"] == "human_review_required"
    assert ci["required_check_health"] == "not_observed"
    assert ci["current_default_branch_health"] is False
    assert ci["configuration_score_is_not_operational_readiness"] is True


def test_every_finding_has_evidence_status_and_confidence() -> None:
    output = apply_client_report_truth_contract(_fixture())
    finding = output["canonical_findings"][0]
    assert finding["evidence_status"] == "review_required"
    assert finding["confidence"] == "medium_confidence"
    assert finding["human_review_status"] == "required"


def test_authoritative_analyzer_status_model_is_bounded() -> None:
    output = apply_client_report_truth_contract(_fixture())
    statuses = {item["authoritative_status"] for item in output["authoritative_analyzer_statuses"]}
    assert statuses <= ANALYZER_STATUSES
    assert statuses == {"completed_with_findings", "failed"}


def test_human_approval_requires_complete_metadata() -> None:
    fixture = _fixture()
    fixture["human_approval_metadata"] = {
        "reviewer_name_or_id": "reviewer-1",
        "reviewer_role": "Security Reviewer",
        "approval_timestamp": "2026-08-02T12:00:00Z",
        "approval_decision": "approved",
        "evidence_manifest_reviewed": True,
        "scanner_candidates_triaged": False,
        "client_delivery_authorized": True,
    }
    incomplete = apply_client_report_truth_contract(fixture)
    assert incomplete["client_delivery_allowed"] is False

    fixture["human_approval_metadata"]["scanner_candidates_triaged"] = True
    approved = apply_client_report_truth_contract(fixture)
    assert approved["canonical_report_truth"]["automated_status"] == "human_approved_final"
    assert approved["client_delivery_allowed"] is True


def test_markdown_uses_client_safe_status_language() -> None:
    output = apply_client_report_truth_contract(_fixture())
    markdown = report_truth_markdown(output)
    assert "Automated Draft" in markdown
    assert "Pending Human Approval" in markdown
    assert "Client Delivery Blocked" in markdown
    assert "Human Approved Final" not in markdown


def test_pdf_status_replacement_removes_misleading_final_language() -> None:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(72, 720, "FINAL REPORT")
    document.drawString(72, 700, "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED")
    document.save()
    repaired = _replace_pdf_status_terms(buffer.getvalue())
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(repaired)).pages)
    assert "AUTOMATED DRAFT" in extracted
    assert "FINAL REPORT" not in extracted
    assert "CLIENT DELIVERY BLOCKED" in extracted
