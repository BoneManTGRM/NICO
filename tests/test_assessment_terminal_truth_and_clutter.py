from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_terminal_outcome_guard_preserves_pending_stages_and_maps_backend_stage() -> None:
    source = _read("apps/web/app/AssessmentStatusOutcomeGuard.tsx")

    assert "const BACKEND_TO_UI_STAGE" in source
    assert 'validate_final_artifacts: "truth_and_review_gates"' in source
    assert "function normalizeTerminalProgress" in source
    assert "Pending and planned stages did not execute" in source
    assert 'failure_ui_stage: uiStage || backendStage' in source
    assert 'status: terminalStatus' in source
    assert 'return {...item, status: "pending"};' in source
    assert "interruptedStatus" not in source


def test_assessment_route_does_not_load_default_project_trends_or_replace_repository_value() -> None:
    source = _read("apps/web/app/GenericRepositoryExample.tsx")

    assert "function isAssessmentRoute()" in source
    assert "function applyAssessmentRepositoryPlaceholder()" in source
    assert "if (isAssessmentRoute())" in source
    assert "removeCommercialOpsPanel();" in source
    assert "applyAssessmentRepositoryPlaceholder();" in source
    assert "Legacy home-page content must never overwrite" in source
    assert 'fetchJson("/projects/default_project/trends")' in source

    assessment_branch = source.split("if (isAssessmentRoute())", 1)[1].split("let cancelled", 1)[0]
    assert "return;" in assessment_branch
    assert "fetchJson" not in assessment_branch
    assert "applyGenericRepositoryExample" not in assessment_branch


def test_commercial_ops_panel_is_limited_to_legacy_home() -> None:
    source = _read("apps/web/app/GenericRepositoryExample.tsx")

    assert "function isLegacyHomeRoute()" in source
    assert "if (!isLegacyHomeRoute())" in source
    assert "removeCommercialOpsPanel();" in source
    assert "if (!isLegacyHomeRoute()) return;" in source


def test_non_home_navigation_does_not_issue_unused_cross_origin_runtime_requests() -> None:
    source = _read("apps/web/app/GenericRepositoryExample.tsx")
    effect_before_fetch = source.split(
        "export default function GenericRepositoryExample()",
        1,
    )[1].split("let cancelled", 1)[0]

    assert "if (!isLegacyHomeRoute())" in effect_before_fetch
    non_home_branch = effect_before_fetch.split("if (!isLegacyHomeRoute())", 1)[1]
    assert "removeCommercialOpsPanel();" in non_home_branch
    assert "return;" in non_home_branch
