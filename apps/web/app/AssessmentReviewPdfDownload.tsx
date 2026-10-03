"use client";

import {useEffect, useRef} from "react";
import {reportLanguageForRequest} from "./assessment/assessmentLocale";

const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const REVIEW_PDF_LABEL = /(?:download\s+review\s+pdf|descargar\s+pdf\s+para\s+revisi[oó]n)/i;
const REVIEW_PDF_KIND = "localized-draft-pending-approval";
const RUN_ID_QUERY = "run_id";
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

type DownloadBinding = {
  commitSha: string;
  canonicalTruthSha256?: string;
  signal?: AbortSignal;
};

const inFlight = new Map<string, Promise<void>>();
const DOWNLOAD_TIMEOUT_MS = 255_000;

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
  // Keep progress and errors visible until the next action or page navigation.
  status.textContent = message;
}

function downloadError(response: Response): Error {
  if (response.status === 401 || response.status === 403) {
    return new Error(spanishUi()
      ? "Inicia sesión en NICO y vuelve a descargar este PDF."
      : "Sign in to NICO, then retry this PDF download.");
  }
  if (response.status === 504 || response.status === 408) {
    return new Error(spanishUi()
      ? "La descarga del PDF excedió el tiempo límite. Vuelve a intentarlo; no inicies otra evaluación."
      : "The PDF download timed out. Retry this download; do not start another assessment.");
  }
  const requestId = String(response.headers.get("x-request-id") || "");
  const reference = /^[a-zA-Z0-9_-]{1,80}$/.test(requestId)
    ? ` (${requestId})` : "";
  return new Error((spanishUi()
    ? "No se pudo descargar el PDF. Vuelve a intentarlo."
    : "The PDF could not be downloaded. Retry this download.") + reference);
}

function integrityError(): Error {
  return new Error(spanishUi()
    ? "El PDF no coincide con esta evaluación y su idioma. Recupera el estado de esta evaluación antes de volver a intentarlo."
    : "The PDF does not match this assessment and language. Recover this assessment's status before retrying.");
}

