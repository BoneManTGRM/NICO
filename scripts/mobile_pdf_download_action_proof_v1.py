from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

VERSION = "nico.mobile-pdf-download-action-proof.v1"
REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]'


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

        page.evaluate(
            """() => {
              window.__nicoReviewPdfDownloadAttribute = '';
              window.__nicoReviewPdfDownloadHref = '';
              window.__nicoReviewPdfObserver?.disconnect?.();
              const observer = new MutationObserver(records => {
                for (const record of records) {
                  for (const node of record.addedNodes) {
                    if (!(node instanceof Element)) continue;
                    const link = node.matches('[data-nico-review-pdf-download="true"]')
                      ? node
                      : node.querySelector?.('[data-nico-review-pdf-download="true"]');
                    if (link) {
                      window.__nicoReviewPdfDownloadAttribute = link.getAttribute('download') || '';
                      window.__nicoReviewPdfDownloadHref = link.getAttribute('href') || '';
                      observer.disconnect();
                      return;
                    }
                  }
                }
              });
              observer.observe(document.body, {childList: true, subtree: true});
              window.__nicoReviewPdfObserver = observer;
            }"""
        )

        artifact_url_suffix = f"/api/nico/assessment/comprehensive-run/{run_id}/report/pdf"
        try:
            with page.expect_download(timeout=240_000) as download_info:
                pdf_button.click()
            download = download_info.value
            failure = download.failure()
            assert not failure, f"Browser-managed review PDF download failed: {failure}"

            with tempfile.TemporaryDirectory(prefix="nico-review-pdf-") as directory:
                target = Path(directory) / (download.suggested_filename or f"nico-{run_id}.pdf")
                download.save_as(target)
                pdf_bytes = target.read_bytes()
        finally:
            page.evaluate("() => window.__nicoReviewPdfObserver?.disconnect?.()")

        requested_filename = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadAttribute || '')")
        )
        requested_href = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadHref || '')")
        )
        suggested_filename = str(download.suggested_filename or "")
        assert pdf_bytes.startswith(b"%PDF"), "UI review PDF did not have a PDF signature"
        assert len(pdf_bytes) > 1_000, "UI review PDF was unexpectedly small"
        assert run_id in requested_filename, (
            f"UI review PDF download attribute did not retain exact run identity: {requested_filename}"
        )
        assert requested_href.split("?", 1)[0].endswith(artifact_url_suffix), (
            f"UI review PDF action did not target the exact-run artifact: {requested_href}"
        )
        assert "AUTOMATED-DRAFT-PENDING-APPROVAL" in requested_filename, requested_filename
        assert "FINAL-PENDING-APPROVAL" not in requested_filename, requested_filename
        assert "FINAL-PENDING-APPROVAL" not in suggested_filename, suggested_filename
        observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
        direct_sha = str(direct.get("pdf_sha256") or "").lower()
        assert direct.get("pdf_run_identity_verified") is True, direct
        assert direct.get("pdf_signature_verified") is True, direct
        assert direct_sha and observed_sha == direct_sha, {
            "ui_download_sha256": observed_sha,
            "preverified_exact_run_sha256": direct_sha,
        }
        page.wait_for_timeout(250)
        assert _artifact_status_cleared(page), "Review PDF action remained stuck on Preparing file"

        return {
            **direct,
            "ui_review_pdf_download_verified": True,
            "ui_review_pdf_download_size_bytes": len(pdf_bytes),
            "ui_review_pdf_download_sha256": observed_sha,
            "ui_review_pdf_suggested_filename": suggested_filename,
            "ui_review_pdf_requested_filename": requested_filename,
            "ui_review_pdf_requested_href": requested_href,
            "ui_review_pdf_exact_run_filename_verified": True,
            "ui_review_pdf_exact_run_href_verified": True,
            "ui_review_pdf_exact_run_response_verified": True,
            "ui_review_pdf_response_sha256_verified": True,
            "ui_review_pdf_matches_preverified_artifact": True,
            "ui_review_pdf_proxy_read_class": "exact-run-artifact",
            "ui_review_pdf_signature_verified": True,
            "ui_review_pdf_artifact_status_cleared": True,
            "ui_review_pdf_original_user_gesture_preserved": True,
            "ui_review_pdf_lifecycle_filename_verified": True,
            "ui_review_pdf_proof_version": VERSION,
        }

    setattr(verify_manifest_and_pdf, "_nico_ui_pdf_download_proof_v1", True)
    setattr(verify_manifest_and_pdf, "_nico_previous", current)
    recovery._verify_manifest_and_pdf = verify_manifest_and_pdf


__all__ = ["VERSION", "install_ui_pdf_download_proof"]
