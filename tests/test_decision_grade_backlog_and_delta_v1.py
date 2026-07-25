from __future__ import annotations

import csv
import io

from nico.decision_grade_backlog_v1 import generate_backlog_exports
from nico.decision_grade_contract_v1 import DecisionGradeContract, build_decision_grade_contract
from nico.decision_grade_delta_v1 import compare_contracts, delta_markdown


PREVIOUS_SHA = "a" * 40
CURRENT_SHA = "b" * 40


def _identity(run_id: str, commit_sha: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": commit_sha,
        "assessment_type": "comprehensive",
        "branch": "main",
        "nico_version": "0.1.1",
        "scanner_configuration_version": "test-v1",
    }


def _record(
    key: str,
    *,
    priority: str = "P1",
    category: str = "architecture",
    location: str | None = None,
    complexity: int = 45,
    status: str = "open",
) -> dict[str, object]:
    return {
        "id": f"legacy-{key}",
        "priority": priority,
        "category": category,
        "title": f"{category} risk {key}",
        "impact": f"{category} risk {key} can delay delivery and increase rework.",
        "confidence": "high",
        "current_status": status,
        "evidence": f"cyclomatic_complexity={complexity}; source={key}",
        "location": location or f"src/{key}.py:20",
        "recommendation": "Implement the bounded remediation and verify it on the exact commit.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": f"{key} cyclomatic complexity <= 30 and the validation workflow passes.",
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close priority evidence and architecture risks.",
            "work_packages": [
                {
                    "title": "Decompose architecture hotspots",
                    "objective": "Reduce concentrated complexity in priority hotspots.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "2-4 weeks",
                    "dependencies": ["Characterization tests"],
                    "acceptance_criteria": ["Target cyclomatic complexity <= 30", "Validation workflow passes"],
                    "expected_impact": "Reduces regression and review cost.",
                },
                {
                    "title": "Restore scanner evidence reliability",
                    "objective": "Restore required scanner evidence and retain safe locations.",
                    "owner_role": "Product Quality Engineer",
                    "effort": "1-3 weeks",
                    "dependencies": ["Worker capacity"],
                    "acceptance_criteria": ["Required scanners complete twice on the exact SHA"],
                    "expected_impact": "Improves evidence assurance.",
                },
            ],
        },
        {
            "window": "31-90 days",
            "objective": "Complete strategic follow-on work.",
            "work_packages": [
                {
                    "title": "Strategic architecture modernization",
                    "objective": "Address remaining cross-cutting debt.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "4-8 weeks",
                    "dependencies": ["Priority work complete"],
                    "acceptance_criteria": ["Architecture acceptance controls pass"],
                    "expected_impact": "Improves long-term maintainability.",
                }
            ],
        },
    ]


def _assessment(records: list[dict[str, object]], technical: int = 82, adjusted: int = 78) -> dict[str, object]:
    return {
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "findings_register": records,
        "sections": [],
        "scoring_weights": [],
    }


def _contract(
    run_id: str,
    commit_sha: str,
    records: list[dict[str, object]],
    *,
    scanner_results: list[dict[str, object]] | None = None,
) -> DecisionGradeContract:
    stages = []
    if scanner_results is not None:
        stages = [{"stage": "scanner_execution", "scanner_results": scanner_results}]
    return build_decision_grade_contract(
        identity=_identity(run_id, commit_sha),
        assessment=_assessment(records),
        stage_summaries=stages,
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )


def test_backlog_aggregates_findings_by_first_30_day_work_package() -> None:
    contract = _contract(
        "run-current",
        CURRENT_SHA,
        [_record("one"), _record("two"), _record("evidence", category="evidence")],
    )
    exports = generate_backlog_exports(contract, report_id="report-current")

    assert exports["external_issue_creation_allowed"] is False
    assert exports["item_count"] == 2
    architecture = next(item for item in exports["json"]["items"] if "Decompose" in item["title"])
    assert len(architecture["source_finding_ids"]) == 2
    assert architecture["assessed_commit_sha"] == CURRENT_SHA
    assert architecture["acceptance_criteria"]
    assert architecture["dedupe_signature"]


