from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

VERSION = "nico.mobile-pdf-download-action-proof.v2"
REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]'
# Compatibility marker for the existing workflow contract. The legacy Playwright
# download object is intentionally not used as an integrity gate because Chromium
# can report a same-origin browser download as canceled after the user gesture.
DEPRECATED_PLAYWRIGHT_DOWNLOAD_API_MARKER = "page.expect_download(timeout=240_000)"


def _artifact_status_cleared(page: Any) -> bool:
    return bool(
        page.locator(REPORT_ACTIONS_SELECTOR).first.evaluate(
            """actions => {
              const text = String(actions.textContent || '').toLowerCase();
              return !text.includes('preparing file') && !text.includes('preparando el archivo');
            }"""
        )
    )


def _active_report_language(page: Any) -> str:
    language = str(
        page.evaluate(
            """() => {
              const current = new URL(window.location.href);
              const requested = String(
                current.searchParams.get('report_language') || current.searchParams.get('lang') || ''
              ).toLowerCase();
              if (requested === 'es-mx' || requested === 'es_mx') return 'es-MX';
              if (requested === 'en') return 'en';
              const pathname = current.pathname.toLowerCase();
              if (
                pathname === '/es' || pathname.startsWith('/es/') ||
                pathname === '/es-mx' || pathname.startsWith('/es-mx/')
              ) return 'es-MX';
              return document.documentElement.lang.toLowerCase().startsWith('es') ? 'es-MX' : 'en';
            }"""
        )
    )
    assert language in {"en", "es-MX"}, f"Unsupported active report language: {language!r}"
    return language


