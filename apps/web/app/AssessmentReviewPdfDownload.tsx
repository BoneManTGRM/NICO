"use client";

import {useEffect, useRef} from "react";
import {reportLanguageForRequest} from "./assessment/assessmentLocale";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const REVIEW_PDF_LABEL = /(?:download\s+review\s+pdf|descargar\s+pdf\s+para\s+revisi[oó]n)/i;
const REVIEW_PDF_KIND = "localized-draft-pending-approval";
const RUN_ID_QUERY = "run_id";
const REENTRY_GUARD_MS = 1_500;
const STATUS_ATTR = "data-nico-review-pdf-action-status";

type ReportLanguage = "en" | "es-MX";

function activeReportLanguage(): ReportLanguage {
  const current = new URL(window.location.href);
  const pathname = current.pathname.toLowerCase();
  const queryLocale = current.searchParams.get("lang")?.toLowerCase();
  const uiLocale = (
    pathname === "/es" ||
    pathname.startsWith("/es/") ||
    pathname === "/es-mx" ||
    pathname.startsWith("/es-mx/") ||
    queryLocale === "es-mx" ||
    queryLocale === "es"
  ) || document.documentElement.lang.toLowerCase().startsWith("es")
    ? "es-MX"
    : "en";
  return reportLanguageForRequest(uiLocale);
}

function spanishUi(): boolean {
  const current = new URL(window.location.href);
  const pathname = current.pathname.toLowerCase();
  const queryLocale = current.searchParams.get("lang")?.toLowerCase();
  return pathname === "/es"
    || pathname.startsWith("/es/")
    || pathname === "/es-mx"
    || pathname.startsWith("/es-mx/")
    || queryLocale === "es-mx"
    || queryLocale === "es"
    || document.documentElement.lang.toLowerCase().startsWith("es");
}

function visibleRunId(actions: Element | null = null): string {
  const fromActions = String(actions?.getAttribute("data-run-id") || "").trim();
  if (fromActions.startsWith("comprun_")) return fromActions;

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

function showStatus(container: Element | null, message: string, failure = false): void {
  if (!container) return;
  let status = container.querySelector<HTMLElement>(`[${STATUS_ATTR}]`);
  if (!status) {
    status = document.createElement("span");
    status.setAttribute(STATUS_ATTR, "true");
    status.className = "muted";
    status.setAttribute("aria-live", "polite");
    container.appendChild(status);
  }
  status.setAttribute("role", failure ? "alert" : "status");
  status.textContent = message;
  window.setTimeout(() => {
    if (status?.isConnected && status.textContent === message) status.remove();
  }, failure ? 8_000 : 5_000);
}

function startExactRunDownload(runId: string, reportLanguage: ReportLanguage): void {
  const href = exactRunPdfHref(runId, reportLanguage);
  const link = document.createElement("a");
  link.href = href;
  link.download = `nico-comprehensive-${runId}-${reportLanguage}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.style.position = "fixed";
  link.style.left = "-9999px";
  link.setAttribute("data-nico-review-pdf-download", "true");
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => link.remove(), 1_000);
}

/**
 * Keep the exact-run PDF request inside the original mobile/desktop user gesture.
 * This compatibility bridge takes ownership only when the terminal report is ready and
 * an exact Comprehensive run ID is bound to the canonical action container. URL and
 * visible-text discovery remain compatibility fallback only. During a React rerender or
 * temporary run-ID projection gap it leaves the click untouched so AssessmentWorkspace
 * remains the safe fallback rather than turning an enabled button into a dead control.
 */
export default function AssessmentReviewPdfDownload() {
  const guardedUntil = useRef(0);

  useEffect(() => {
    function handleReviewPdfClick(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const actions = button.closest(REPORT_ACTIONS_SELECTOR);
      if (!actions) return;
      // An accepted-edition action must remain with AssessmentWorkspace, which
      // verifies the streamed bytes against the exact approved PDF digest. This
      // localization bridge owns only explicitly pending-review draft actions.
      if (button.getAttribute("data-assessment-pdf-kind") !== REVIEW_PDF_KIND) return;
      if (!REVIEW_PDF_LABEL.test(String(button.textContent || "").trim())) return;

      // Do not cancel the native React click until this bridge can prove it owns the
      // exact terminal artifact action.
      if (actions.getAttribute("data-assessment-report-ready") !== "true") return;
      const runId = visibleRunId(actions);
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
      showStatus(
        actions,
        spanishUi()
          ? "PDF solicitado. Revisa la nueva pestaña o tus descargas."
          : "PDF requested. Check the new tab or your downloads.",
      );
    }

    document.addEventListener("click", handleReviewPdfClick, true);
    return () => document.removeEventListener("click", handleReviewPdfClick, true);
  }, []);

  return null;
}

export {activeReportLanguage, exactRunPdfHref, spanishUi, startExactRunDownload, visibleRunId};
