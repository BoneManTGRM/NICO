from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_completed_assessment_adds_exact_run_final_review_action() -> None:
    source = _read("apps/web/app/AssessmentFinalReviewAction.tsx")
    layout = _read("apps/web/app/layout.tsx")

    assert "<AssessmentFinalReviewAction />" in layout
    assert "Review and accept this report" in source
    assert "Revisar y aceptar este informe" in source
    assert "/operations/final-review?${query}" in source
    assert "run_id: context.run_id" in source
    assert "customer_id: context.customer_id" in source
    assert "project_id: context.project_id" in source
    assert 'query.set("lang", "es-MX")' in source
    assert "sessionStorage" in source
    assert "admin" not in source.lower().split("sessionstorage")[0][-100:]


def test_final_review_is_one_controlled_approval_and_download_action() -> None:
    source = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")

    assert "Review once. Approve once. Download the accepted report." in source
    assert "Approve and download final report" in source
    assert "await ensureReview(current)" in source
    assert '/approved`' in source
    assert "await downloadApprovedPdf(latest)" in source
    assert "I reviewed the exact report, scorecard, evidence limitations" in source
    assert "Request more evidence" in source
    assert "Reject delivery" in source
    assert 'type="password"' in source
    assert "localStorage" not in source
    assert "document.cookie" not in source


def test_retainer_workspace_requires_one_exact_baseline_and_explains_scope() -> None:
    source = _read("apps/web/app/retainer-ops/RetainerWorkspace.tsx")

    assert "See what changed after an accepted assessment." in source
    assert "does not rerun the full assessment and does not deploy code" in source
    assert "Accepted baseline run ID" in source
    assert "Choose the exact accepted Express or Comprehensive baseline run" in source
    assert "Refresh ongoing evidence" in source
    assert "Ongoing delivery health" in source
    assert "This is not the assessment technical-maturity score." in source
    assert "Optional business context" in source
    assert "Detailed evidence and scoring" in source
    assert "commit_summary" not in source
    assert "pr_summary" not in source
    assert "issue_summary" not in source


def test_operator_workspaces_preserve_mexican_spanish_locale() -> None:
    layout = _read("apps/web/app/layout.tsx")
    navigation = _read("apps/web/app/PrimaryNavigation.tsx")
    locale = _read("apps/web/app/OperatorWorkspaceLocale.tsx")

    assert 'import OperatorWorkspaceLocale from "./OperatorWorkspaceLocale";' in layout
    assert "<OperatorWorkspaceLocale />" in layout
    assert 'queryLocale === "es-MX"' in navigation
    assert 'params.set("lang", "es-MX")' in navigation
    assert "withLanguage(link.href, spanishActive)" in navigation
    assert "REVISIÓN FINAL DE NICO" in locale
    assert "SUPERVISIÓN CONTINUA DE INGENIERÍA" in locale
    assert 'document.documentElement.lang = "es-MX"' in locale
    assert 'params.get("lang") !== "es-MX"' in locale


def test_simplified_workflow_styles_are_loaded() -> None:
    layout = _read("apps/web/app/layout.tsx")
    styles = _read("apps/web/styles/workflow-simplification.css")

    assert 'import "../styles/workflow-simplification.css";' in layout
    assert ".nico-final-review-action" in styles
    assert ".nico-retainer-workspace .retainer-advanced" in styles
    assert "@media (max-width: 700px)" in styles
