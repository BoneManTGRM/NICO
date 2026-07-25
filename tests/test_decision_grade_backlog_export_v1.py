from __future__ import annotations

from nico.decision_grade_backlog_export_v1 import (
    build_backlog_exports,
    validate_backlog_exports,
    wrap_report_builder_with_backlog_exports,
)

SHA = "a" * 40


def _criterion(name: str) -> dict:
    return {
        "criterion_id": f"AC-{name}",
        "description": f"{name} passes on the validation commit.",
        "workflow_name": "NICO CI",
    }


def _finding(fid: str, priority: str, work_package: str) -> dict:
    return {
        "finding_id": fid,
        "title": f"Risk {fid}",
        "priority": priority,
        "scope": "repository",
        "evidence_ids": [f"EVD-{fid}"],
        "evidence_locations": [f"src/{fid}.py:10"],
        "factual_statement": f"Observed {fid}.",
        "technical_interpretation": "The control is not reliable.",
        "business_impact": "Release delay and engineering rework are possible.",
        "recommended_action": "Repair the control and add regression coverage.",
        "owner_role": "Platform Engineer",
        "effort": "M",
        "acceptance_criteria": [_criterion(fid)],
        "residual_risk": {"does_not_eliminate": "Provider outages remain possible."},
        "roadmap_mappings": [work_package],
        "backlog_issue_mapping": f"backlog/{fid}",
    }


def _contract() -> dict:
    return {
        "identity": {"assessment_id": "comprun-1", "assessed_commit_sha": SHA},
        "findings": [
            _finding("RISK-P1-001", "P1", "WP-001"),
            _finding("RISK-P1-002", "P1", "WP-001"),
            _finding("RISK-P2-003", "P2", "WP-002"),
            _finding("RISK-P3-004", "P3", "WP-003"),
        ],
        "roadmap_work_packages": [
            {
                "work_package_id": "WP-001",
                "title": "Stabilize release verification",
                "time_window": "0-30 days",
                "ordered_implementation_steps": ["Classify failures.", "Repair recurrent causes."],
                "dependencies": ["CI access"],
                "owner_role": "Platform Engineer",
                "effort_range": "M",
                "classification": "Quick Win",
                "acceptance_criteria": [_criterion("WP-001")],
                "residual_risk": {"does_not_eliminate": "External provider failures remain possible."},
            },
            {
                "work_package_id": "WP-002",
                "title": "Reduce maintenance exposure",
                "time_window": "31-90 days",
                "ordered_implementation_steps": ["Implement the strategic remediation."],
                "dependencies": [],
                "owner_role": "Product Engineer",
                "effort_range": "L",
                "classification": "Strategic",
                "acceptance_criteria": [_criterion("WP-002")],
                "residual_risk": {"does_not_eliminate": "Future regressions remain possible."},
            },
        ],
    }


def test_multiple_findings_mapping_to_one_work_package_are_deduplicated() -> None:
    exports = build_backlog_exports(_contract())
    assert exports["candidate_finding_count"] == 3
    assert exports["item_count"] == 2
    assert exports["deduplicated"] is True
    first = exports["items"][0]
    assert first["backlog_item_id"] == "WP-001"
    assert first["related_finding_ids"] == ["RISK-P1-001", "RISK-P1-002"]


def test_all_required_formats_and_hashes_are_generated() -> None:
    exports = build_backlog_exports(_contract())
    assert set(exports["formats"]) == {"markdown", "json", "github", "jira_csv", "linear_csv"}
    assert len(exports["hashes"]) == 5
    assert validate_backlog_exports(exports) == []


def test_items_are_commit_bound_and_never_auto_created() -> None:
    exports = build_backlog_exports(_contract())
    assert exports["automatic_external_creation_allowed"] is False
    assert all(item["assessed_commit_sha"] == SHA for item in exports["items"])
    assert all(item["automatic_external_creation_allowed"] is False for item in exports["items"])
    assert all(item["requires_human_review"] is True for item in exports["items"])


def test_output_is_deterministic() -> None:
    first = build_backlog_exports(_contract())
    second = build_backlog_exports(_contract())
    assert first["hashes"] == second["hashes"]
    assert first["items"] == second["items"]


def test_wrapper_attaches_exports_and_quality_flags() -> None:
    def delegate() -> dict:
        return {"status": "complete", "decision_grade_contract": _contract(), "report_package": {}, "report_quality_contract": {}}

    result = wrap_report_builder_with_backlog_exports(delegate)()
    assert result["status"] == "complete"
    assert result["backlog_exports"]["item_count"] == 2
    assert result["report_package"]["backlog_exports"]["item_count"] == 2
    assert result["report_quality_contract"]["backlog_export_present"] is True
    assert result["report_quality_contract"]["backlog_external_issue_creation_allowed"] is False


def test_wrapper_fails_closed_when_contract_is_missing() -> None:
    result = wrap_report_builder_with_backlog_exports(lambda: {"status": "complete", "report_package": {}})()
    assert result["status"] == "blocked"
    assert result["reason"] == "decision_grade_backlog_export_failed"
    assert result["report_quality_contract"]["backlog_export_present"] is False
