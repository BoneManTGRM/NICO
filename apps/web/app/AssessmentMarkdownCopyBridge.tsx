"use client";

import {useEffect, useRef} from "react";
import {reportLanguageForRequest} from "./assessment/assessmentLocale";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const COPY_MARKDOWN_LABEL = /(?:copy\s+markdown|copiar\s+markdown)/i;
const STATUS_ATTR = "data-nico-markdown-action-status";

type CacheEntry = {
  runId: string;
  commitSha: string;
  reportLanguage: ReportLanguage;
  markdown: string;
  promise: Promise<string> | null;
};

type ReportLanguage = "en" | "es-MX";

function spanish(): boolean {
  const path = window.location.pathname.toLowerCase();
  const queryLocale = new URL(window.location.href).searchParams.get("lang")?.toLowerCase();
  return path === "/es-mx"
    || path.startsWith("/es-mx/")
    || path.startsWith("/es/")
    || queryLocale === "es-mx"
    || queryLocale === "es"
    || document.documentElement.lang.toLowerCase().startsWith("es");
}

function activeReportLanguage(): ReportLanguage {
  return reportLanguageForRequest(spanish() ? "es-MX" : "en");
}

function visibleRunId(actions: Element | null = null): string {
  const fromActions = String(actions?.getAttribute("data-run-id") || "").trim();
  if (fromActions.startsWith("comprun_")) return fromActions;

  const fromQuery = new URL(window.location.href).searchParams.get("run_id")?.trim() || "";
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

function visibleCommitSha(actions: Element | null = null): string {
  return String(actions?.getAttribute("data-commit-sha") || "").trim();
}

function markdownHref(runId: string, reportLanguage: ReportLanguage): string {
  return `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/localized-report/${encodeURIComponent(reportLanguage)}`;
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
  }, failure ? 8_000 : 3_500);
}

async function copyText(text: string): Promise<boolean> {
  if (!text.trim()) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Keep WebKit and hardened desktop profiles usable when Clipboard API access is denied.
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

async function loadMarkdown(entry: CacheEntry): Promise<string> {
  if (entry.markdown) return entry.markdown;
  if (entry.promise) return entry.promise;

  entry.promise = (async () => {
    const response = await fetch(markdownHref(entry.runId, entry.reportLanguage), {
      method: "GET",
      cache: "no-store",
      headers: {Accept: "application/json"},
    });
    if (!response.ok) throw new Error(`markdown_http_${response.status}`);
    const payload = await response.json() as {
      run_id?: unknown;
      commit_sha?: unknown;
      report_language?: unknown;
      assessment_rerun?: unknown;
      report?: {markdown?: unknown};
    };
    if (String(payload.run_id || "") !== entry.runId) throw new Error("markdown_run_identity_mismatch");
    if (entry.commitSha && String(payload.commit_sha || "") !== entry.commitSha) {
      throw new Error("markdown_commit_identity_mismatch");
    }
    if (String(payload.report_language || "") !== entry.reportLanguage) {
      throw new Error("markdown_report_language_mismatch");
    }
    if (payload.assessment_rerun !== false) throw new Error("markdown_assessment_rerun_not_proven_false");
    const markdown = String(payload.report?.markdown || "");
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

function enabledCopyButton(actions: Element): HTMLButtonElement | null {
  for (const button of Array.from(actions.querySelectorAll<HTMLButtonElement>("button"))) {
    if (COPY_MARKDOWN_LABEL.test(String(button.textContent || "").trim())) {
      return button.disabled ? null : button;
    }
  }
  return null;
}

/**
 * Compatibility helper for terminal Copy Markdown across desktop Chromium and WebKit.
 * It may take ownership of a click only after report readiness and an exact run identity
 * are both established. The canonical action container's data-run-id is authoritative;
 * URL/visible-text discovery remains compatibility fallback only. If exact binding is
 * temporarily absent during a React rerender, the native AssessmentWorkspace onClick
 * remains available instead of presenting a dead button.
 */
export default function AssessmentMarkdownCopyBridge() {
  const cache = useRef<CacheEntry | null>(null);
  const guardedUntil = useRef(0);

  useEffect(() => {
    function entryForVisibleRun(actions: Element | null = null): CacheEntry | null {
      const runId = visibleRunId(actions);
      if (!runId) return null;
      const commitSha = visibleCommitSha(actions);
      const reportLanguage = activeReportLanguage();
      if (
        !cache.current
        || cache.current.runId !== runId
        || cache.current.commitSha !== commitSha
        || cache.current.reportLanguage !== reportLanguage
      ) {
        cache.current = {runId, commitSha, reportLanguage, markdown: "", promise: null};
      }
      return cache.current;
    }

    async function handleCopyMarkdownClick(event: MouseEvent): Promise<void> {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const actions = button.closest(REPORT_ACTIONS_SELECTOR);
      if (!actions || !COPY_MARKDOWN_LABEL.test(String(button.textContent || "").trim())) return;

      // Never swallow a click unless this compatibility bridge has authoritative
      // terminal report state and an exact run to act on. The native React handler is
      // the safe fallback during rerenders or temporary projection gaps.
      if (actions.getAttribute("data-assessment-report-ready") !== "true") return;
      const entry = entryForVisibleRun(actions);
      if (!entry) return;

      const now = Date.now();
      if (now < guardedUntil.current) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        return;
      }
      guardedUntil.current = now + 1_200;

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      if (!entry.markdown) {
        showStatus(
          actions,
          spanish()
            ? "Preparando Markdown. Cuando indique que está listo, pulsa Copiar Markdown otra vez."
            : "Preparing Markdown. When it is ready, click Copy Markdown again.",
        );
        void loadMarkdown(entry)
          .then(() => {
            guardedUntil.current = 0;
            showStatus(
              actions,
              spanish() ? "Markdown listo. Pulsa Copiar Markdown." : "Markdown ready. Click Copy Markdown.",
            );
          })
          .catch(() => {
            guardedUntil.current = 0;
            showStatus(
              actions,
              spanish()
                ? "No se pudo preparar Markdown. Vuelve a intentarlo."
                : "Markdown could not be prepared. Try again.",
              true,
            );
          });
        return;
      }

      try {
        if (!await copyText(entry.markdown)) throw new Error("clipboard_write_failed");
        showStatus(actions, spanish() ? "Markdown copiado." : "Markdown copied.");
      } catch {
        showStatus(
          actions,
          spanish()
            ? "No se pudo copiar Markdown. Vuelve a intentarlo."
            : "Markdown could not be copied. Try again.",
          true,
        );
      }
    }

    document.addEventListener("click", handleCopyMarkdownClick, true);

    return () => {
      document.removeEventListener("click", handleCopyMarkdownClick, true);
    };
  }, []);

  return null;
}

export {activeReportLanguage, copyText, enabledCopyButton, markdownHref, visibleCommitSha, visibleRunId};
