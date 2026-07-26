from __future__ import annotations

from pathlib import Path


FINAL_EXECUTION = Path("nico/comprehensive_final_report_execution_v1.py")
FINAL_REVIEW = Path("apps/web/app/AssessmentFinalReviewAction.tsx")
LAYOUT = Path("apps/web/app/layout.tsx")


def test_production_registry_binds_current_report_and_cross_format_providers() -> None:
    source = FINAL_EXECUTION.read_text(encoding="utf-8")

    assert 'VERSION = "nico.comprehensive_final_report_execution.v2"' in source
    assert "finality_aware_cross_format_verification_provider" in source
    assert 'raw["final_report_generation"] = wrapped' in source
    assert 'raw["cross_format_verification"] = finality_aware_cross_format_verification_provider' in source
    assert '"cross_format_provider_bound": verifier_bound' in source
    assert '"canonical_score_parity_required": True' in source
    assert '"failed_checks_exposed": True' in source
    assert '"global_report_builder_mutated": False' in source
    assert "install_comprehensive_report_finality_v51" not in source
    assert "install_comprehensive_cross_format_finality_v49" not in source


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
