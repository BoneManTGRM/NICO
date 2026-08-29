from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

# Keep the established evidence-schema identifier: production Chromium/WebKit
# workflows consume this version and the stronger lifecycle fields are additive.
VERSION = "nico.mobile-pdf-download-action-proof.v1"
REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]'
DRAFT_PDF_KIND = "localized-draft-pending-approval"
ACCEPTED_PDF_KIND = "accepted-edition"
SUPPORTED_PDF_KINDS = {DRAFT_PDF_KIND, ACCEPTED_PDF_KIND}
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


def _pdf_action_contract(
    run_id: str,
    report_language: str,
    action_kind: str,
) -> dict[str, str]:
    assert report_language in {"en", "es-MX"}
    assert action_kind in SUPPORTED_PDF_KINDS
    if action_kind == DRAFT_PDF_KIND:
        path, fallback_filename = _localized_pdf_contract(run_id, report_language)
        return {
            "path": path,
            "fallback_filename": fallback_filename,
            "lifecycle": "localized-draft-pending-human-approval",
            "read_class": "exact-run-localized-artifact",
        }
    return {
        "path": f"/api/nico/assessment/comprehensive-run/{run_id}/report/pdf",
        "fallback_filename": (
            f"nico-comprehensive-{run_id}-APPROVED-ACCEPTED-EDITION.pdf"
        ),
        "lifecycle": "exact-approved-accepted-edition",
        "read_class": "exact-run-accepted-edition",
    }


def _choose_pdf_action(
    actions: list[dict[str, Any]],
    requested_report_language: str,
) -> dict[str, Any]:
    """Select the requested-locale action while proving the complete button set.

    An approved cross-locale surface intentionally contains two independent actions:
    the immutable source-language accepted edition and a newly generated requested-
    locale draft. The proof exercises the requested-locale draft in that case. When
    the requested locale is the accepted source language, the accepted edition is the
    sole action. Unapproved surfaces expose only the requested-locale draft.
    """

    assert requested_report_language in {"en", "es-MX"}
    assert actions, "No terminal PDF action was rendered"
    assert all(item.get("kind") in SUPPORTED_PDF_KINDS for item in actions), actions
    assert all(item.get("report_language") in {"en", "es-MX"} for item in actions), actions
    assert all(item.get("visible") is True for item in actions), actions
    assert all(item.get("enabled") is True for item in actions), actions

    accepted = [item for item in actions if item.get("kind") == ACCEPTED_PDF_KIND]
    drafts = [item for item in actions if item.get("kind") == DRAFT_PDF_KIND]
    assert len(accepted) <= 1 and len(drafts) <= 1, actions
    if accepted and accepted[0].get("report_language") == requested_report_language:
        assert not drafts, {
            "reason": "accepted_source_locale_must_not_offer_regenerated_draft",
            "actions": actions,
        }
        return accepted[0]

    requested_drafts = [
        item
        for item in drafts
        if item.get("report_language") == requested_report_language
    ]
    assert len(requested_drafts) == 1, {
        "reason": "requested_locale_pdf_action_missing_or_ambiguous",
        "requested_report_language": requested_report_language,
        "actions": actions,
    }
    if accepted:
        assert accepted[0].get("report_language") != requested_report_language, actions
    return requested_drafts[0]


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
    """Verify the server's canonical repository-qualified PDF filename."""

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


