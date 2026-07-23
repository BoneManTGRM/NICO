from __future__ import annotations

import io

from pypdf import PdfReader

from nico.mid_report_professional_v4 import (
    MID_REPORT_V4_VERSION,
    _enhance,
    _markdown,
    _pdf,
)


def _section(section_id: str, label: str, score: int, truth: str = "Verified") -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "truth_status": truth,
        "confidence": "scanner-and-repository-bound",
        "summary": f"Evidence-bound conclusion for {label}.",
        "evidence": [
            f"Repository evidence retained for {label}.",
            f"Analyzer or workflow evidence retained for {label}.",
            f"Same-run identity evidence retained for {label}.",
        ],
        "findings": [f"Review the principal {label} constraint before client delivery."],
        "unavailable": [f"Additional corroboration remains required for {label}."],
        "scope_disclosures": [f"The {label} conclusion is bounded to the captured evidence."],
        "score_evidence_breakdown": {
            "base_score": max(0, score - 10),
            "verified_control_credit": 10,
            "final_score": score,
        },
    }


def _context(section_id: str, label: str) -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": None,
        "truth_status": "Unavailable",
        "summary": f"{label} requires validated external context.",
        "evidence": [],
        "findings": [],
        "unavailable": [f"No validated {label} evidence was attached."],
    }


def _payload() -> dict:
    technical = [
        _section("code_audit", "Code Audit", 60),
        _section("dependency_health", "Dependency / Library Ecosystem", 72, "Verified with limitations"),
        _section("secrets_review", "Secrets Exposure Review", 80, "Verified with limitations"),
        _section("static_analysis", "Static Analysis", 49, "Verified with limitations"),
        _section("ci_cd", "CI/CD Analysis", 83, "Verified with limitations"),
        _section("architecture_debt", "Architecture & Technical Debt", 85),
        _section("velocity_complexity", "Velocity / Complexity", 80),
    ]
    context = [
        _context("functional_qa", "Functional QA"),
        _context("platform_parity", "Platform Parity"),
        _context("architecture_context", "Architecture Context"),
        _context("stakeholder_alignment", "Stakeholder Alignment"),
        _context("business_roadmap", "Business-Aligned Roadmap"),
    ]
    rows = []
    weights = {
        "code_audit": 20,
        "dependency_health": 15,
        "secrets_review": 10,
        "static_analysis": 15,
        "ci_cd": 15,
        "architecture_debt": 15,
        "velocity_complexity": 10,
    }
    for section in technical:
        weight = weights[section["id"]]
        rows.append({
            "section_id": section["id"],
            "label": section["label"],
            "score": section["score"],
            "weight": weight,
            "weighted_contribution": round(section["score"] * weight / 100, 2),
            "truth_status": section["truth_status"],
        })
    return {
        "report_id": "mid_report_v4_test",
        "run_id": "midrun_v4_test",
        "repository": "BoneManTGRM/NICO",
        "client_name": "Test Client",
        "snapshot_commit_sha": "a" * 40,
        "source_identity_sha256": "b" * 64,
        "review_packet": {"review_packet_sha256": "c" * 64},
        "report_version": "mid-assessment-draft-v3-decision-ready",
        "detail_level": 3,
        "sections": technical + context,
        "evidence_coverage": {
            "percent": 100,
            "numerator": 24,
            "denominator": 24,
            "method": "Explicit evidence-unit coverage for the same run.",
        },
        "decision_summary": {
            "technical_maturity": "Mid",
            "technical_score": 71,
            "verified_strengths": [
                "Architecture & Technical Debt: 85/100.",
                "CI/CD Analysis: 83/100.",
                "Secrets Exposure Review: 80/100.",
            ],
            "primary_score_constraints": [
                {"label": "Static Analysis", "score": 49, "primary_reason": "Exact-snapshot analyzer corroboration remains incomplete."},
                {"label": "Code Audit", "score": 60, "primary_reason": "Sampled risk-pattern hits require disposition."},
                {"label": "Dependency / Library Ecosystem", "score": 72, "primary_reason": "Cross-scanner corroboration remains incomplete."},
            ],
            "recommended_actions": [
                "Resolve exact-snapshot analyzer coverage.",
                "Disposition sampled code-risk findings.",
                "Retain verification evidence and rescan.",
            ],
        },
        "score_integrity": {
            "calculated_score": 71,
            "reported_score": 71,
            "final_report_score": 71,
            "score_match": True,
            "weighted_rows": rows,
        },
        "repair_intelligence": {
            "candidates": [
                {
                    "rank": 1,
                    "title": "Resolve sampled code-risk pattern hits",
                    "severity": "medium",
                    "priority_score": 53.0,
                    "effort": "medium",
                    "recommended_action": "Collect the affected paths and apply the smallest reversible repair.",
                    "test_plan": ["Run the smallest relevant test.", "Run the full suite.", "Run a NICO rescan."],
                },
                {
                    "rank": 2,
                    "title": "Review non-success workflow runs",
                    "severity": "low",
                    "priority_score": 42.0,
                    "effort": "medium",
                    "recommended_action": "Classify failed, cancelled, and flaky runs by cause.",
                    "test_plan": ["Re-run affected jobs.", "Confirm stable workflow conclusions."],
                },
            ]
        },
        "review_exception_original_count": 3,
        "review_exception_final_count": 2,
        "deduplicated_review_exceptions": [
            {
                "severity": "medium",
                "title": "Limited conclusion in Static Analysis",
                "category": "low_confidence_or_limited_conclusion",
                "section_id": "static_analysis",
                "reason": "The section requires reviewer judgment.",
                "blockers": ["Exact-snapshot analyzer corroboration remains incomplete."],
            },
            {
                "severity": "medium",
                "title": "Unavailable Functional QA evidence",
                "category": "missing_evidence_affecting_delivery",
                "section_id": "functional_qa",
                "reason": "Direct functional evidence was not attached.",
                "blockers": ["A runnable build or equivalent evidence is required."],
            },
        ],
    }


