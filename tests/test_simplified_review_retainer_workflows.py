from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_completed_assessment_adds_exact_run_final_review_action() -> None:
    source = _read("apps/web/app/AssessmentFinalReviewAction.tsx")
    navigation = _read("apps/web/app/PrimaryNavigation.tsx")
    layout = _read("apps/web/app/layout.tsx")

    assert 'import AssessmentFinalReviewAction from "./AssessmentFinalReviewAction";' in layout
    assert "<AssessmentFinalReviewAction />" in layout
    assert "AssessmentFinalReviewAction" not in navigation
    assert (layout + navigation).count("<AssessmentFinalReviewAction />") == 1
    assert "Review and accept this report" in source
    assert "Revisar y aceptar este informe" in source
    assert "/operations/final-review?${query}" in source
    assert "run_id: context.run_id" in source
    assert "customer_id: context.customer_id" in source
    assert "project_id: context.project_id" in source
    assert 'query.set("lang", "es-MX")' in source
    assert "sessionStorage" in source
    assert "admin" not in source.lower().split("sessionstorage")[0][-100:]


def test_final_review_uses_canonical_accepted_edition_api_for_strategic() -> None:
    source = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")

    assert 'data-review-contract={canonical ? "accepted-edition-v2"' in source
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review" in source
    assert "review_authorized: true" in source
    assert "authorization_confirmed: true" in source
    assert "reviewer_role: reviewerRole.trim()" in source
    assert 'decision,\n          decision_reason: reason' in source
    assert 'await submitCanonicalDecision("approved")' in source
    assert "await downloadCanonicalPdf(reviewed)" in source
    assert "report_artifact_digest" in source
    assert "approval_certificate_sha256" in source
    assert "accepted_edition_manifest_sha256" in source


def test_final_review_is_one_controlled_approval_and_download_action() -> None:
    source = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")

    assert "Internal final review and client-ready authorization." in source
    assert "Approve and download final PDF" in source
    assert "I reviewed this exact report." in source
    assert "scorecard, evidence limitations, immutable run identity, artifact digest" in source
    assert "Request more evidence" in source
    assert "Reject delivery" in source
    assert 'recordOtherDecision("request_more_evidence")' in source
    assert 'recordOtherDecision("rejected")' in source
    assert "localStorage" not in source
    assert "document.cookie" not in source


def test_final_review_prioritizes_reviewer_role_and_exact_run_identity() -> None:
    source = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")

    reviewer = source.index("Authorized reviewer")
    role = source.index("Reviewer role")
    open_review = source.index("Open review")
    advanced = source.index("Change report identity or scope")

    assert reviewer < role < open_review < advanced
    assert "The report identity is already attached" in source
    assert "No secret is stored in the URL or browser storage" in source
    assert "Operator admin token" in source
    assert 'type="password"' in source


def test_final_review_has_mexican_spanish_accepted_edition_parity() -> None:
    source = _read("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx")

    assert "CONTROL INTERNO DE CALIDAD NICO" in source
    assert "Aprobar y descargar PDF final" in source
    assert "Solicitar más evidencia" in source
    assert "Rechazar entrega" in source
    assert "Certificado de aprobación" in source
    assert 'query.get("lang") === "es-MX"' in source
    assert "document.documentElement.lang = requestedLocale" in source


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
    assert 'queryLocale === "es-mx"' in navigation
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