def _fetch_captured_pdf(
    page: Any,
    requested_url: str,
    run_id: str,
    *,
    action_kind: str,
    report_language: str,
) -> dict[str, Any]:
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
    assert re.fullmatch(r"[0-9a-f]{64}", header_sha), {
        "missing_or_invalid_artifact_sha256_header": header_sha,
    }
    assert header_sha == observed_sha, {
        "captured_pdf_sha256": observed_sha,
        "response_artifact_sha256": header_sha,
    }
    header_run_id = str(response.headers.get("x-nico-run-id") or "")
    assert header_run_id == run_id, {
        "expected_run_id": run_id,
        "response_run_id": header_run_id,
    }
    canonical_truth_sha256 = str(
        response.headers.get("x-nico-canonical-truth-sha256") or ""
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{64}", canonical_truth_sha256), {
        "missing_or_invalid_canonical_truth_sha256_header": canonical_truth_sha256,
    }
    accepted_pdf_sha256 = str(
        response.headers.get("x-nico-accepted-pdf-sha256") or ""
    ).lower()
    response_report_language = str(
        response.headers.get("x-nico-report-language") or ""
    ).strip()
    assessment_rerun = str(
        response.headers.get("x-nico-assessment-rerun") or ""
    ).strip().lower()
    if action_kind == DRAFT_PDF_KIND:
        assert response_report_language == report_language, {
            "expected_report_language": report_language,
            "response_report_language": response_report_language,
        }
        assert assessment_rerun == "false", {
            "assessment_rerun": assessment_rerun,
        }
        assert not accepted_pdf_sha256, {
            "localized_draft_must_not_claim_accepted_pdf": accepted_pdf_sha256,
        }
    else:
        assert action_kind == ACCEPTED_PDF_KIND
        assert re.fullmatch(r"[0-9a-f]{64}", accepted_pdf_sha256), {
            "missing_or_invalid_accepted_pdf_sha256_header": accepted_pdf_sha256,
        }
        assert accepted_pdf_sha256 == observed_sha, {
            "accepted_pdf_sha256": accepted_pdf_sha256,
            "observed_pdf_sha256": observed_sha,
        }
    return {
        "pdf_bytes": pdf_bytes,
        "pdf_sha256": observed_sha,
        "content_disposition": str(response.headers.get("content-disposition") or ""),
        "response_run_id": header_run_id,
        "artifact_hash_header_verified": True,
        "canonical_truth_sha256": canonical_truth_sha256,
        "accepted_pdf_sha256": accepted_pdf_sha256,
        "accepted_edition_digest_verified": action_kind == ACCEPTED_PDF_KIND,
        "response_report_language": response_report_language,
        "assessment_rerun": assessment_rerun,
        "localized_draft_identity_verified": action_kind == DRAFT_PDF_KIND,
    }


