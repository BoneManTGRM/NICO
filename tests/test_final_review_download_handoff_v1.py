from pathlib import Path


HANDOFF = Path("apps/web/app/operations/final-review/FinalReviewDownloadHandoff.tsx")
LAYOUT = Path("apps/web/app/operations/final-review/layout.tsx")


def test_final_review_exposes_explicit_fallback_for_generated_pdf() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "HTMLAnchorElement.prototype.click" in source
    assert 'data-final-review-pdf-handoff={pendingPdf ? "ready" : "pending"}' in source
    assert 'href={pendingPdf.url}' in source
    assert 'download={pendingPdf.filename}' in source
    assert 'target="_blank"' in source
    assert 'data-final-review-pdf-open="true"' in source
    assert '"Open PDF"' in source
    assert '"Abrir PDF"' in source


def test_final_review_keeps_blob_alive_for_webkit_fallback() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "REVOKE_DELAY_MS = 5 * 60 * 1000" in source
    assert "originalRevokeObjectURL.call(URL, url)" in source
    assert "window.setTimeout" in source
    assert "URL.revokeObjectURL(url), 0" not in source


def test_ios_final_review_reserves_user_activated_pdf_window_before_async_work() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "function isIOSFamilyWebKit" in source
    assert 'document.addEventListener("click", reservePdfWindow, true)' in source
    assert 'window.open("about:blank", "nico-comprehensive-pdf")' in source
    assert '"Approve and download final PDF"' in source
    assert '"Aprobar y descargar PDF final"' in source
    assert '"Download exact PDF to review"' in source
    assert '"Descargar PDF exacto para revisión"' in source
    assert '"Download approved PDF again"' in source
    assert '"Descargar nuevamente el PDF aprobado"' in source


def test_ios_reserved_window_receives_verified_blob_instead_of_late_programmatic_click() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    reserved_path = source.split("if (reservedPdfWindow && !reservedPdfWindow.closed)", 1)[1]
    reserved_path = reserved_path.split("originalClick.call(this)", 1)[0]
    assert "targetWindow.location.replace(href)" in reserved_path
    assert "return;" in reserved_path
    assert "setPendingPdf({url: href, filename, action})" in source


def test_handoff_closes_stale_reserved_window_without_shortening_blob_fallback() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000" in source
    assert "APPROVED_PDF_PRESENTATION_TIMEOUT_MS = 60 * 1000" in source
    assert "REVOKE_DELAY_MS = 5 * 60 * 1000" in source
    assert "}, RESERVED_WINDOW_TIMEOUT_MS);" in source


def test_handoff_restores_global_hooks_and_closes_unused_reserved_window() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert 'document.removeEventListener("click", reservePdfWindow, true)' in source
    assert "clearReservedPdfWindow(true)" in source
    assert "HTMLAnchorElement.prototype.click = originalClick" in source
    assert "URL.revokeObjectURL = originalRevokeObjectURL" in source
    assert "window.fetch = originalFetch" in source


def test_final_review_distinguishes_draft_failed_approval_and_approved_pdf() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert 'data-final-review-artifact-outcome={outcome?.kind || "unknown"}' in source
    assert 'setOutcome({kind: "draft-ready"})' not in source  # action-specific branch is required
    assert 'action === "review" ? "draft-ready" : "approved-pdf-ready"' in source
    assert 'setOutcome({kind: "approval-failed", httpStatus: response.status})' in source
    assert 'setOutcome({kind: "approval-recorded"})' in source
    assert 'kind: "approved-pdf-not-presented"' in source
    assert "Approval DID NOT complete. This action did not create an approved-final PDF" in source
    assert "Verified DRAFT. Human approval is still pending" in source
    assert "APPROVED FINAL PDF verified and ready to open" in source
    assert "Delivery remains separate and blocked" in source


def test_truth_layer_observes_approval_without_adding_delivery_authority() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "window.fetch = trackedFetch" in source
    assert 'approvalDecisionFromBody(init?.body) === "approved"' in source
    assert "responseConfirmsApproval(payload)" in source
    assert '"delivery_authorized"' not in source
    assert '"/authorize-delivery"' not in source


def test_handoff_is_scoped_to_final_review_route() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'from "./FinalReviewDownloadHandoff"' in source
    assert "<FinalReviewDownloadHandoff />" in source
    assert "{children}" in source
