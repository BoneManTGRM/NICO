from __future__ import annotations

import io

from pypdf import PdfReader

import nico.mid_report_v3 as v3


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
            "review_packet_sha256": "c" * 64,
            "exceptions": [
                {
                    "severity": "high",
                    "title": "Review required: Dependency Health",
                    "reason": "Two material records require validation.",
                    "blockers": ["Confirm affected resolved versions."],
                }
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
                "truth_status": "Verified",
                "summary": "Exact snapshot code evidence is attached.",
                "evidence": ["361 test paths and 100 pull requests were observed."],
                "findings": [],
                "unavailable": [],
                "missing_evidence_sources": [],
                "failed_evidence_tools": [],
                "scope_disclosures": ["This score does not replace line-by-line semantic review."],
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
    markdown = v3.decision_ready_markdown(_payload())

    assert "## Why the score is what it is" in markdown
    assert "| Code Audit | 88 | 20% | 17.6 |" in markdown
    assert markdown.count("Review required: Dependency Health") == 1
    assert "Suggested repairs are report-only" in markdown


def test_mid_v3_install_rebinds_all_report_formats() -> None:
    installed = v3.install_mid_report_v3()

    assert installed["pdf_style"] == v3.PDF_STYLE_VERSION
    if installed["status"] == "installed":
        assert installed["score_explanation"] is True
        assert installed["prioritized_repairs"] is True
        assert installed["client_repository_write_allowed"] is False
    else:
        assert installed["status"] == "already_installed"
