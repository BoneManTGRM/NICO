from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


FINAL_EXECUTION = Path("nico/comprehensive_final_report_execution_v1.py")
FINAL_REVIEW = Path("apps/web/app/AssessmentFinalReviewAction.tsx")
LAYOUT = Path("apps/web/app/layout.tsx")


def _load_final_execution():
    spec = importlib.util.spec_from_file_location(
        "test_comprehensive_final_report_execution_v4",
        FINAL_EXECUTION,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _context() -> dict[str, Any]:
    return {
        "run_id": "comprun_truth_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_truth_test",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "prior_stage_results": {
            "evidence_reconciliation_and_scoring": {
                "status": "complete",
                "assessment": {
                    "technical_score": 85,
                    "evidence_adjusted_score": 74,
                    "canonical_evidence_adjusted_score": 74,
                    "maturity_signal": {
                        "score": 85,
                        "technical_score": 85,
                        "source_score": 85,
                        "presented_score": 72,
                        "evidence_adjusted_score": 74,
                        "canonical_evidence_adjusted_score": 74,
                    },
                },
                "evidence": {
                    "technical_score": 85,
                    "evidence_adjusted_score": 72,
                },
            }
        },
    }


def test_production_registry_binds_current_report_and_cross_format_providers() -> None:
    source = FINAL_EXECUTION.read_text(encoding="utf-8")

    assert 'VERSION = "nico.comprehensive_final_report_execution.v4"' in source
    assert "finality_aware_cross_format_verification_provider" in source
    assert "finalize_comprehensive_report_result" in source
    assert 'raw["final_report_generation"] = wrapped' in source
    assert 'raw["cross_format_verification"] = finality_aware_cross_format_verification_provider' in source
    assert '"cross_format_provider_bound": verifier_bound' in source
    assert '"canonical_score_parity_required": True' in source
    assert '"canonical_score_synchronized_before_render": True' in source
    assert '"local_finality_applied_after_render": True' in source
    assert '"pdf_finality_semantics_required": True' in source
    assert '"failed_checks_exposed": True' in source
    assert '"global_report_builder_mutated": False' in source
    assert "install_comprehensive_report_finality_v51" not in source
    assert "install_comprehensive_cross_format_finality_v49" not in source


def test_final_report_context_synchronizes_scores_without_mutating_prior_stages() -> None:
    module = _load_final_execution()
    original = _context()

    updated, truth = module._canonical_final_report_context(original)

    assessment = updated["prior_stage_results"]["evidence_reconciliation_and_scoring"]["assessment"]
    maturity = assessment["maturity_signal"]
    evidence = updated["prior_stage_results"]["evidence_reconciliation_and_scoring"]["evidence"]
    assert truth["status"] == "complete"
    assert truth["technical_score"] == 85
    assert truth["canonical_evidence_adjusted_score"] == 74
    assert assessment["technical_score"] == 85
    assert assessment["evidence_adjusted_score"] == 74
    assert assessment["canonical_evidence_adjusted_score"] == 74
    assert maturity["score"] == 85
    assert maturity["source_score"] == 85
    assert maturity["technical_score"] == 85
    assert maturity["presented_score"] == 85
    assert maturity["evidence_adjusted_score"] == 74
    assert maturity["canonical_evidence_adjusted_score"] == 74
    assert evidence["technical_score"] == 85
    assert evidence["evidence_adjusted_score"] == 74
    assert evidence["canonical_evidence_adjusted_score"] == 74
    assert evidence["final_report_input_scores_synchronized"] is True
    assert original["prior_stage_results"]["evidence_reconciliation_and_scoring"]["assessment"]["maturity_signal"]["presented_score"] == 72
    assert original["prior_stage_results"]["evidence_reconciliation_and_scoring"]["evidence"]["evidence_adjusted_score"] == 72


def test_final_report_provider_receives_synchronized_scores_before_render() -> None:
    module = _load_final_execution()
    observed: dict[str, Any] = {}

    def provider(context: dict[str, Any]) -> dict[str, Any]:
        observed.update(context)
        assessment = context["prior_stage_results"]["evidence_reconciliation_and_scoring"]["assessment"]
        maturity = assessment["maturity_signal"]
        assert maturity["presented_score"] == 85
        assert assessment["canonical_evidence_adjusted_score"] == 74
        return {
            "status": "complete",
            "report_package": {
                "report_id": "report_truth_test",
                "markdown": "report",
                "html": "<!doctype html><html></html>",
                "json": {"assessment": assessment},
                "pdf_base64": "JVBERi0xLjQK",
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        }

    result = module.wrap_final_report_provider(provider)(_context())

    assert observed["final_report_input_score_truth"]["status"] == "complete"
    assert result["final_report_input_score_truth"]["technical_score"] == 85
    assert result["final_report_input_score_truth"]["canonical_evidence_adjusted_score"] == 74
    assert result["local_finality"]["status"] == "skipped"


def test_comprehensive_review_action_fails_closed_until_cross_format_passes() -> None:
    source = FINAL_REVIEW.read_text(encoding="utf-8")

    assert "export function finalReviewReadiness" in source
    assert "stageResults(value).cross_format_truth_verification" in source
    assert "SUCCESS_STATUSES.has(status) && failedChecks.length === 0" in source
    assert 'runStatus === "review_required" || runStatus === "approved"' in source
    assert 'context.service === "comprehensive" && !context.review_ready' in source
    assert "existing?.remove()" in source
    assert 'actions.dataset.nicoReviewGate = "blocked"' in source
    assert "cross_format_failed_checks" in source


def test_fail_closed_review_action_is_installed_in_root_layout() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentFinalReviewAction from "./AssessmentFinalReviewAction";' in source
    assert "<AssessmentFinalReviewAction />" in source
    assert source.index("<UnifiedAssessmentPublicGuard />") < source.index("<AssessmentFinalReviewAction />")
