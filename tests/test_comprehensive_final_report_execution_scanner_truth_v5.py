from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI

from nico.comprehensive_final_report_execution_v1 import (
    _canonical_final_report_context,
    install_comprehensive_final_report_execution,
    wrap_final_report_provider,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]


def _context(*, failed: list[str] | None = None) -> dict:
    failed = failed or []
    completed = [tool for tool in TOOLS if tool not in failed]
    return {
        "run_id": "comprun_final_scanner_truth",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_final_scanner_truth",
        "customer_id": "customer_final_scanner_truth",
        "project_id": "project_final_scanner_truth",
        "prior_stage_results": {
            "dependency_security_static_analysis": {
                "status": "complete",
                "scanner": {
                    "status": "complete",
                    "tools_requested": list(TOOLS),
                    "tools_run": completed,
                    "failed_tools": failed,
                    "unavailable_tools": [],
                    "timed_out_tools": [],
                },
                "evidence": {
                    "analyzer_execution_coverage": 78,
                    "incomplete_applicable_analyzers": 2,
                    "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
                    "flattened": [
                        "client_readiness_contract.incomplete_analyzers[0]: pip-audit",
                        *(
                            ["client_readiness_contract.incomplete_analyzers[1]: semgrep"]
                            if "semgrep" in failed
                            else []
                        ),
                    ],
                },
            },
            "evidence_reconciliation_and_scoring": {
                "status": "complete",
                "assessment": {
                    "technical_score": 93,
                    "evidence_adjusted_score": 90,
                    "canonical_evidence_adjusted_score": 90,
                    "maturity_signal": {
                        "level": "Exceptional",
                        "score": 93,
                        "technical_score": 93,
                        "source_score": 93,
                        "presented_score": 92,
                        "evidence_adjusted_score": 90,
                        "canonical_evidence_adjusted_score": 90,
                    },
                    "sections": [],
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "client_readiness_contract": {
                    "authoritative_source": "direct_exact_run_records_plus_live_scanner_manifest",
                    "coverage_numerator": len(completed),
                    "coverage_denominator": len(TOOLS),
                    "requested_exact_run_scanners": list(TOOLS),
                    "completed_exact_commit_scanners": completed,
                    "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
                },
                "evidence": {
                    "technical_score": 93,
                    "evidence_adjusted_score": 90,
                    "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
                },
            },
            "decision_report_generation": {
                "status": "complete",
                "evidence": {
                    "legacy_lines": [
                        "assessment.incomplete_analyzers[0]: pip-audit",
                        *(
                            ["assessment.incomplete_analyzers[1]: semgrep"]
                            if "semgrep" in failed
                            else []
                        ),
                    ]
                },
            },
        },
    }


def test_authoritative_production_context_removes_completed_tool_aliases_before_provider() -> None:
    source = _context()
    original = deepcopy(source)

    updated, truth = _canonical_final_report_context(source)

    dependency = updated["prior_stage_results"]["dependency_security_static_analysis"]
    scoring = updated["prior_stage_results"]["evidence_reconciliation_and_scoring"]
    manifest = updated["pre_render_scanner_truth"]

    assert manifest["status"] == "applied"
    assert manifest["requested"] == sorted(TOOLS)
    assert manifest["completed"] == sorted(TOOLS)
    assert manifest["incomplete"] == []
    assert manifest["coverage"] == 100
    assert dependency["evidence"]["incomplete_analyzers"] == []
    assert dependency["evidence"]["incomplete_applicable_analyzers"] == 0
    assert dependency["evidence"]["analyzer_execution_coverage"] == 100
    assert dependency["evidence"]["flattened"] == []
    assert updated["prior_stage_results"]["decision_report_generation"]["evidence"]["legacy_lines"] == []
    assert scoring["assessment"]["technical_score"] == 93
    assert scoring["assessment"]["canonical_evidence_adjusted_score"] == 90
    assert truth["scanner_truth_synchronized_before_render"] is True
    assert truth["pre_render_scanner_truth"]["incomplete"] == []
    assert source == original


def test_wrapped_production_provider_receives_sanitized_stage_results() -> None:
    observed: dict = {}

    def provider(context: dict) -> dict:
        observed.update(context)
        combined = repr(context["prior_stage_results"])
        assert "incomplete_analyzers[0]: pip-audit" not in combined
        assert context["prior_stage_results"]["dependency_security_static_analysis"]["evidence"]["incomplete_analyzers"] == []
        return {
            "status": "complete",
            "summary": "provider received canonical scanner truth",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    result = wrap_final_report_provider(provider)(_context())

    assert result["status"] == "complete"
    assert observed["pre_render_scanner_truth"]["coverage"] == 100
    assert result["pre_render_scanner_truth"]["incomplete"] == []
    assert result["final_report_input_score_truth"]["scanner_truth_synchronized_before_render"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_genuine_current_failure_remains_incomplete_at_production_boundary() -> None:
    updated, truth = _canonical_final_report_context(_context(failed=["semgrep"]))

    manifest = updated["pre_render_scanner_truth"]
    dependency = updated["prior_stage_results"]["dependency_security_static_analysis"]
    assert manifest["coverage"] == 89
    assert manifest["incomplete"] == ["semgrep"]
    assert dependency["evidence"]["incomplete_analyzers"] == ["semgrep"]
    assert dependency["evidence"]["flattened"] == [
        "client_readiness_contract.incomplete_analyzers[1]: semgrep"
    ]
    assert truth["pre_render_scanner_truth"]["incomplete"] == ["semgrep"]


def test_installer_advertises_authoritative_scanner_truth_boundary() -> None:
    app = FastAPI()
    app.state.__setattr__(
        PROVIDER_STATE_KEY,
        {
            "final_report_generation": lambda context: {
                "status": "complete",
                "context": context,
            }
        },
    )

    installed = install_comprehensive_final_report_execution(app)

    assert installed["bound"] is True
    assert installed["authoritative_scanner_truth_synchronized_before_render"] is True
    assert installed["canonical_score_synchronized_before_render"] is True
    assert installed["human_review_required"] is True
    assert installed["client_delivery_allowed"] is False