def test_backlog_exports_are_github_jira_linear_and_markdown_ready() -> None:
    contract = _contract("run-current", CURRENT_SHA, [_record("one")])
    exports = generate_backlog_exports(contract, report_id="report-current")

    assert exports["github_issues"][0]["title"].startswith("[P1]")
    assert "## Acceptance criteria" in exports["github_issues"][0]["body"]
    jira_rows = list(csv.DictReader(io.StringIO(exports["jira_csv"])))
    linear_rows = list(csv.DictReader(io.StringIO(exports["linear_csv"])))
    assert jira_rows[0]["External ID"]
    assert jira_rows[0]["Priority"] == "High"
    assert linear_rows[0]["External ID"]
    assert linear_rows[0]["Priority"] == "2"
    assert "# NICO Decision-Grade Backlog" in exports["markdown"]
    assert all(exports["hashes"].values())


def test_delta_reports_closed_new_reduced_and_score_changes() -> None:
    previous = _contract(
        "run-previous",
        PREVIOUS_SHA,
        [
            _record("closed"),
            _record("persistent", priority="P1", complexity=50),
            _record("reduced", priority="P1", category="dependency"),
        ],
    )
    current = _contract(
        "run-current",
        CURRENT_SHA,
        [
            _record("persistent", priority="P1", complexity=40),
            _record("reduced", priority="P2", category="dependency"),
            _record("new"),
        ],
    )
    delta = compare_contracts(
        previous,
        current,
        previous_assessment=_assessment([], technical=70, adjusted=60),
        current_assessment=_assessment([], technical=82, adjusted=78),
    )

    assert delta["status"] == "complete"
    assert delta["summary"]["closed_risks"] == 1
    assert delta["summary"]["new_risks"] == 1
    assert delta["summary"]["reduced_risks"] == 1
    assert delta["score_deltas"]["technical_score"]["delta"] == 12
    assert delta["score_deltas"]["evidence_adjusted_score"]["delta"] == 18
    assert delta["summary"]["complexity_improvements"] == 1
    assert "Risks closed: 1" in delta_markdown(delta)


def test_delta_does_not_claim_closure_when_current_evidence_failed() -> None:
    previous = _contract(
        "run-previous",
        PREVIOUS_SHA,
        [_record("scanner-bound-risk", category="static")],
        scanner_results=[{"tool": "semgrep", "status": "complete", "required": True, "category": "static"}],
    )
    current = _contract(
        "run-current",
        CURRENT_SHA,
        [],
        scanner_results=[
            {
                "tool": "semgrep",
                "status": "failed",
                "required": True,
                "category": "static",
                "reason": "worker failure",
            }
        ],
    )
    delta = compare_contracts(previous, current)

    assert delta["summary"]["closed_risks"] == 0
    assert delta["summary"]["closure_withheld_for_evidence_gap"] == 1
    withheld = delta["finding_changes"]["not_observed_due_to_evidence_gap"][0]
    assert withheld["change"] == "not_observed_due_to_evidence_gap"
    assert "semgrep" in withheld["missing_or_failed_evidence"]
    assert delta["summary"]["scanner_regressions"] == 1


def test_delta_detects_reopened_finding_without_relying_on_wording() -> None:
    previous = _contract("run-previous", PREVIOUS_SHA, [_record("same", status="closed")])
    current = _contract("run-current", CURRENT_SHA, [_record("same", status="open")])
    current.findings[0].title = "Renamed presentation of the same control risk"

    delta = compare_contracts(previous, current)

    assert delta["summary"]["reopened_risks"] == 1
    reopened = delta["finding_changes"]["reopened"][0]
    assert reopened["title_changed"] is True


def test_delta_refuses_incompatible_repository_comparison() -> None:
    previous = _contract("run-previous", PREVIOUS_SHA, [_record("same")])
    current = _contract("run-current", CURRENT_SHA, [_record("same")])
    current.identity.repository_identifier = "another/repository"

    delta = compare_contracts(previous, current)

    assert delta["status"] == "incompatible"
    assert delta["comparable"] is False
    assert "repository_mismatch" in delta["incompatibilities"]
    assert delta["synthetic_delta_generated"] is False
