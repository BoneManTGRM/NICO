from __future__ import annotations

import io

from pypdf import PdfReader

import nico.mid_assessment_report as report_module
from nico.mid_report_professional_v3 import MID_REPORT_V3_VERSION


def _section(section_id: str, score: int | None, truth_status: str, *, findings=None, unavailable=None, source="repository_evidence") -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "gray" if score is None else "green" if score >= 80 else "yellow",
        "truth_status": truth_status,
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": [f"Direct evidence for {section_id}."],
        "findings": findings or [],
        "unavailable": unavailable or [],
        "missing_evidence_sources": [],
        "failed_evidence_tools": [],
        "source_classification": source,
        "direct_repository_proof": source == "repository_evidence",
        "human_review_required": truth_status != "Verified",
        "unsupported_claims_permitted": False,
    }


def _record_and_packet() -> tuple[dict, dict, dict]:
    sections = [
        _section("code_audit", 80, "Verified"),
        _section("dependency_health", 70, "Verified with limitations", findings=["One dependency advisory requires review."]),
        _section("secrets_review", 88, "Verified"),
        _section("static_analysis", 74, "Verified with limitations", findings=["Two static findings require triage."]),
        _section("ci_cd", 95, "Verified"),
        _section("architecture_debt", 86, "Verified"),
        _section("velocity_complexity", 76, "Verified with limitations", findings=["Complexity concentration requires staged repair."]),
        _section("functional_qa", None, "Human review required", source="user_submitted_external_context"),
    ]
    truth = {
        "version": "mid-truth-status-v2",
        "sections": sections,
        "summary": {
            "verified": 4,
            "verified_with_limitations": 3,
            "unavailable": 0,
            "failed": 0,
            "human_review_required": 1,
            "items_requiring_review": 4,
            "unsupported_claims_permitted": 0,
        },
        "evidence_coverage": {
            "label": "Automated evidence coverage",
            "calculated": True,
            "percent": 100,
            "numerator": 12,
            "denominator": 12,
            "method": "Twelve explicit evidence units.",
        },
        "unsupported_claims_permitted": 0,
    }
    record = {
        "run_id": "midrun_report_v3",
        "customer_id": "customer_v3",
        "project_id": "project_v3",
        "repository": "owner/repository",
        "snapshot_id": "snapshot_v3",
        "snapshot_commit_sha": "a" * 40,
        "status": "complete",
        "request": {"client_name": "Client", "project_name": "Project"},
        "response": {
            "assessment": {"maturity_signal": {"level": "Mid", "score": 81}, "sections": sections},
            "mid_truth_status": truth,
        },
    }
    duplicate_blocker = "One dependency advisory requires review."
    packet = {
        "review_packet_id": "packet_v3",
        "review_packet_sha256": "b" * 64,
        "summary": {"items_requiring_review": 3},
        "exceptions": [
            {
                "section_id": "dependency_health",
                "title": "Limited conclusion in Dependency",
                "severity": "medium",
                "category": "low_confidence_or_limited_conclusion",
                "reason": "Dependency evidence requires review.",
                "blockers": [duplicate_blocker],
            },
            {
                "section_id": "dependency_health",
                "title": "Score-affecting claim in Dependency",
                "severity": "medium",
                "category": "score_changing_claim",
                "reason": "Dependency evidence requires review.",
                "blockers": [duplicate_blocker],
            },
            {
                "section_id": "functional_qa",
                "title": "Human validation required for Functional QA",
                "severity": "medium",
                "category": "inference_or_external_context",
                "reason": "User-submitted context requires validation.",
                "blockers": [],
            },
        ],
        "verified_sections": ["code_audit", "secrets_review", "ci_cd", "architecture_debt"],
    }
    identity = report_module._source_identity(record, packet, truth)
    return record, packet, identity


def test_v3_payload_explains_score_and_deduplicates_review_exceptions() -> None:
    record, packet, identity = _record_and_packet()

    payload = report_module._report_payload(record, packet, identity, "2026-07-15T20:00:00Z")

    assert payload["report_version"] == MID_REPORT_V3_VERSION
    assert payload["detail_level"] == 3
    assert payload["technical_score"] == 81
    assert payload["score_integrity"]["calculated_from_seven_technical_sections"] is True
    assert payload["score_integrity"]["evidence_coverage_changes_score"] is False
    assert payload["decision_summary"]["human_context_section_count"] == 1
    assert payload["review_exception_original_count"] == 3
    assert payload["review_exception_final_count"] == 2
    assert payload["repair_intelligence"]["candidate_count"] >= 3
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False


def test_v3_markdown_and_pdf_are_decision_ready() -> None:
    record, packet, identity = _record_and_packet()
    payload = report_module._report_payload(record, packet, identity, "2026-07-15T20:00:00Z")

    markdown = report_module._markdown(payload)
    pdf = report_module._pdf(payload)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    normalized = " ".join(text.split())

    assert "## Decision summary" in markdown
    assert "The score is the weighted result of seven technical sections" in markdown
    assert "Human-context sections unscored: 1" in markdown
    assert "## Prioritized repair intelligence" in markdown
    assert "NICO did not modify the assessed repository" in markdown
    assert pdf.startswith(b"%PDF")
    assert "MID TECHNICAL ASSESSMENT" in normalized
    assert "Weighted Technical Scorecard" in normalized
    assert "Primary score constraints" in normalized
    assert "Prioritized Repair Intelligence" in normalized
    assert "Human-Context Modules" in normalized
    assert "Original exception records: 3" in normalized
    assert "Decision-ready deduplicated items: 2" in normalized
    assert "Score-affecting claim in Dependency" not in normalized
