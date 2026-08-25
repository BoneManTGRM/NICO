"use client";

import {useEffect, useRef} from "react";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const REVIEW_PDF_LABEL = /(?:download\s+(?:review|approved)\s+pdf|descargar[^\n]*pdf)/i;
const RUN_ID_QUERY = "run_id";
const REENTRY_GUARD_MS = 1_500;

type ReportLanguage = "en" | "es-MX";

function activeReportLanguage(): ReportLanguage {
  const current = new URL(window.location.href);
  const requested = String(
    current.searchParams.get("report_language") || current.searchParams.get("lang") || "",
  ).toLowerCase();
  if (requested === "es-mx" || requested === "es_mx") return "es-MX";
  if (requested === "en") return "en";

  const pathname = current.pathname.toLowerCase();
  if (
    pathname === "/es" ||
    pathname.startsWith("/es/") ||
    pathname === "/es-mx" ||
    pathname.startsWith("/es-mx/")
  ) {
    return "es-MX";
  }

  return document.documentElement.lang.toLowerCase().startsWith("es") ? "es-MX" : "en";
}

function visibleRunId(): string {
  const fromQuery = new URL(window.location.href).searchParams.get(RUN_ID_QUERY)?.trim() || "";
  if (fromQuery.startsWith("comprun_")) return fromQuery;

  for (const selector of [
    ".nico-identifier-value code[title]",
    "[data-mobile-compact-terminal='true'] code[title]",
    "[data-assessment-run-state='true'] h2[title]",
  ]) {
    for (const node of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
      const value = String(node.getAttribute("title") || "").trim();
      if (value.startsWith("comprun_")) return value;
    }
  }
  return "";
}

function exactRunPdfHref(runId: string, reportLanguage: ReportLanguage = "en"): string {
  return `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/localized-report/${encodeURIComponent(reportLanguage)}/pdf`;
}

function startExactRunDownload(runId: string, reportLanguage: ReportLanguage): void {
  const href = exactRunPdfHref(runId, reportLanguage);
  const link = document.createElement("a");
  link.href = href;
  link.download = `nico-comprehensive-${runId}-${reportLanguage}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.hidden = true;
  link.setAttribute("data-nico-review-pdf-download", "true");
  document.body.appendChild(link);

  // Prefer an explicit browsing context so desktop Chromium/WebKit visibly opens the
  // exact-run report instead of silently consuming a successful streamed response.
  // If popup policy blocks that action, the original user gesture still owns the
  // prepared same-origin download anchor as a deterministic fallback.
  const opened = window.open(href, "_blank", "noopener,noreferrer");
  if (!opened) {
    link.click();
  }
  window.setTimeout(() => link.remove(), 1_000);
}

/**
 * Keep the exact-run PDF request inside the original mobile/desktop user gesture.
 *
 * The assessment result intentionally carries only a bounded terminal manifest. The
 * backend localized artifact route validates exact run identity, canonical truth,
 * strict base64, the PDF signature, and SHA-256. No asynchronous artifact conversion
 * happens before browser navigation, so WebKit/Chromium keep the trusted gesture.
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

      const runId = visibleRunId();
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
      startExactRunDownload(runId, activeReportLanguage());
    }

    document.addEventListener("click", handleReviewPdfClick, true);
    return () => document.removeEventListener("click", handleReviewPdfClick, true);
  }, []);

  return null;
}

export {activeReportLanguage, exactRunPdfHref, visibleRunId};
