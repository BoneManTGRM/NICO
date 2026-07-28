from __future__ import annotations

from pathlib import Path

from nico.phase6_final_remediation_v1 import (
    canonicalize_findings,
    normalize_report_filename,
    reconcile_assessment,
)

ROOT = Path(__file__).resolve().parents[1]


def _sql_finding(*, finding_id: str, path: str, line: int) -> dict:
    return {
        "finding_id": finding_id,
        "priority": "P0",
        "category": "static",
        "title": "Avoiding SQL string concatenation: untrusted input concatenated with raw SQL query can result in SQL Injection.",
        "evidence": "tool=semgrep; rule=python.lang.security.audit.formatted-sql-query; severity=high; verified=True",
        "location": f"{path}:{line}",
        "roadmap_mappings": ["WP-01", "WP-01", "WP-03", "WP-03"],
        "acceptance_criteria": ["Rerun exact SHA.", "Rerun exact SHA."],
        "backlog_issue_mapping": "backlog/RISK",
    }


def test_repeated_phase5_section_is_removed_from_customer_assessment() -> None:
    assessment = {
        "commit_sha": "a" * 40,
        "phase5_verified_outcomes": {"current_commit_sha": "a" * 40, "truth_rule": "retained evidence only"},
        "sections": [
            {"id": "code_audit", "evidence": [], "findings": [], "unavailable": []},
            {"id": "phase5_verified_outcomes", "label": "Verified Change Since Phase 5 Baseline"},
        ],
        "findings_register": [],
    }

    result = reconcile_assessment(assessment, {})

    assert all(section.get("id") != "phase5_verified_outcomes" for section in result["sections"])
    assert "phase5_verified_outcomes" not in result
    assert result["verification_provenance"]["customer_report_section"] is False


def test_same_stable_finding_in_same_file_is_grouped_once() -> None:
    findings, dispositions = canonicalize_findings(
        [
            _sql_finding(finding_id="RISK-P0-ABC", path="nico/comprehensive_run_store.py", line=83),
            _sql_finding(finding_id="RISK-P0-ABC", path="nico/comprehensive_run_store.py", line=169),
        ]
    )

    assert findings == []
    assert len(dispositions) == 1
    assert dispositions[0]["executive_title"] == "Unsafe SQL query construction"
    assert dispositions[0]["status"] == "approved_nonblocking"
    assert dispositions[0]["roadmap_mappings"] == ["WP-01", "WP-03"]
    assert dispositions[0]["acceptance_criteria"] == ["Rerun exact SHA."]
    assert dispositions[0]["related_locations"] == [
        "nico/comprehensive_run_store.py:83",
        "nico/comprehensive_run_store.py:169",
    ]


def test_same_incoming_id_in_different_files_cannot_collide() -> None:
    first = {
        "finding_id": "RISK-P1-COLLIDE",
        "priority": "P1",
        "category": "code",
        "title": "First distinct issue",
        "location": "nico/one.py:10",
    }
    second = {
        "finding_id": "RISK-P1-COLLIDE",
        "priority": "P1",
        "category": "code",
        "title": "Second distinct issue",
        "location": "nico/two.py:20",
    }

    findings, dispositions = canonicalize_findings([first, second])

    assert dispositions == []
    assert len(findings) == 2
    assert len({item["finding_id"] for item in findings}) == 2
    assert {item["canonical_location"] for item in findings} == {"nico/one.py:10", "nico/two.py:20"}


def test_report_filename_status_is_idempotent() -> None:
    original = "nico-assessment-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    first = normalize_report_filename(original, complete=True, approved=False)
    second = normalize_report_filename(first, complete=True, approved=False)

    assert first == "nico-assessment-FINAL-PENDING-APPROVAL.pdf"
    assert second == first


def test_customer_front_matter_uses_neutral_assessment_coverage() -> None:
    source = (ROOT / "nico" / "comprehensive_express_quality_v7.py").read_text(encoding="utf-8")
    report_source = (ROOT / "nico" / "comprehensive_decision_grade_report_v5.py").read_text(encoding="utf-8")

    assert "Assessment Coverage" in source
    assert "Why this is broader than Express" not in source
    assert "Assessment Coverage" in report_source
    assert "Why this is broader than Express" not in report_source


def test_mid_review_uses_neutral_score_methodology() -> None:
    source = (ROOT / "apps" / "web" / "app" / "assessment" / "MidSectionReview.tsx").read_text(encoding="utf-8")

    assert "methodologyNote" in source
    assert "Express is a faster baseline" not in source


def test_terminal_bootstrap_installs_phase6_after_phase5() -> None:
    source = (ROOT / "nico" / "api" / "terminal_authority_bootstrap.py").read_text(encoding="utf-8")

    assert "install_phase6_final_remediation_v1" in source
    assert "PHASE6_FINAL_REMEDIATION = install_phase6_final_remediation_v1()" in source
    assert source.index("PHASE5_REPORT_TRUTH =") < source.index("PHASE6_FINAL_REMEDIATION =")
