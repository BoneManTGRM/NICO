from pathlib import Path


HANDOFF = Path("apps/web/app/operations/final-review/FinalReviewDownloadHandoff.tsx")
LAYOUT = Path("apps/web/app/operations/final-review/layout.tsx")


def test_final_review_exposes_explicit_fallback_for_generated_pdf() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "HTMLAnchorElement.prototype.click" in source
    assert 'href={pendingPdf.url}' in source
    assert 'download={pendingPdf.filename}' in source
    assert 'target="_blank"' in source
    assert "Open / download PDF" in source
    assert "Abrir / descargar PDF" in source


def test_final_review_keeps_blob_alive_for_webkit_fallback() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "REVOKE_DELAY_MS" in source
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


def test_ios_reserved_window_receives_verified_blob_instead_of_late_programmatic_click() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    reserved_path = source.split("if (reservedPdfWindow && !reservedPdfWindow.closed)", 1)[1]
    reserved_path = reserved_path.split("originalClick.call(this)", 1)[0]
    assert "targetWindow.location.replace(href)" in reserved_path
    assert "return;" in reserved_path
    assert "setPendingPdf({url: href, filename})" in source


def test_handoff_restores_global_hooks_and_closes_unused_reserved_window() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert 'document.removeEventListener("click", reservePdfWindow, true)' in source
    assert "clearReservedPdfWindow(true)" in source
    assert "HTMLAnchorElement.prototype.click = originalClick" in source
    assert "URL.revokeObjectURL = originalRevokeObjectURL" in source


def test_handoff_is_scoped_to_final_review_route() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'from "./FinalReviewDownloadHandoff"' in source
    assert "<FinalReviewDownloadHandoff />" in source
    assert "{children}" in source
