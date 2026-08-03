"use client";

import {useEffect, useRef} from "react";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const REVIEW_PDF_LABEL = /(?:download\s+review\s+pdf|descargar\s+pdf\s+para\s+revisi[oó]n)/i;
const RUN_ID_QUERY = "run_id";
const REENTRY_GUARD_MS = 1_500;

function exactRunPdfHref(runId: string): string {
  return `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/pdf`;
}

function startExactRunDownload(runId: string): void {
  const link = document.createElement("a");
  link.href = exactRunPdfHref(runId);
  link.download = `nico-comprehensive-${runId}-FINAL-PENDING-APPROVAL.pdf`;
  link.rel = "noopener";
  link.hidden = true;
  link.setAttribute("data-nico-review-pdf-download", "true");
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => link.remove(), 1_000);
}

/**
 * Keep the exact-run PDF request inside the original mobile user gesture.
 *
 * The assessment result intentionally carries only a bounded terminal manifest.
 * Waiting for an asynchronous in-memory response conversion before clicking a
 * synthetic link loses Safari's download gesture and can leave the React action
 * waiting indefinitely while a streamed proxy response stalls. The backend
 * artifact route already validates exact run identity, strict base64, the PDF
 * signature, and SHA-256. This bridge therefore hands the same-origin download
 * directly to the browser.
 */
export default function AssessmentReviewPdfDownload() {
  const guardedUntil = useRef(0);

  useEffect(() => {
    function handleReviewPdfClick(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      if (!button.closest(REPORT_ACTIONS_SELECTOR)) return;
      if (!REVIEW_PDF_LABEL.test(String(button.textContent || "").trim())) return;

      const runId = new URL(window.location.href).searchParams.get(RUN_ID_QUERY)?.trim() || "";
      if (!runId.startsWith("comprun_")) return;

      const now = Date.now();
      if (now < guardedUntil.current) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        return;
      }
      guardedUntil.current = now + REENTRY_GUARD_MS;

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      startExactRunDownload(runId);
    }

    document.addEventListener("click", handleReviewPdfClick, true);
    return () => document.removeEventListener("click", handleReviewPdfClick, true);
  }, []);

  return null;
}

export {exactRunPdfHref};