async function retrieveExactRunPdf(
  runId: string,
  reportLanguage: ReportLanguage,
  binding: DownloadBinding,
): Promise<void> {
  const signal = binding.signal || AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS);
  const response = await fetch(exactRunPdfHref(runId, reportLanguage), {
    method: "GET", cache: "no-store", credentials: "same-origin",
    headers: {Accept: "application/pdf"}, signal,
  });
  if (!response.ok) throw downloadError(response);
  const header = (name: string) => String(response.headers.get(name) || "").trim();
  const declaredSha = header("x-nico-pdf-sha256").toLowerCase();
  const truthSha = header("x-nico-canonical-truth-sha256").toLowerCase();
  if (
    !/^[0-9a-f]{40}$/.test(binding.commitSha)
    || header("x-nico-run-id") !== runId
    || header("x-nico-commit-sha") !== binding.commitSha
    || header("x-nico-report-language") !== reportLanguage
    || header("x-nico-assessment-rerun") !== "false"
    || header("x-nico-approval-status") !== "pending_human_approval"
    || header("x-nico-delivery-status") !== "blocked_pending_human_approval"
    || header("x-nico-client-delivery-allowed") !== "false"
    || header("x-nico-accepted-pdf-sha256") !== ""
    || !/^[0-9a-f]{64}$/.test(declaredSha)
    || header("x-nico-artifact-sha256").toLowerCase() !== declaredSha
    || !/^[0-9a-f]{64}$/.test(truthSha)
    || (binding.canonicalTruthSha256 && truthSha !== binding.canonicalTruthSha256.toLowerCase())
  ) throw integrityError();

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (signal.aborted) throw signal.reason;
  if (bytes.length < 5 || String.fromCharCode(...bytes.slice(0, 5)) !== "%PDF-") {
    throw integrityError();
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const observedSha = Array.from(digest, value => value.toString(16).padStart(2, "0")).join("");
  if (observedSha !== declaredSha) throw integrityError();
  if (signal.aborted) throw signal.reason;

  const url = URL.createObjectURL(new Blob([bytes], {type: "application/pdf"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `nico-comprehensive-${runId}-${reportLanguage}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf`;
  link.style.position = "fixed";
  link.style.left = "-9999px";
  link.setAttribute("data-nico-review-pdf-download", "true");
  document.body.appendChild(link);
  // Only verified bytes reach the browser download. The assessment page stays open.
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function startExactRunDownload(
  runId: string,
  reportLanguage: ReportLanguage,
  binding: DownloadBinding,
): Promise<void> {
  const key = JSON.stringify([runId, reportLanguage, binding.commitSha, binding.canonicalTruthSha256 || ""]);
  const existing = inFlight.get(key);
  if (existing) return existing;
  const operation = retrieveExactRunPdf(runId, reportLanguage, binding)
    .finally(() => {
      if (inFlight.get(key) === operation) inFlight.delete(key);
    });
  inFlight.set(key, operation);
  return operation;
}

/** Track pending-review downloads through response validation and byte delivery. */
export default function AssessmentReviewPdfDownload() {
  const pending = useRef(new Map<string, AbortController>());

  useEffect(() => {
    const active = pending.current;
    function handleReviewPdfClick(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const actions = button.closest(REPORT_ACTIONS_SELECTOR);
      if (!actions) return;
      // Accepted editions retain AssessmentWorkspace's exact approval verification.
      if (button.getAttribute("data-assessment-pdf-kind") !== REVIEW_PDF_KIND) return;
      if (!REVIEW_PDF_LABEL.test(String(button.textContent || "").trim())) return;
      if (actions.getAttribute("data-assessment-report-ready") !== "true") return;
      const runId = visibleRunId(actions);
      const commitSha = String(actions.getAttribute("data-commit-sha") || "").trim();
      if (!runId.startsWith("comprun_") || !/^[0-9a-f]{40}$/.test(commitSha)) return;
      const requestedLanguage = button.getAttribute("data-report-language");
      const reportLanguage = requestedLanguage === "en" || requestedLanguage === "es-MX"
        ? requestedLanguage : activeReportLanguage();
      const key = JSON.stringify([runId, reportLanguage, commitSha]);
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      if (active.has(key)) return;
      const controller = new AbortController();
      active.set(key, controller);
      const timeout = window.setTimeout(() => controller.abort(new DOMException("PDF download deadline exceeded", "TimeoutError")), DOWNLOAD_TIMEOUT_MS);
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      showStatus(actions, spanishUi()
        ? "Descargando y verificando el PDF… Puedes seguir usando esta página."
        : "Downloading and verifying the PDF… You can keep using this page.");
      void startExactRunDownload(runId, reportLanguage, {
        commitSha,
        canonicalTruthSha256: String(actions.getAttribute("data-canonical-truth-sha256") || "").trim(),
        signal: controller.signal,
      }).then(() => {
        if (!controller.signal.aborted) showStatus(actions, spanishUi()
          ? "PDF verificado y enviado a tus descargas."
          : "PDF verified and sent to your downloads.");
      }).catch((error: unknown) => {
        if (!actions.isConnected) return;
        const timedOut = error instanceof DOMException && error.name === "TimeoutError";
        showStatus(actions, timedOut
          ? (spanishUi()
            ? "La descarga del PDF excedió el tiempo límite. Vuelve a intentarlo; no inicies otra evaluación."
            : "The PDF download timed out. Retry this download; do not start another assessment.")
          : error instanceof Error ? error.message
            : (spanishUi() ? "La descarga se interrumpió. Vuelve a intentarlo." : "The download was interrupted. Retry this download."),
        true);
      }).finally(() => {
        window.clearTimeout(timeout);
        active.delete(key);
        button.disabled = false;
        button.removeAttribute("aria-busy");
      });
    }

    document.addEventListener("click", handleReviewPdfClick, true);
    return () => {
      document.removeEventListener("click", handleReviewPdfClick, true);
      for (const controller of active.values()) controller.abort();
      active.clear();
    };
  }, []);

  return null;
}

export {activeReportLanguage, exactRunPdfHref, spanishUi, startExactRunDownload, visibleRunId};
