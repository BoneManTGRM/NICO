from __future__ import annotations

from nico.comprehensive_report_content_render_v66 import (
    install_comprehensive_report_content_render_v66,
)


def test_compact_scanner_counts_do_not_render_as_zero_findings() -> None:
    from nico import v2_premium_report_renderer as renderer

    status = install_comprehensive_report_content_render_v66()
    assert status["scanner_count_truth_bound"] is True

    canonical = {
        "scanner_execution_records": [
            {
                "scanner_name": "osv-scanner",
                "state": "completed_with_findings",
                "completed": True,
                "exact_commit_match": True,
                "artifact_hash": "abc",
                "finding_count": 59,
                "findings": [],
            }
        ],
        "review_candidate_summary": {
            "raw_total": 59,
            "verified_material_total": 0,
            "review_required_total": 59,
            "by_tool": {"osv-scanner": {"raw": 59, "review_required": 59}},
            "by_category": {
                "dependency": {"raw": 59, "material": 0, "review_required": 59}
            },
        },
    }

    stages = renderer._scanner_stages(canonical)
    scanner = stages[0]
    assert any("retained finding count=59" in line for line in scanner["evidence"])
    assert not any("findings=0" in line for line in scanner["evidence"])
    candidate = next(
        item for item in stages if item["stage_id"] == "review_required_candidate_register"
    )
    assert any("Confirmed material findings: 0" in line for line in candidate["evidence"])
    assert any("Review-required candidates: 59" in line for line in candidate["evidence"])
    assert candidate["status"] == "review_required"


def test_rich_finding_cards_restore_verification_rollback_and_exit_criteria() -> None:
    from nico import v2_premium_report_renderer as renderer

    install_comprehensive_report_content_render_v66()
    markdown = renderer._detailed_findings_markdown(
        [
            {
                "finding_id": "NICO-FINDING-1",
                "priority": "P1",
                "title": "Reduce complexity in build_report",
                "category": "architecture",
                "status": "review_required",
                "exact_source": "nico/report.py:50-180",
                "rule_id": "complexity_hotspot",
                "exact_commit_match": True,
                "evidence": "cyclomatic_complexity=74",
                "business_impact": "Regression risk.",
                "recommendation": "Decompose the function.",
                "verification": ["Exact-SHA rerun reports complexity at or below 30."],
                "acceptance_criteria": ["Required checks pass."],
                "rollback": "Revert if verification fails.",
                "exit_criteria": ["No material regression is introduced."],
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
            }
        ],
        spanish=False,
    )

    assert "Exact source: nico/report.py:50-180" in markdown
    assert "Verification:" in markdown
    assert "Rollback: Revert if verification fails." in markdown
    assert "Final exit criteria:" in markdown


def test_ci_operational_context_is_separate_and_unscored() -> None:
    from nico import v2_premium_report_renderer as renderer

    install_comprehensive_report_content_render_v66()
    canonical = {
        "stage_summaries": [],
        "canonical_findings": [],
        "scanner_execution_records": [],
        "ci_operational_context": {
            "successful_runs": 83,
            "non_success_runs": 12,
            "jobs_observed": 38,
            "technical_score_effect": "none",
        },
    }

    stages = renderer._canonical_stages(canonical)
    operational = next(
        item for item in stages if item["stage_id"] == "ci_cd_operational_readiness"
    )
    assert any("Successful workflow runs: 83" in line for line in operational["evidence"])
    assert any("Non-success workflow runs: 12" in line for line in operational["evidence"])
    assert any("no technical-score effect" in line for line in operational["evidence"])
