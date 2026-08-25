from pathlib import Path

from scripts import mobile_pdf_download_action_proof_v1 as proof


def test_mobile_pdf_download_proof_tracks_localized_report_contract() -> None:
    run_id = "comprun_contract"

    en_path, en_filename = proof._localized_pdf_contract(run_id, "en")
    assert en_path == (
        "/api/nico/assessment/comprehensive-run/comprun_contract/"
        "localized-report/en/pdf"
    )
    assert en_filename == (
        "nico-comprehensive-comprun_contract-en-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )

    es_path, es_filename = proof._localized_pdf_contract(run_id, "es-MX")
    assert es_path == (
        "/api/nico/assessment/comprehensive-run/comprun_contract/"
        "localized-report/es-MX/pdf"
    )
    assert es_filename == (
        "nico-comprehensive-comprun_contract-es-MX-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )


def test_mobile_pdf_download_proof_does_not_depend_on_download_object_bookkeeping() -> None:
    source = Path("scripts/mobile_pdf_download_action_proof_v1.py").read_text(encoding="utf-8")

    assert "with page.expect_download" not in source
    assert "download.failure()" not in source
    assert "download.path()" not in source
    assert "download.save_as(" not in source
    assert "page.expect_request(" in source
    assert "localized-report/{report_language}/pdf" in source
    assert "_fetch_captured_pdf(page, requested_url, run_id)" in source
    assert proof.DEPRECATED_PLAYWRIGHT_DOWNLOAD_API_MARKER == (
        "page.expect_download(timeout=240_000)"
    )
