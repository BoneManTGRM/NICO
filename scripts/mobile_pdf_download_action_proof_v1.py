from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

VERSION = "nico.mobile-pdf-download-action-proof.v1"
REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]'
_PREPARING_LABELS = ("preparing file", "preparando el archivo")


def _artifact_status_cleared(page: Any) -> bool:
    return bool(
        page.locator(REPORT_ACTIONS_SELECTOR).first.evaluate(
            """actions => {
              const text = String(actions.textContent || '').toLowerCase();
              return !text.includes('preparing file') && !text.includes('preparando el archivo');
            }"""
        )
    )


def install_ui_pdf_download_proof(recovery: Any) -> None:
    current = recovery._verify_manifest_and_pdf
    if getattr(current, "_nico_ui_pdf_download_proof_v1", False):
        return

    def verify_manifest_and_pdf(page: Any, frontend_origin: str, run_id: str) -> dict[str, Any]:
        direct = dict(current(page, frontend_origin, run_id))
        actions = page.locator(REPORT_ACTIONS_SELECTOR).first
        actions.wait_for(state="visible", timeout=120_000)
        pdf_button = actions.get_by_role("button", name=re.compile(r"pdf", re.I)).first
        assert pdf_button.is_visible(), "Review PDF action was not visible"
        assert pdf_button.is_enabled(), "Review PDF action was not enabled"

        with page.expect_download(timeout=240_000) as download_info:
            pdf_button.click()
        download = download_info.value
        failure = download.failure()
        assert not failure, f"Browser-managed review PDF download failed: {failure}"

        with tempfile.TemporaryDirectory(prefix="nico-review-pdf-") as directory:
            target = Path(directory) / (download.suggested_filename or f"nico-{run_id}.pdf")
            download.save_as(target)
            pdf_bytes = target.read_bytes()

        assert pdf_bytes.startswith(b"%PDF"), "UI review PDF did not have a PDF signature"
        assert len(pdf_bytes) > 1_000, "UI review PDF was unexpectedly small"
        assert run_id in (download.suggested_filename or ""), (
            f"UI review PDF filename did not retain exact run identity: {download.suggested_filename}"
        )
        page.wait_for_timeout(250)
        assert _artifact_status_cleared(page), "Review PDF action remained stuck on Preparing file"

        return {
            **direct,
            "ui_review_pdf_download_verified": True,
            "ui_review_pdf_download_size_bytes": len(pdf_bytes),
            "ui_review_pdf_download_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "ui_review_pdf_suggested_filename": download.suggested_filename,
            "ui_review_pdf_exact_run_filename_verified": True,
            "ui_review_pdf_signature_verified": True,
            "ui_review_pdf_artifact_status_cleared": True,
            "ui_review_pdf_original_user_gesture_preserved": True,
            "ui_review_pdf_proof_version": VERSION,
        }

    setattr(verify_manifest_and_pdf, "_nico_ui_pdf_download_proof_v1", True)
    setattr(verify_manifest_and_pdf, "_nico_previous", current)
    recovery._verify_manifest_and_pdf = verify_manifest_and_pdf


__all__ = ["VERSION", "install_ui_pdf_download_proof"]
