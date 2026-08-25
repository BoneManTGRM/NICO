"use client";

import {useEffect, useRef} from "react";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const REVIEW_PDF_LABEL = /(?:download\s+(?:review|approved)\s+pdf|descargar[^\n]*pdf)/i;
const COPY_MARKDOWN_LABEL = /(?:copy\s+markdown|copiar\s+markdown)/i;
const RUN_ID_QUERY = "run_id";
const REENTRY_GUARD_MS = 1_500;
const STATUS_ATTR = "data-nico-artifact-action-status";

type ReportLanguage = "en" | "es-MX";

type MarkdownEntry = {
  runId: string;
  markdown: string;
  promise: Promise<string> | null;
};

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

function exactRunMarkdownHref(runId: string): string {
  return `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/markdown`;
}

function actionStatus(container: Element | null, message: string, failure = false): void {
  if (!container) return;
  let status = container.querySelector<HTMLElement>(`[${STATUS_ATTR}]`);
  if (!status) {
    status = document.createElement("span");
    status.setAttribute(STATUS_ATTR, "true");
    status.setAttribute("role", failure ? "alert" : "status");
    status.className = "muted";
    container.appendChild(status);
  }
  status.setAttribute("role", failure ? "alert" : "status");
  status.textContent = message;
  window.setTimeout(() => {
    if (status?.isConnected && status.textContent === message) status.remove();
  }, failure ? 8_000 : 2_500);
}

function startExactRunDownload(runId: string, reportLanguage: ReportLanguage): void {
  const href = exactRunPdfHref(runId, reportLanguage);
  // Execute browser navigation directly inside the original trusted click. Using a
  // synthetic hidden anchor alone proved insufficient on some desktop/WebKit paths:
  // the server returned 200 while the user saw no visible result. A real browsing
  // context is deterministic; if popup policy rejects it, same-tab navigation is the
  // explicit fallback rather than a silent no-op.
  const opened = window.open(href, "_blank", "noopener,noreferrer");
  if (!opened) window.location.assign(href);
}

async function writeClipboard(text: string): Promise<boolean> {
  if (!text.trim()) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Continue to the bounded legacy fallback. This remains useful for WebKit and
    // hardened desktop browser profiles where Clipboard API permission is denied.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  textarea.remove();
  return copied;
}

async function fetchMarkdown(entry: MarkdownEntry): Promise<string> {
  if (entry.markdown) return entry.markdown;
  if (entry.promise) return entry.promise;
  entry.promise = (async () => {
    const response = await fetch(exactRunMarkdownHref(entry.runId), {
      method: "GET",
      cache: "no-store",
      headers: {Accept: "text/markdown"},
    });
    if (!response.ok) throw new Error(`markdown_http_${response.status}`);
    const markdown = await response.text();
    if (!markdown.trim()) throw new Error("markdown_empty");
    entry.markdown = markdown;
    return markdown;
  })();
  try {
    return await entry.promise;
  } finally {
    entry.promise = null;
  }
}

/**
 * Make terminal artifact controls deterministic across Chromium and WebKit.
 *
 * - The review PDF uses the existing same-run localized artifact route directly in
 *   the trusted click, so a successful server response always yields visible browser
 *   navigation/download behavior.
 * - Markdown is prefetched as soon as terminal actions mount, preserving the user
 *   activation for the actual clipboard write. The click path retains a bounded fetch
 *   fallback and exposes visible success/failure instead of silently doing nothing.
 */
export default function AssessmentReviewPdfDownload() {
  const guardedUntil = useRef(0);
  const markdownCache = useRef<MarkdownEntry | null>(null);

  useEffect(() => {
    function entryForVisibleRun(): MarkdownEntry | null {
      const runId = visibleRunId();
      if (!runId) return null;
      if (!markdownCache.current || markdownCache.current.runId !== runId) {
        markdownCache.current = {runId, markdown: "", promise: null};
      }
      return markdownCache.current;
    }

    function prefetchVisibleMarkdown(): void {
      const actions = document.querySelector(REPORT_ACTIONS_SELECTOR);
      if (!actions) return;
      const entry = entryForVisibleRun();
      if (!entry || entry.markdown || entry.promise) return;
      void fetchMarkdown(entry).catch(() => {
        // Prefetch failure is not terminal. The explicit click retries and surfaces a
        // visible error if the exact-run artifact is genuinely unavailable.
      });
    }

    async function handleArtifactClick(event: MouseEvent): Promise<void> {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const actions = button.closest(REPORT_ACTIONS_SELECTOR);
      if (!actions) return;
      const label = String(button.textContent || "").trim();
      const pdfAction = REVIEW_PDF_LABEL.test(label);
      const markdownAction = COPY_MARKDOWN_LABEL.test(label);
      if (!pdfAction && !markdownAction) return;

      const entry = entryForVisibleRun();
      if (!entry) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        actionStatus(actions, activeReportLanguage() === "es-MX" ? "No se pudo determinar la ejecución exacta." : "The exact run could not be determined.", true);
        return;
      }

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

      if (pdfAction) {
        actionStatus(actions, activeReportLanguage() === "es-MX" ? "Abriendo el PDF exacto…" : "Opening exact-run PDF…");
        startExactRunDownload(entry.runId, activeReportLanguage());
        return;
      }

      const spanish = activeReportLanguage() === "es-MX";
      try {
        if (!entry.markdown) {
          actionStatus(actions, spanish ? "Preparando Markdown…" : "Preparing Markdown…");
        }
        const markdown = entry.markdown || await fetchMarkdown(entry);
        const copied = await writeClipboard(markdown);
        if (!copied) throw new Error("clipboard_write_failed");
        actionStatus(actions, spanish ? "Markdown copiado." : "Markdown copied.");
      } catch {
        actionStatus(
          actions,
          spanish
            ? "No se pudo copiar Markdown. Vuelve a intentarlo o abre el informe para revisión."
            : "Markdown could not be copied. Try again or open the review report.",
          true,
        );
      }
    }

    document.addEventListener("click", handleArtifactClick, true);
    const observer = new MutationObserver(() => window.requestAnimationFrame(prefetchVisibleMarkdown));
    observer.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["disabled", "data-assessment-report-ready"]});
    prefetchVisibleMarkdown();

    return () => {
      document.removeEventListener("click", handleArtifactClick, true);
      observer.disconnect();
    };
  }, []);

  return null;
}

export {activeReportLanguage, exactRunMarkdownHref, exactRunPdfHref, visibleRunId, writeClipboard};