def _load_source_bound_pdf(
    source_proof_path: Path,
    run_id: str,
    report_language: str,
) -> dict[str, Any]:
    """Reuse exact-SHA bilingual bytes already certified by the source proof."""

    payload = json.loads(source_proof_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), "Source proof must be a JSON object"
    assert str(payload.get("run_id") or "") == run_id
    assert payload.get("same_run_bilingual_pdf_verified") is True
    assert payload.get("same_run_bilingual_assessment_rerun") is False
    assert payload.get("localized_pdf_artifact_hash_headers_verified") is True
    assert payload.get("terminal_state_unchanged_after_localized_reads") is True
    prefix = "spanish" if report_language == "es-MX" else "english"
    expected_sha = str(payload.get(f"{prefix}_pdf_sha256") or "").lower()
    assert re.fullmatch(r"[0-9a-f]{64}", expected_sha), expected_sha
    artifact_name = Path(str(payload.get(f"{prefix}_pdf_path") or "")).name
    assert artifact_name, f"Source {report_language} PDF path is missing"
    artifact_path = source_proof_path.parent / artifact_name
    pdf_bytes = artifact_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF"), f"Source {report_language} artifact was not a PDF"
    assert len(pdf_bytes) > 1_000, f"Source {report_language} PDF was unexpectedly small"
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    assert observed_sha == expected_sha, {
        "source_pdf_sha256": observed_sha,
        "source_proof_pdf_sha256": expected_sha,
    }
    canonical_truth_sha256 = str(
        payload.get("canonical_truth_sha256") or ""
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{64}", canonical_truth_sha256)
    return {
        "pdf_bytes": pdf_bytes,
        "pdf_sha256": observed_sha,
        "content_disposition": "",
        "response_run_id": run_id,
        "artifact_hash_header_verified": True,
        "canonical_truth_sha256": canonical_truth_sha256,
        "accepted_pdf_sha256": "",
        "accepted_edition_digest_verified": False,
        "response_report_language": report_language,
        "assessment_rerun": False,
        "localized_draft_identity_verified": True,
        "evidence_source": "exact-sha-spanish-source-proof",
    }


def install_ui_pdf_download_proof(
    recovery: Any,
    *,
    source_proof_path: Path | None = None,
) -> None:
    current = recovery._verify_manifest_and_pdf
    if getattr(current, "_nico_ui_pdf_download_proof_v1", False):
        return

    def verify_manifest_and_pdf(page: Any, frontend_origin: str, run_id: str) -> dict[str, Any]:
        direct = dict(current(page, frontend_origin, run_id))
        actions = page.locator(REPORT_ACTIONS_SELECTOR).first
        actions.wait_for(state="visible", timeout=120_000)
        report_language = _active_report_language(page)
        requested_language_attr = str(
            actions.get_attribute("data-requested-report-language") or ""
        ).strip()
        assert requested_language_attr == report_language, {
            "active_report_language": report_language,
            "requested_report_language_attribute": requested_language_attr,
        }
        action_records = list(
            actions.locator("button[data-assessment-pdf-kind]").evaluate_all(
                r"""buttons => buttons.map(button => {
                  const rect = button.getBoundingClientRect();
                  const style = getComputedStyle(button);
                  return {
                    kind: String(button.getAttribute('data-assessment-pdf-kind') || ''),
                    report_language: String(button.getAttribute('data-report-language') || ''),
                    label: String(button.textContent || '').replace(/\s+/g, ' ').trim(),
                    visible: rect.width > 0 && rect.height > 0
                      && style.display !== 'none' && style.visibility !== 'hidden',
                    enabled: !button.disabled,
                  };
                })"""
            )
            or []
        )
        selected = _choose_pdf_action(action_records, report_language)
        action_kind = str(selected["kind"])
        action_report_language = str(selected["report_language"])
        contract = _pdf_action_contract(
            run_id,
            action_report_language,
            action_kind,
        )
        artifact_url_suffix = contract["path"]
        expected_filename = contract["fallback_filename"]
        pdf_button = actions.locator(
            f'button[data-assessment-pdf-kind="{action_kind}"]'
            f'[data-report-language="{action_report_language}"]'
        ).first
        assert pdf_button.is_visible(), "Selected PDF action was not visible"
        assert pdf_button.is_enabled(), "Selected PDF action was not enabled"
        expected_origin = urlparse(frontend_origin)

        # Capture both UI implementations without changing their dispatch semantics:
        # the pending-review compatibility bridge creates an exact-route anchor, while
        # the accepted-edition React action validates bytes first and creates a blob URL.
        page.evaluate(
            """() => {
              window.__nicoReviewPdfDownloadAttribute = '';
              window.__nicoReviewPdfDownloadHref = '';
              window.__nicoReviewPdfDownloadRel = '';
              window.__nicoReviewPdfDownloadTarget = '';
              window.__nicoReviewPdfAnchorClickCount = 0;
              window.__nicoAcceptancePdfAnchor = null;
              window.__nicoReviewPdfObserver?.disconnect?.();
              if (window.__nicoAcceptancePdfClickCapture) {
                document.removeEventListener(
                  "click", window.__nicoAcceptancePdfClickCapture, true
                );
              }
              const capture = link => {
                if (!(link instanceof HTMLAnchorElement)) return;
                const value = {
                  download: link.getAttribute('download') || '',
                  href: link.getAttribute('href') || '',
                  rel: link.getAttribute('rel') || '',
                  target: link.getAttribute('target') || '',
                  marked_review_download:
                    link.getAttribute('data-nico-review-pdf-download') === 'true',
                };
                window.__nicoAcceptancePdfAnchor = value;
                window.__nicoReviewPdfDownloadAttribute = value.download;
                window.__nicoReviewPdfDownloadHref = value.href;
                window.__nicoReviewPdfDownloadRel = value.rel;
                window.__nicoReviewPdfDownloadTarget = value.target;
              };
              const captureAnchorClick = event => {
                const target = event.target instanceof Element ? event.target : null;
                const link = target?.closest?.('a');
                if (!(link instanceof HTMLAnchorElement)) return;
                if (link.getAttribute('data-nico-review-pdf-download') !== 'true') return;
                window.__nicoReviewPdfAnchorClickCount = Number(
                  window.__nicoReviewPdfAnchorClickCount || 0
                ) + 1;
                capture(link);
              };
              window.__nicoAcceptancePdfClickCapture = captureAnchorClick;
              document.addEventListener("click", captureAnchorClick, true);
              const observer = new MutationObserver(records => {
                for (const record of records) {
                  for (const node of record.addedNodes) {
                    if (!(node instanceof Element)) continue;
                    const link = node.matches('[data-nico-review-pdf-download="true"]')
                      ? node
                      : node.querySelector?.('[data-nico-review-pdf-download="true"]');
                    if (link) {
                      capture(link);
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
                "() => Boolean(window.__nicoAcceptancePdfAnchor?.href)",
                timeout=120_000,
            )
            # Keep the passive listener alive briefly so a fallback or accidental
            # second anchor activation cannot escape the exact-count assertion.
            page.wait_for_timeout(750)
        finally:
            page.evaluate(
                """() => {
                  window.__nicoReviewPdfObserver?.disconnect?.();
                  if (window.__nicoAcceptancePdfClickCapture) {
                    document.removeEventListener(
                      "click", window.__nicoAcceptancePdfClickCapture, true
                    );
                    window.__nicoAcceptancePdfClickCapture = null;
                  }
                }"""
            )

        # Browser-managed downloads are not exposed consistently as Playwright
        # request events (Chromium can complete the same-origin request without one).
        # Count the exact marked anchor activation instead, without replacing native
        # browser behavior. The captured endpoint is fetched and validated below.
        anchor_click_count = int(
            page.evaluate("() => Number(window.__nicoReviewPdfAnchorClickCount || 0)")
        )
        assert anchor_click_count == 1, {
            "expected_user_gesture_anchor_click_count": 1,
            "observed_user_gesture_anchor_click_count": anchor_click_count,
        }

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
        requested_url = urljoin(
            frontend_origin.rstrip("/") + "/",
            artifact_url_suffix,
        )
        parsed_requested = urlparse(requested_url)
        assert parsed_requested.scheme == expected_origin.scheme, requested_url
        assert parsed_requested.netloc == expected_origin.netloc, requested_url
        if action_kind == DRAFT_PDF_KIND:
            parsed_anchor = urlparse(urljoin(frontend_origin.rstrip("/") + "/", requested_href))
            assert unquote(parsed_anchor.path) == artifact_url_suffix, (
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
        else:
            assert requested_href.startswith("blob:"), requested_href
            assert requested_filename.lower().endswith(".pdf"), requested_filename
            assert run_id in requested_filename, requested_filename
        assert "FINAL-PENDING-APPROVAL" not in requested_filename, requested_filename

        if action_kind == DRAFT_PDF_KIND:
            assert source_proof_path is not None, "Exact-SHA source proof is required"
            captured = _load_source_bound_pdf(
                source_proof_path,
                run_id,
                action_report_language,
            )
        else:
            captured = _fetch_captured_pdf(
                page,
                requested_url,
                run_id,
                action_kind=action_kind,
                report_language=action_report_language,
            )
        pdf_bytes = captured["pdf_bytes"]
        observed_sha = str(captured["pdf_sha256"])
        content_disposition = str(captured["content_disposition"])
        response_filename = ""
        if content_disposition:
            if action_kind == DRAFT_PDF_KIND:
                response_filename = _validate_response_filename(
                    content_disposition,
                    run_id,
                    action_report_language,
                )
            else:
                response_filename = _content_disposition_filename(content_disposition)
                assert response_filename.lower().endswith(".pdf"), response_filename
                assert run_id in response_filename, response_filename
                assert requested_filename == response_filename, {
                    "requested_filename": requested_filename,
                    "response_filename": response_filename,
                }
        direct_sha = str(direct.get("pdf_sha256") or "").lower()
        direct_canonical_truth_sha256 = str(
            direct.get("canonical_truth_sha256") or ""
        ).lower()
        assert captured["canonical_truth_sha256"] == direct_canonical_truth_sha256
        assert direct.get("pdf_run_identity_verified") is True, direct
        assert direct.get("pdf_signature_verified") is True, direct
        if action_kind == ACCEPTED_PDF_KIND:
            assert captured["accepted_pdf_sha256"] == direct_sha
        page.wait_for_timeout(250)
        page.bring_to_front()
        page.wait_for_function(
            "() => document.visibilityState === 'visible' && document.hidden === false",
            timeout=5_000,
        )
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
            "ui_review_pdf_report_language": action_report_language,
            "ui_review_pdf_requested_report_language": report_language,
            "ui_review_pdf_action_kind": action_kind,
            "ui_review_pdf_action_lifecycle": contract["lifecycle"],
            "ui_review_pdf_action_set": action_records,
            "ui_review_pdf_network_path": artifact_url_suffix,
            "ui_review_pdf_artifact_evidence_source": captured.get(
                "evidence_source", "live-exact-artifact-response"
            ),
            "ui_review_pdf_source_artifact_reused": action_kind == DRAFT_PDF_KIND,
            "ui_review_pdf_user_gesture_anchor_click_count": anchor_click_count,
            "ui_review_pdf_anchor_click_observation_verified": True,
            "ui_review_pdf_single_dispatch_verified": True,
            "ui_review_pdf_exact_run_filename_verified": True,
            "ui_review_pdf_exact_run_href_verified": True,
            "ui_review_pdf_exact_run_response_verified": True,
            "ui_review_pdf_response_sha256_verified": True,
            "ui_review_pdf_artifact_hash_header_verified": captured[
                "artifact_hash_header_verified"
            ],
            "ui_review_pdf_canonical_truth_sha256": captured[
                "canonical_truth_sha256"
            ],
            "ui_review_pdf_canonical_truth_digest_verified": True,
            "ui_review_pdf_matches_preverified_artifact": bool(direct_sha and observed_sha == direct_sha),
            "ui_review_pdf_proxy_read_class": contract["read_class"],
            "ui_review_pdf_signature_verified": True,
            "ui_review_pdf_artifact_status_cleared": True,
            "ui_review_pdf_original_user_gesture_preserved": True,
            "ui_review_pdf_lifecycle_filename_verified": True,
            "ui_review_pdf_lifecycle_contract_verified": True,
            "ui_review_pdf_accepted_edition_digest_verified": captured[
                "accepted_edition_digest_verified"
            ],
            "ui_review_pdf_localized_draft_identity_verified": captured[
                "localized_draft_identity_verified"
            ],
            "ui_review_pdf_target_contract": (
                "blank-noopener-noreferrer"
                if action_kind == DRAFT_PDF_KIND
                else "same-page-validated-blob-download"
            ),
            "ui_review_pdf_target_blank_verified": action_kind == DRAFT_PDF_KIND,
            "ui_review_pdf_noopener_noreferrer_verified": action_kind == DRAFT_PDF_KIND,
            "ui_review_pdf_original_assessment_page_preserved": True,
            "ui_review_pdf_original_page_visible_after_action": True,
            "ui_review_pdf_proof_version": VERSION,
        }

    setattr(verify_manifest_and_pdf, "_nico_ui_pdf_download_proof_v1", True)
    setattr(verify_manifest_and_pdf, "_nico_previous", current)
    recovery._verify_manifest_and_pdf = verify_manifest_and_pdf


__all__ = [
    "ACCEPTED_PDF_KIND",
    "DRAFT_PDF_KIND",
    "VERSION",
    "install_ui_pdf_download_proof",
]