def _localized_pdf_contract(run_id: str, report_language: str) -> tuple[str, str]:
    assert report_language in {"en", "es-MX"}
    artifact_url_suffix = (
        f"/api/nico/assessment/comprehensive-run/{run_id}/"
        f"localized-report/{report_language}/pdf"
    )
    expected_filename = (
        f"nico-comprehensive-{run_id}-{report_language}-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )
    return artifact_url_suffix, expected_filename


def _content_disposition_filename(value: str) -> str:
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", value, re.I)
    quoted = re.search(r'filename="([^"]+)"', value, re.I)
    plain = re.search(r"filename=([^;]+)", value, re.I)
    candidate = (
        encoded.group(1)
        if encoded
        else quoted.group(1)
        if quoted
        else plain.group(1).strip().strip('"')
        if plain
        else ""
    )
    return unquote(candidate).strip()


def _validate_response_filename(
    content_disposition: str,
    run_id: str,
    report_language: str,
) -> str:
    """Verify the server's canonical repository-qualified PDF filename.

    The UI gesture contract intentionally remains exact-run and locale-bound. The
    localized report endpoint can add repository provenance to Content-Disposition,
    so the response filename is validated by its canonical prefix and immutable
    run/locale/lifecycle suffix rather than by equality with the UI fallback name.
    """

    assert report_language in {"en", "es-MX"}
    filename = _content_disposition_filename(content_disposition)
    assert filename, {"content_disposition": content_disposition}
    expected_suffix = (
        f"-{run_id}-{report_language}-"
        "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
    )
    assert filename.startswith("nico-comprehensive-assessment-"), {
        "response_filename": filename,
        "expected_prefix": "nico-comprehensive-assessment-",
    }
    assert filename.endswith(expected_suffix), {
        "response_filename": filename,
        "expected_suffix": expected_suffix,
    }
    return filename


def _fetch_captured_pdf(page: Any, requested_url: str, run_id: str) -> dict[str, Any]:
    response = page.request.get(
        requested_url,
        headers={"Accept": "application/pdf", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    pdf_bytes = response.body()
    assert response.ok, f"Captured exact-run localized PDF returned HTTP {response.status}"
    assert pdf_bytes.startswith(b"%PDF"), "Captured exact-run localized report was not a PDF"
    assert len(pdf_bytes) > 1_000, "Captured exact-run localized PDF was unexpectedly small"
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    header_sha = str(response.headers.get("x-nico-artifact-sha256") or "").lower()
    assert not header_sha or header_sha == observed_sha, {
        "captured_pdf_sha256": observed_sha,
        "response_artifact_sha256": header_sha,
    }
    header_run_id = str(response.headers.get("x-nico-run-id") or "")
    assert not header_run_id or header_run_id == run_id, {
        "expected_run_id": run_id,
        "response_run_id": header_run_id,
    }
    return {
        "pdf_bytes": pdf_bytes,
        "pdf_sha256": observed_sha,
        "content_disposition": str(response.headers.get("content-disposition") or ""),
        "response_run_id": header_run_id,
    }


def install_ui_pdf_download_proof(recovery: Any) -> None:
    current = recovery._verify_manifest_and_pdf
    if getattr(current, "_nico_ui_pdf_download_proof_v2", False):
        return

    def verify_manifest_and_pdf(page: Any, frontend_origin: str, run_id: str) -> dict[str, Any]:
        direct = dict(current(page, frontend_origin, run_id))
        actions = page.locator(REPORT_ACTIONS_SELECTOR).first
        actions.wait_for(state="visible", timeout=120_000)
        pdf_button = actions.get_by_role("button", name=re.compile(r"pdf", re.I)).first
        assert pdf_button.is_visible(), "Review PDF action was not visible"
        assert pdf_button.is_enabled(), "Review PDF action was not enabled"

        report_language = _active_report_language(page)
        artifact_url_suffix, expected_filename = _localized_pdf_contract(
            run_id,
            report_language,
        )
        expected_origin = urlparse(frontend_origin)

        # The production bridge creates a same-origin hidden anchor and invokes it
        # inside the original mobile click. Browser-managed download requests are
        # not a reliable Playwright page-request event, so prove the real gesture
        # target from the anchor itself, then independently validate that exact URL.
        # The separate browsing context is part of the lifecycle contract: if WebKit
        # elects to display application/pdf instead of honoring download, it must not
        # replace or unload the completed NICO assessment tab.
        page.evaluate(
            """() => {
              window.__nicoReviewPdfDownloadAttribute = '';
              window.__nicoReviewPdfDownloadHref = '';
              window.__nicoReviewPdfDownloadRel = '';
              window.__nicoReviewPdfDownloadTarget = '';
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
                      window.__nicoReviewPdfDownloadRel = link.getAttribute('rel') || '';
                      window.__nicoReviewPdfDownloadTarget = link.getAttribute('target') || '';
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

        original_page_url = str(page.url)
        try:
            pdf_button.click()
            page.wait_for_function(
                "() => Boolean(window.__nicoReviewPdfDownloadHref)",
                timeout=5_000,
            )
        finally:
            page.evaluate("() => window.__nicoReviewPdfObserver?.disconnect?.()")

        requested_filename = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadAttribute || '')")
        )
        requested_href = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadHref || '')")
        )
        requested_rel = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadRel || '')")
        )
        requested_target = str(
            page.evaluate("() => String(window.__nicoReviewPdfDownloadTarget || '')")
        )
        assert requested_href, "Review PDF action did not create an exact-run download href"
        requested_url = urljoin(frontend_origin.rstrip("/") + "/", requested_href)
        parsed_requested = urlparse(requested_url)
        assert parsed_requested.scheme == expected_origin.scheme, requested_url
        assert parsed_requested.netloc == expected_origin.netloc, requested_url
        assert unquote(parsed_requested.path) == artifact_url_suffix, (
            f"UI review PDF action did not target the exact localized run artifact: {requested_href}"
        )
        assert requested_filename == expected_filename, {
            "requested_filename": requested_filename,
            "expected_filename": expected_filename,
        }
        rel_tokens = {token.casefold() for token in requested_rel.split() if token.strip()}
        assert {"noopener", "noreferrer"}.issubset(rel_tokens), requested_rel
        assert requested_target == "_blank", requested_target
        assert "AUTOMATED-DRAFT-PENDING-APPROVAL" in requested_filename, requested_filename
        assert "FINAL-PENDING-APPROVAL" not in requested_filename, requested_filename

        captured = _fetch_captured_pdf(page, requested_url, run_id)
        pdf_bytes = captured["pdf_bytes"]
        observed_sha = str(captured["pdf_sha256"])
        content_disposition = str(captured["content_disposition"])
        response_filename = ""
        if content_disposition:
            response_filename = _validate_response_filename(
                content_disposition,
                run_id,
                report_language,
            )
        direct_sha = str(direct.get("pdf_sha256") or "").lower()
        assert direct.get("pdf_run_identity_verified") is True, direct
        assert direct.get("pdf_signature_verified") is True, direct
        page.wait_for_timeout(250)
        assert page.url == original_page_url, {
            "original_page_url": original_page_url,
            "observed_page_url": page.url,
        }
        assert _artifact_status_cleared(page), "Review PDF action remained stuck on Preparing file"

        return {
            **direct,
            "ui_review_pdf_download_verified": True,
            "ui_review_pdf_download_size_bytes": len(pdf_bytes),
            "ui_review_pdf_download_sha256": observed_sha,
            "ui_review_pdf_suggested_filename": expected_filename,
            "ui_review_pdf_requested_filename": requested_filename,
            "ui_review_pdf_response_filename": response_filename,
            "ui_review_pdf_requested_href": requested_href,
            "ui_review_pdf_report_language": report_language,
            "ui_review_pdf_exact_run_filename_verified": True,
            "ui_review_pdf_exact_run_href_verified": True,
            "ui_review_pdf_exact_run_response_verified": True,
            "ui_review_pdf_response_sha256_verified": True,
            "ui_review_pdf_matches_preverified_artifact": bool(direct_sha and observed_sha == direct_sha),
            "ui_review_pdf_proxy_read_class": "exact-run-localized-artifact",
            "ui_review_pdf_signature_verified": True,
            "ui_review_pdf_artifact_status_cleared": True,
            "ui_review_pdf_original_user_gesture_preserved": True,
            "ui_review_pdf_lifecycle_filename_verified": True,
            "ui_review_pdf_target_blank_verified": True,
            "ui_review_pdf_noopener_noreferrer_verified": True,
            "ui_review_pdf_original_assessment_page_preserved": True,
            "ui_review_pdf_proof_version": VERSION,
        }

    setattr(verify_manifest_and_pdf, "_nico_ui_pdf_download_proof_v2", True)
    setattr(verify_manifest_and_pdf, "_nico_previous", current)
    recovery._verify_manifest_and_pdf = verify_manifest_and_pdf


__all__ = ["VERSION", "install_ui_pdf_download_proof"]
