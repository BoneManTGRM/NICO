from __future__ import annotations

from nico.comprehensive_report_truth_stabilization_v52 import (
    prepare_report_stage_results,
    stabilize_report_package,
)


def _findings() -> tuple[dict, dict]:
    summary = {
        "finding_id": "SUMMARY",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
        "observed_evidence": "complexity=74",
    }
    detail = {
        "finding_id": "DETAIL",
        "title": "Reduce complexity in _spanish_pdf",
        "exact_source": "nico/spanish.py:50-223:50",
        "function": "_spanish_pdf",
        "rule_id": "complexity_hotspot",
        "observed_evidence": "complexity=74; loc=174; grade=F",
        "recommendation": "Split preparation, translation, layout, and validation.",
    }
    return summary, detail


def _sample() -> dict:
    finding_summary, finding_detail = _findings()
    canonical = {
        "technical_score": 92,
        "canonical_technical_score": 92,
        "evidence_adjusted_score": 86,
        "canonical_evidence_adjusted_score": 86,
        "incomplete_analyzers": ["bandit"],
        "analyzer_execution_coverage": 89,
        "report_contract_status": "blocked",
        "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
        "findings": [finding_summary, finding_detail],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "exact_commit_match": True,
                "findings": 0,
            }
        ],
    }
    return {
        "report_package": {
            "json": canonical,
            "markdown": "The canonical register contains 88 unique decision-grade findings. span ish_pdf",
            "html": "<html>The canonical register contains 88 unique decision-grade findings. co llect_snapshot_repository_evidence</html>",
            "report_quality_contract": {
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_evidence_adjusted_score_mismatch",
            },
        }
    }


def _section(
    section_id: str,
    score: int,
    evidence: list[str],
    *,
    unavailable: list[str] | None = None,
) -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "source_score": score,
        "presented_score": score,
        "score_value": score,
        "evidence": evidence,
        "findings": [],
        "unavailable": unavailable or [],
    }


def _stage_results() -> dict:
    summary, detail = _findings()
    assessment = {
        "repository": "BoneManTGRM/NICO",
        "technical_score": 92,
        "evidence_adjusted_score": 86,
        "canonical_evidence_adjusted_score": 86,
        "maturity_signal": {
            "score": 92,
            "technical_score": 92,
            "evidence_adjusted_score": 86,
            "canonical_evidence_adjusted_score": 86,
        },
        "sections": [
            _section("code_audit", 96, ["Exact snapshot source evidence retained."]),
            _section(
                "dependency_health",
                96,
                ["Authoritative manifest and lockfile evidence retained."],
                unavailable=["59 review-required dependency candidates remain untriaged."],
            ),
            _section(
                "secrets_review",
                96,
                ["Gitleaks and TruffleHog full-history evidence retained."],
                unavailable=["17 review-required secret candidates remain untriaged."],
            ),
            _section(
                "static_analysis",
                83,
                ["Semgrep completed.", "TypeScript completed."],
                unavailable=["Bandit evidence unavailable."],
            ),
            _section("ci_cd", 100, ["Workflow configuration retained."]),
            _section("architecture_debt", 78, ["Complexity hotspot evidence retained."]),
            _section("velocity_complexity", 87, ["Commit and pull request evidence retained."]),
        ],
        "findings_register": [summary, detail],
        "decision_grade_findings_register": [summary, detail],
    }
    duplicate_text = [
        "P1 · Reduce complexity in _spanish_pdf · NICO-FINDING-SUMMARY · nico/spanish.py:50",
        "P1 · Reduce complexity in _spanish_pdf · NICO-FINDING-DETAIL · nico/spanish.py:50-223:50",
    ]
    return {
        "dependency_security_static_analysis": {
            "status": "complete",
            "scanner_results": [
                {
                    "scanner_name": "bandit",
                    "status": "completed",
                    "exact_commit_match": True,
                    "artifact_hash": "abc123",
                    "findings": 0,
                }
            ],
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "assessment": assessment,
            "evidence": {
                "technical_score": 92,
                "evidence_adjusted_score": 86,
                "canonical_evidence_adjusted_score": 86,
                "incomplete_analyzers": ["bandit"],
                "analyzer_execution_coverage": 89,
            },
        },
        "risk_reduction_and_executive_briefing": {
            "status": "complete",
            "findings": duplicate_text,
            "summary": "The canonical register contains 88 unique decision-grade findings.",
            "specific_correction": "Use co llect_snapshot_repository_evidence and _ span ish_pdf.",
        },
    }


def test_stabilization_reconciles_scanner_score_and_duplicates() -> None:
    result = stabilize_report_package(_sample())
    package = result["report_package"]
    canonical = package["json"]

    assert canonical["incomplete_analyzers"] == []
    assert canonical["analyzer_execution_coverage"] == 100
    assert canonical["report_contract_status"] == "ready_for_human_review"
    assert canonical["report_contract_reason"] == ""
    assert len(canonical["findings"]) == 1
    assert canonical["findings"][0]["finding_id"] == "DETAIL"
    assert canonical["finding_register_deduplicated"] is True
    assert canonical["scanner_state_reconciled"] is True


def test_stabilization_repairs_cross_format_identifiers_and_count() -> None:
    result = stabilize_report_package(_sample())
    package = result["report_package"]

    assert "span ish_pdf" not in package["markdown"]
    assert "_spanish_pdf" in package["markdown"]
    assert "co llect_snapshot_repository_evidence" not in package["html"]
    assert "collect_snapshot_repository_evidence" in package["html"]
    assert "contains 1 unique decision-grade findings" in package["markdown"]
    assert package["report_quality_contract"]["report_contract_status"] == "ready_for_human_review"


def test_stage_truth_is_reconciled_before_any_report_format_is_rendered() -> None:
    stages = prepare_report_stage_results(_stage_results())
    scoring = stages["evidence_reconciliation_and_scoring"]
    evidence = scoring["evidence"]
    assessment = scoring["assessment"]
    risk = stages["risk_reduction_and_executive_briefing"]

    assert evidence["incomplete_analyzers"] == []
    assert evidence["analyzer_execution_coverage"] == 100
    assert evidence["evidence_adjusted_score"] == assessment["canonical_evidence_adjusted_score"]
    assert evidence["canonical_evidence_adjusted_score"] == assessment["canonical_evidence_adjusted_score"]
    assert assessment["score_reconciliation"]["independently_recomputable"] is True
    assert len(assessment["findings_register"]) == 1
    assert len(assessment["decision_grade_findings_register"]) == 1
    assert len(risk["findings"]) == 1
    assert "contains 1 unique decision-grade findings" in risk["summary"]
    assert "collect_snapshot_repository_evidence" in risk["specific_correction"]
    assert "_spanish_pdf" in risk["specific_correction"]
