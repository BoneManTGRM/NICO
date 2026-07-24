from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workspace_is_decomposed_by_responsibility() -> None:
    workspace = _read("apps/web/app/assessment/AssessmentWorkspace.tsx")

    assert 'from "./assessmentCopy"' in workspace
    assert 'from "./assessmentModel"' in workspace
    assert 'from "./assessmentTypes"' in workspace
    assert 'from "./useAssessmentRun"' in workspace
    assert "function continueRun" not in workspace
    assert "async function run()" not in workspace
    assert "const EN:" not in workspace
    assert "const ES:" not in workspace
    # One import occurrence plus the two bounded presentation-only states.
    assert workspace.count("useState") <= 3


def test_customer_sees_one_assessment_with_core_and_strategic_depths() -> None:
    copy = _read("apps/web/app/assessment/assessmentCopy.ts")
    workspace = _read("apps/web/app/assessment/AssessmentWorkspace.tsx")

    assert "One assessment. Two depths. One evidence ledger." in copy
    assert "Una evaluación. Dos niveles. Un solo registro de evidencia." in copy
    assert 'label: "Core"' in copy
    assert 'label: "Strategic"' in copy
    assert 'label: "Estratégica"' in copy
    assert 'data-assessment-service-count="1"' in workspace
    assert 'data-assessment-depth-count="2"' in workspace
    assert 'data-assessment-depth={value === "express" ? "core" : "strategic"}' in workspace


def test_legacy_routes_are_implementation_details_not_separate_scorecards() -> None:
    hook = _read("apps/web/app/assessment/useAssessmentRun.ts")

    assert 'assessment_depth: publicDepth(service)' in hook
    assert 'report_language: locale' in hook
    assert 'const path = service === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake";' in hook
    assert "implementation routes, not" in hook
    assert "independent customer-facing assessment products" in hook


def test_score_assurance_and_risk_are_presented_separately() -> None:
    workspace = _read("apps/web/app/assessment/AssessmentWorkspace.tsx")
    model = _read("apps/web/app/assessment/assessmentModel.ts")

    assert "sectionPresentation(section, copy)" in workspace
    assert "view.technicalClass" in workspace
    assert "view.assuranceClass" in workspace
    assert "view.riskClass" in workspace
    assert "assurance_label" in model
    assert "risk_disposition" in model
    assert "scoreClass" in model
    assert "`${displayState} · ${score}`" not in workspace


def test_hook_owns_polling_state_and_preserves_human_review_boundary() -> None:
    hook = _read("apps/web/app/assessment/useAssessmentRun.ts")

    assert "MAX_POLL_ATTEMPTS" in hook
    assert "POLL_INTERVAL_MS" in hook
    assert "continueRun" in hook
    assert 'setPhase("failed")' in hook
    assert "copy.comprehensiveReview" in hook
    assert "copy.expressComplete" in hook
    assert "authorization_confirmed: true" in hook
    assert "authorized defensive repository assessment" in hook
