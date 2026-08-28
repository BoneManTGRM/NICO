from pathlib import Path

import pytest

from scripts import mobile_pdf_download_action_proof_v1 as proof


def test_mobile_pdf_download_proof_tracks_localized_draft_contract() -> None:
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


def test_mobile_pdf_download_proof_tracks_exact_accepted_edition_contract() -> None:
    contract = proof._pdf_action_contract(
        "comprun_contract",
        "es-MX",
        proof.ACCEPTED_PDF_KIND,
    )

    assert contract["path"] == (
        "/api/nico/assessment/comprehensive-run/comprun_contract/report/pdf"
    )
    assert contract["fallback_filename"] == (
        "nico-comprehensive-comprun_contract-APPROVED-ACCEPTED-EDITION.pdf"
    )
    assert contract["lifecycle"] == "exact-approved-accepted-edition"


def test_mobile_pdf_download_proof_selects_locale_and_lifecycle_fail_closed() -> None:
    draft = {
        "kind": proof.DRAFT_PDF_KIND,
        "report_language": "es-MX",
        "visible": True,
        "enabled": True,
    }
    accepted = {
        "kind": proof.ACCEPTED_PDF_KIND,
        "report_language": "en",
        "visible": True,
        "enabled": True,
    }

    assert proof._choose_pdf_action([draft], "es-MX") == draft
    assert proof._choose_pdf_action([accepted], "en") == accepted
    assert proof._choose_pdf_action([accepted, draft], "es-MX") == draft

    with pytest.raises(AssertionError):
        proof._choose_pdf_action([accepted, draft], "en")
    with pytest.raises(AssertionError):
        proof._choose_pdf_action(
            [{**draft, "kind": "unknown-lifecycle"}],
            "es-MX",
        )


def test_mobile_pdf_download_proof_accepts_canonical_repository_qualified_response_filename() -> None:
    filename = (
        "nico-comprehensive-assessment-BoneManTGRM-NICO-comprun_contract-en-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )
    disposition = f'attachment; filename="{filename}"'

    assert proof._validate_response_filename(
        disposition,
        "comprun_contract",
        "en",
    ) == filename

    with pytest.raises(AssertionError):
        proof._validate_response_filename(
            disposition,
            "comprun_other",
            "en",
        )

    with pytest.raises(AssertionError):
        proof._validate_response_filename(
            disposition.replace("PENDING-APPROVAL", "APPROVED"),
            "comprun_contract",
            "en",
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
    assert "window.__nicoAcceptancePdfAnchor" in source
    assert "unquote(parsed_anchor.path) == artifact_url_suffix" in source
    assert "_fetch_captured_pdf(" in source
    assert "_validate_response_filename(" in source
    assert 're.fullmatch(r"[0-9a-f]{64}", header_sha)' in source
    assert "assert header_sha == observed_sha" in source
    assert 'response.headers.get("x-nico-canonical-truth-sha256")' in source
    assert 'captured["canonical_truth_sha256"] == direct_canonical_truth_sha256' in source
    assert 'x-nico-accepted-pdf-sha256' in source
    assert '"ui_review_pdf_action_kind": action_kind' in source
    assert '"ui_review_pdf_network_path": artifact_url_suffix' in source
    assert '"ui_review_pdf_original_page_visible_after_action": True' in source
    assert proof.DEPRECATED_PLAYWRIGHT_DOWNLOAD_API_MARKER == (
        "page.expect_download(timeout=240_000)"
    )
