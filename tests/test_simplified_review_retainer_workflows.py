from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_completed_assessment_adds_exact_run_final_review_action() -> None:
    source = _read("apps/web/app/AssessmentFinalReviewAction.tsx")
    navigation = _read("apps/web/app/PrimaryNavigation.tsx")

    assert 'import AssessmentFinalReviewAction from "./AssessmentFinalReviewAction";' in navigation
    assert "<AssessmentFinalReviewAction />" in navigation
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
    workspace = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")
    setup = _read("apps/web/app/operations/final-review/FinalReviewSetup.tsx")
    decision = _read("apps/web/app/operations/final-review/FinalReviewDecision.tsx")
    source = "\n".join((workspace, setup, decision))

    assert "Review and release the final report." in workspace
    assert "Approve and download final report" in decision
    assert "await ensureReview(current)" in workspace
    assert '/approved`' in workspace
    assert "await downloadApprovedPdf(latest)" in workspace
    assert "I reviewed the exact report, scorecard, evidence limitations" in decision
    assert "Request more evidence" in decision
    assert "Reject delivery" in decision
    assert 'type="password"' in setup
    assert "localStorage" not in source
    assert "document.cookie" not in source


def test_final_review_progressively_discloses_one_simple_mobile_flow() -> None:
    workspace = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")
    setup = _read("apps/web/app/operations/final-review/FinalReviewSetup.tsx")
    decision = _read("apps/web/app/operations/final-review/FinalReviewDecision.tsx")
    model = _read("apps/web/app/operations/final-review/finalReviewModel.ts")
    styles = _read("apps/web/app/operations/final-review/final-review.module.css")

    assert "!result" in workspace
    assert "<FinalReviewSetup" in workspace
    assert "<FinalReviewDecision" in workspace
    assert "serviceFromRunId(requestedRun)" in workspace
    assert 'normalized.startsWith("comprun_")' in model
    assert 'normalized.startsWith("express_run_")' in model
    assert "<select" not in setup
    assert "Assessment type is detected from the run ID." in setup
    assert "Use another report or advanced scope" in setup
    assert "Add a note or choose another decision" in decision
    assert "position: sticky" in styles
    assert ".actionBar" in styles
    assert "grid-template-columns: 190px minmax(0, 1fr)" in styles


def test_final_review_polish_has_complete_english_and_mexican_spanish_copy() -> None:
    locale = _read("apps/web/app/OperatorWorkspaceLocale.tsx")

    assert '"Review and release the final report."' in locale
    assert '"Revisa y libera el informe final."' in locale
    assert '"One exact package. One human decision. One accepted PDF."' in locale
    assert '"Un paquete exacto. Una decisión humana. Un PDF aceptado."' in locale
    assert '"Use another report or advanced scope"' in locale
    assert '"Usar otro informe o alcance avanzado"' in locale
    assert '"Delivery stays locked until this exact package is approved."' in locale
    assert '"La entrega permanece bloqueada hasta que se apruebe este paquete exacto."' in locale


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
    navigation = _read("apps/web/app/PrimaryNavigation.tsx")
    locale = _read("apps/web/app/OperatorWorkspaceLocale.tsx")

    assert 'import OperatorWorkspaceLocale from "./OperatorWorkspaceLocale";' in navigation
    assert "<OperatorWorkspaceLocale />" in navigation
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
