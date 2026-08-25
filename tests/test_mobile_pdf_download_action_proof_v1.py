from pathlib import Path

import pytest

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


def test_server_content_disposition_accepts_repository_qualified_exact_run_filename() -> None:
    proof._assert_server_content_disposition(
        'attachment; filename="nico-comprehensive-assessment-BoneManTGRM-NICO-'
        'comprun_contract-en-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"',
        run_id="comprun_contract",
        report_language="en",
    )


def test_server_content_disposition_remains_exact_run_and_pdf_fail_closed() -> None:
    with pytest.raises(AssertionError):
        proof._assert_server_content_disposition(
            'attachment; filename="nico-comprehensive-assessment-BoneManTGRM-NICO-'
            'comprun_other-en-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"',
            run_id="comprun_contract",
            report_language="en",
        )

    with pytest.raises(AssertionError):
        proof._assert_server_content_disposition(
            'attachment; filename="nico-comprehensive-assessment-BoneManTGRM-NICO-'
            'comprun_contract-en-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf.json"',
            run_id="comprun_contract",
            report_language="en",
        )


def test_mobile_pdf_download_proof_uses_real_anchor_contract_not_download_events() -> None:
    source = Path("scripts/mobile_pdf_download_action_proof_v1.py").read_text(encoding="utf-8")

    assert "with page.expect_download" not in source
    assert "with page.expect_request" not in source
    assert "download.failure()" not in source
    assert "download.path()" not in source
    assert "download.save_as(" not in source
    assert "MutationObserver" in source
    assert 'data-nico-review-pdf-download="true"' in source
    assert "window.__nicoReviewPdfDownloadHref" in source
    assert "unquote(parsed_requested.path) == artifact_url_suffix" in source
    assert "_fetch_captured_pdf(page, requested_url, run_id)" in source
    assert proof.DEPRECATED_PLAYWRIGHT_DOWNLOAD_API_MARKER == (
        "page.expect_download(timeout=240_000)"
    )
