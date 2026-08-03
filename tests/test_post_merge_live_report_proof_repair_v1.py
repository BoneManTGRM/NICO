from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_BRIDGE = ROOT / "apps/web/app/AssessmentReviewPdfDownload.tsx"
DOWNLOAD_PROOF = ROOT / "scripts/mobile_pdf_download_action_proof_v1.py"


def test_review_pdf_download_filename_is_automated_draft() -> None:
    source = DOWNLOAD_BRIDGE.read_text(encoding="utf-8")

    assert "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf" in source
    assert "FINAL-PENDING-APPROVAL.pdf" not in source


def test_mobile_download_proof_binds_ui_href_to_preverified_exact_run_artifact() -> None:
    source = DOWNLOAD_PROOF.read_text(encoding="utf-8")

    assert "window.__nicoReviewPdfDownloadHref" in source
    assert 'requested_href.split("?", 1)[0].endswith(artifact_url_suffix)' in source
    assert 'direct.get("pdf_run_identity_verified") is True' in source
    assert 'direct.get("pdf_signature_verified") is True' in source
    assert "observed_sha == direct_sha" in source
    assert '"ui_review_pdf_matches_preverified_artifact": True' in source
    assert '"ui_review_pdf_exact_run_href_verified": True' in source
    assert 'page.on("response", capture_response)' not in source
    assert 'assert responses, "UI review PDF response was not observed"' not in source


def test_mobile_download_proof_rejects_false_finality_filenames() -> None:
    source = DOWNLOAD_PROOF.read_text(encoding="utf-8")

    assert '"AUTOMATED-DRAFT-PENDING-APPROVAL" in requested_filename' in source
    assert '"FINAL-PENDING-APPROVAL" not in requested_filename' in source
    assert '"FINAL-PENDING-APPROVAL" not in suggested_filename' in source
    assert '"ui_review_pdf_lifecycle_filename_verified": True' in source
