from pathlib import Path


HANDOFF = Path("apps/web/app/operations/final-review/FinalReviewDownloadHandoff.tsx")
LAYOUT = Path("apps/web/app/operations/final-review/layout.tsx")


def test_final_review_does_not_expose_secondary_pdf_fallback() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    # The physical Final Review tap is the only user action. The verified PDF is
    # presented through the synchronously reserved WebKit browsing context; the
    # old second-tap "PDF is ready / Open PDF" fallback must stay removed.
    assert "HTMLAnchorElement.prototype.click" in source
    assert 'data-final-review-pdf-handoff="ready"' not in source
    assert "pendingPdf" not in source
    assert 'data-final-review-pdf-open="true"' not in source
    assert '"PDF is ready"' not in source
    assert '"El PDF está listo"' not in source
    assert '"Open PDF"' not in source
    assert '"Abrir PDF"' not in source


def test_final_review_keeps_blob_alive_for_webkit_presentation() -> None:
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
    assert '"Download final assessment PDF"' in source
    assert '"Descargar PDF final de la evaluación"' in source
    assert '"Approve exact downloaded report"' in source
    assert '"Aprobar informe exacto descargado"' in source
    assert "owner test" not in source.lower()


def test_ios_reserved_window_receives_verified_blob_without_second_tap() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    reserved_path = source.split("if (reservedPdfWindow && !reservedPdfWindow.closed)", 1)[1]
    reserved_path = reserved_path.split("originalClick.call(this)", 1)[0]
    assert "targetWindow.location.replace(href)" in reserved_path
    assert "return;" in reserved_path
    assert "setPendingPdf" not in source
    assert "No second-tap handoff is rendered." in source


def test_handoff_closes_stale_reserved_window_without_shortening_blob_lifetime() -> None:
    source = HANDOFF.read_text(encoding="utf-8")

    assert "RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000" in source
    assert "REVOKE_DELAY_MS = 5 * 60 * 1000" in source
    assert "}, RESERVED_WINDOW_TIMEOUT_MS);" in source


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
