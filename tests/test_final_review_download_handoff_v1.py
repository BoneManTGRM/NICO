from pathlib import Path


SOURCE = Path("apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx")


def test_approved_pdf_uses_persistent_user_activated_download_handoff() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "preparedApprovedPdf" in source
    assert "href={preparedApprovedPdf.url}" in source
    assert "download={preparedApprovedPdf.filename}" in source
    assert "setDownloadedArtifactDigest(preparedApprovedPdf.digest)" in source


def test_final_review_does_not_claim_download_before_user_handoff() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "APPROVED FINAL PDF downloaded" not in source
    assert "PDF FINAL APROBADO. Revisa" not in source


def test_temporary_blob_urls_are_not_revoked_immediately() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "URL.revokeObjectURL(url), 0" not in source
