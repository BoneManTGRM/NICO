from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workspace_delegates_copy_model_types_and_run_control() -> None:
    workspace = read("apps/web/app/assessment/AssessmentWorkspace.tsx")

    assert 'from "./assessmentCopy"' in workspace
    assert 'from "./assessmentModel"' in workspace
    assert 'from "./assessmentTypes"' in workspace
    assert 'from "./useAssessmentRun"' in workspace
    assert "async function continueRun" not in workspace
    assert "async function run()" not in workspace
    assert "const EN:" not in workspace
    assert "const ES:" not in workspace
    assert workspace.count("useState") <= 3


def test_public_workspace_is_one_comprehensive_assessment() -> None:
    workspace = read("apps/web/app/assessment/AssessmentWorkspace.tsx")
    hook = read("apps/web/app/assessment/useAssessmentRun.ts")

    assert 'data-assessment-service-count="1"' in workspace
    assert 'data-canonical-assessment="strategic"' in workspace
    assert 'data-customer-facing-assessment="comprehensive"' in workspace
    assert "aria-pressed" not in workspace
    assert 'const service: Service = "comprehensive"' in hook
    assert 'requestWithRetry(' in hook
    assert '"/assessment/comprehensive-intake"' in hook
    assert 'assessment_depth: "strategic"' in hook
    assert 'report_language: locale' in hook


def test_score_assurance_and_risk_remain_separate() -> None:
    workspace = read("apps/web/app/assessment/AssessmentWorkspace.tsx")
    model = read("apps/web/app/assessment/assessmentModel.ts")

    assert "sectionPresentation(section, copy)" in workspace
    assert "view.technicalTone" in workspace
    assert "view.assuranceTone" in workspace
    assert "view.riskTone" in workspace
    assert "assurance_label" in model
    assert "risk_disposition" in model
    assert "scoreTone" in model


def test_polling_and_human_review_boundary_live_in_hook() -> None:
    hook = read("apps/web/app/assessment/useAssessmentRun.ts")

    assert "MAX_POLL_ATTEMPTS" in hook
    assert "POLL_INTERVAL_MS" in hook
    assert "continueRun" in hook
    assert 'setPhase("failed")' in hook
    assert "copy.comprehensiveReview" in hook
    assert "authorization_confirmed: true" in hook
    assert "authorized defensive repository assessment" in hook