def test_mid_v4_builds_full_depth_report_without_blank_pages() -> None:
    payload = _enhance(_payload())
    pdf = _pdf(payload)
    reader = PdfReader(io.BytesIO(pdf))

    assert payload["report_version"] == "mid-assessment-draft-v3-decision-ready"
    assert payload["detail_level"] == 3
    assert payload["presentation_version"] == MID_REPORT_V4_VERSION
    assert payload["presentation_detail_level"] == 4
    assert payload["report_depth_contract"]["legacy_payload_contract_preserved"] is True
    assert payload["report_depth_contract"]["dedicated_technical_dossiers"] == 7
    assert len(reader.pages) >= 13
    extracted = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    assert all(len(text) >= 80 for text in extracted)
    joined = "\n".join(extracted)
    for heading in (
        "Assessment Scope and Methodology",
        "Score Intelligence and Sensitivity",
        "Technical Review Dossier 1 of 7",
        "Technical Review Dossier 7 of 7",
        "Prioritized Repair Intelligence and Roadmap",
        "Human-Context Modules and Evidence Requests",
        "Review by Exception and Integrity",
    ):
        assert heading in joined


def test_mid_v4_markdown_retains_domain_evidence_and_review_boundaries() -> None:
    payload = _enhance(_payload())
    markdown = _markdown(payload)

    assert "# NICO MID ASSESSMENT" in markdown
    assert "FINAL REPORT - PENDING HUMAN APPROVAL" in markdown
    assert "## Decision summary" in markdown
    assert "The score is the weighted result of seven technical sections" in markdown
    assert "Human-context sections unscored: 5" in markdown
    assert "## Automated evidence coverage" in markdown
    assert "Technical dossier 1: Code Audit" in markdown
    assert "Technical dossier 7: Velocity / Complexity" in markdown
    assert "Evidence reviewed" in markdown
    assert "Reviewer questions" in markdown
    assert "Prioritized repair intelligence" in markdown
    assert "Human-context evidence requests" in markdown
    assert "NICO did not modify the assessed repository" in markdown
    assert "Unsupported claims permitted: 0" in markdown
    assert "Score changes require verified remediation and a new immutable snapshot" in markdown
