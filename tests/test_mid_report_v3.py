from __future__ import annotations

import io

from pypdf import PdfReader

import nico.mid_report_v3 as v3
from nico.mid_report_v3_compat import (
    MID_REPORT_IDENTITY_VERSION,
    MID_REPORT_PRESENTATION_VERSION,
    _presentation_review,
    _presentation_sections,
    _rendering_payload,
)


def _payload() -> dict:
    return {
        "status": "draft",
        "report_id": "mid_report_test",
        "run_id": "midrun_test",
        "repository": "owner/repo",
        "snapshot_commit_sha": "a" * 40,
        "client_name": "Client",
        "project_name": "Project",
        "generated_at": "2026-07-15T18:00:00Z",
        "source_identity_sha256": "b" * 64,
        "review_packet": {
            "packet_version": "mid-review-by-exception-v1",
            "review_packet_id": "packet_one",
            "review_packet_sha256": "c" * 64,
            "exceptions": [
                {
                    "item_id": "limited",
                    "category": "low_confidence_or_limited_conclusion",
                    "section_id": "dependency_health",
                    "severity": "high",
                    "title": "Limited dependency conclusion",
                    "reason": "Two material records require validation.",
                    "blockers": ["Confirm affected resolved versions."],
                },
                {
                    "item_id": "score",
                    "category": "score_changing_claim",
                    "section_id": "dependency_health",
                    "severity": "medium",
                    "title": "Dependency score claim",
                    "reason": "The score depends on review.",
                    "blockers": ["Confirm the score evidence."],
                },
            ],
        },
        "evidence_coverage": {
            "percent": 100,
            "numerator": 12,
            "denominator": 12,
            "method": "Twelve explicit exact-run evidence units.",
        },
        "decision_summary": {
            "maturity_level": "Senior",
            "technical_score": 84,
            "evidence_coverage_percent": 100,
            "review_items": 7,
            "primary_score_constraints": [
                "Dependency: 2 corroborated material record(s).",
                "Velocity / Complexity remains below green.",
            ],
            "priority_actions": [
                "Validate the two dependency records against the current resolved graph.",
                "Decompose one bounded complexity hotspot after characterization tests.",
            ],
        },
        "mid_score_explanation": {
            "contributions": [
                {"label": "Code Audit", "score": 88, "weight": 20, "weighted_points": 17.6},
                {"label": "Dependency / Library Ecosystem", "score": 55, "weight": 15, "weighted_points": 8.25},
                {"label": "Secrets Exposure Review", "score": 88, "weight": 10, "weighted_points": 8.8},
            ]
        },
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 88,
                "truth_status": "Verified with limitations",
                "summary": "Exact snapshot code evidence is attached.",
                "evidence": ["361 test paths and 100 pull requests were observed."],
                "findings": [],
                "unavailable": ["This score does not replace line-by-line semantic review."],
                "missing_evidence_sources": [],
                "failed_evidence_tools": [],
                "scope_disclosures": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 55,
                "truth_status": "Verified with limitations",
                "summary": "Structured scanners completed with two corroborated records.",
                "evidence": ["pip-audit, npm audit, and OSV-Scanner completed."],
                "findings": ["Remediate two corroborated records before approval."],
                "unavailable": [],
                "missing_evidence_sources": [],
                "failed_evidence_tools": [],
                "scope_disclosures": [],
                "dependency_scanner_triage": {"material_finding_count": 2},
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 64,
                "truth_status": "Failed",
                "summary": "One required tool failed.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
                "missing_evidence_sources": [],
                "failed_evidence_tools": ["semgrep"],
                "scope_disclosures": [],
            },
        ],
        "repair_intelligence": {
            "candidate_count": 1,
            "code_suggestion_count": 0,
            "candidates": [
                {
                    "rank": 1,
                    "title": "Dependency records require exact-version remediation",
                    "severity": "high",
                    "priority_score": 66.2,
                    "effort": "medium",
                    "impact": "Unresolved dependency advisories can increase exploit and support risk.",
                    "recommended_action": "Confirm resolved versions, update only affected packages, and rerun all scanners.",
                    "evidence": ["Two corroborated material records."],
                    "rollback_plan": "Restore the prior lockfile if focused and full verification fail.",
                    "tgrm": {"level": 2},
                }
            ],
        },
    }


def test_mid_v3_pdf_is_decision_ready_and_explains_score() -> None:
    payload = _payload()

    pdf = v3.decision_ready_pdf(payload)

    assert pdf.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = " ".join(text.split())
    compact = "".join(text.split())
    assert "MIDASSESSMENT" in compact
    assert "Executive decision brief" in text
    assert "Why the technical score is what it is" in text
    assert "Dependency: 2 corroborated material record(s)." in normalized
    assert "Section scorecard" in text
    assert "Prioritized repair plan" in text
    assert "Consolidated human review" in text
    assert "NICO did not modify the assessed repository" in normalized
    assert "DRAFT - HUMAN REVIEW REQUIRED" in normalized


def test_mid_v3_markdown_has_score_contributions_and_no_duplicate_review_headings() -> None:
    payload = _payload()
    _presentation_review(payload)
    rendered = _rendering_payload(payload)
    markdown = v3.decision_ready_markdown(rendered)

    assert "## Why the score is what it is" in markdown
    assert "| Code Audit | 88 | 20% | 17.6 |" in markdown
    assert markdown.count("Review required: Dependency Health") == 1
    assert "Suggested repairs are report-only" in markdown


def test_mid_v3_presentation_preserves_source_truth_and_review_identity() -> None:
    payload = _payload()
    source_exceptions = list(payload["review_packet"]["exceptions"])

    _presentation_sections(payload)
    _presentation_review(payload)

    code = next(item for item in payload["sections"] if item["id"] == "code_audit")
    dependency = next(item for item in payload["sections"] if item["id"] == "dependency_health")
    static = next(item for item in payload["sections"] if item["id"] == "static_analysis")
    assert code["truth_status"] == "Verified with limitations"
    assert code["display_truth_status"] == "Verified"
    assert dependency["display_truth_status"] == "Verified with limitations"
    assert static["failed_evidence_tools"] == ["semgrep"]
    assert payload["review_packet"]["packet_version"] == "mid-review-by-exception-v1"
    assert payload["review_packet"]["review_packet_id"] == "packet_one"
    assert payload["review_packet"]["review_packet_sha256"] == "c" * 64
    assert payload["review_packet"]["exceptions"] == source_exceptions
    assert len(payload["review_packet"]["display_exceptions"]) == 1
    assert payload["decision_summary"]["source_review_items"] == 2
    assert payload["decision_summary"]["review_items"] == 1
    assert MID_REPORT_IDENTITY_VERSION == "mid-assessment-draft-v2"
    assert MID_REPORT_PRESENTATION_VERSION == "mid-assessment-decision-ready-v3"


def test_mid_v3_install_rebinds_all_report_formats() -> None:
    installed = v3.install_mid_report_v3()

    assert installed["pdf_style"] == v3.PDF_STYLE_VERSION
    if installed["status"] == "installed":
        assert installed["score_explanation"] is True
        assert installed["prioritized_repairs"] is True
        assert installed["client_repository_write_allowed"] is False
    else:
        assert installed["status"] == "already_installed"
