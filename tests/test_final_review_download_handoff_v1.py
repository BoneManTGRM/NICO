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


def test_handoff_is_scoped_to_final_review_route() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'from "./FinalReviewDownloadHandoff"' in source
    assert "<FinalReviewDownloadHandoff />" in source
    assert "{children}" in source
