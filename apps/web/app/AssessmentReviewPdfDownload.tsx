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
  canonicalTruthSha256: string;
  signal?: AbortSignal;
  requiresNewApproval?: boolean;
  isCurrent?: () => boolean;
};

const inFlight = new Map<string, {operation: Promise<void>; binding: DownloadBinding}>();
const DOWNLOAD_TIMEOUT_MS = 255_000;
const pendingReviewOperations = new Map<string, AbortController>();
const pendingReviewPromises = new Map<string, {operation: Promise<void>; isCurrent: () => boolean; controller: AbortController}>();
const buttonOwners = new WeakMap<HTMLButtonElement, AbortController>();
const statusOwners = new WeakMap<Element, AbortController>();

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

class PdfDownloadFailure extends Error {}

function downloadError(response: Response): Error {
  if (response.status === 401 || response.status === 403) {
    return new PdfDownloadFailure(spanishUi()
      ? "Inicia sesión en NICO y vuelve a descargar este PDF."
      : "Sign in to NICO, then retry this PDF download.");
  }
  if (response.status === 504 || response.status === 408) {
    return new PdfDownloadFailure(spanishUi()
      ? "La descarga del PDF excedió el tiempo límite. Vuelve a intentarlo; no inicies otra evaluación."
      : "The PDF download timed out. Retry this download; do not start another assessment.");
  }
  const requestId = String(response.headers.get("x-request-id") || "");
  const reference = /^[a-zA-Z0-9_-]{1,80}$/.test(requestId)
    ? ` (${requestId})` : "";
  return new PdfDownloadFailure((spanishUi()
    ? "No se pudo descargar el PDF. Vuelve a intentarlo."
    : "The PDF could not be downloaded. Retry this download.") + reference);
}

function integrityError(): Error {
  return new PdfDownloadFailure(spanishUi()
    ? "El PDF no coincide con esta evaluación y su idioma. Recupera el estado de esta evaluación antes de volver a intentarlo."
    : "The PDF does not match this assessment and language. Recover this assessment's status before retrying.");
}

async function retrieveExactRunPdf(
  runId: string,
  reportLanguage: ReportLanguage,
  binding: DownloadBinding,
): Promise<void> {
  if (!runId.startsWith("comprun_") || !/^[0-9a-f]{40}$/.test(binding.commitSha)
    || !/^[0-9a-f]{64}$/i.test(binding.canonicalTruthSha256)
    || (binding.isCurrent && !binding.isCurrent())) throw integrityError();
  const signal = binding.signal || AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS);
  const response = await fetch(exactRunPdfHref(runId, reportLanguage), {
    method: "GET", cache: "no-store", credentials: "same-origin",
    headers: {Accept: "application/pdf"}, signal,
  });
  if (signal.aborted) throw signal.reason;
  if (binding.isCurrent && !binding.isCurrent()) throw integrityError();
  if (!response.ok) throw downloadError(response);
  const header = (name: string) => String(response.headers.get(name) || "").trim();
  const declaredSha = header("x-nico-pdf-sha256").toLowerCase();
  const truthSha = header("x-nico-canonical-truth-sha256").toLowerCase();
  if (
    header("content-type").split(";", 1)[0].trim().toLowerCase() !== "application/pdf"
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
    || truthSha !== binding.canonicalTruthSha256.toLowerCase()
    || (binding.requiresNewApproval && header("x-nico-localized-artifact-requires-new-approval") !== "true")
  ) throw integrityError();

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (signal.aborted) throw signal.reason;
  if (binding.isCurrent && !binding.isCurrent()) throw integrityError();
  if (bytes.length < 5 || String.fromCharCode(...bytes.slice(0, 5)) !== "%PDF-") {
    throw integrityError();
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const observedSha = Array.from(digest, value => value.toString(16).padStart(2, "0")).join("");
  if (observedSha !== declaredSha) throw integrityError();
  if (signal.aborted) throw signal.reason;

  if (binding.isCurrent && !binding.isCurrent()) throw integrityError();
  const url = URL.createObjectURL(new Blob([bytes], {type: "application/pdf"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `nico-comprehensive-${runId}-${reportLanguage}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf`;
  link.style.position = "fixed";
  link.style.left = "-9999px";
  link.setAttribute("data-nico-review-pdf-download", "true");
  document.body.appendChild(link);
  // Only verified bytes reach the browser download. The assessment page stays open.
  if (binding.isCurrent && !binding.isCurrent()) {
    link.remove(); URL.revokeObjectURL(url); throw integrityError();
  }
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function startExactRunDownload(
  runId: string,
  reportLanguage: ReportLanguage,
  binding: DownloadBinding,
): Promise<void> {
  const frozenBinding = {...binding};
  try {
    if (!runId.startsWith("comprun_") || !/^[0-9a-f]{40}$/.test(frozenBinding.commitSha)
      || !/^[0-9a-f]{64}$/i.test(frozenBinding.canonicalTruthSha256)
      || (frozenBinding.isCurrent && !frozenBinding.isCurrent())) throw integrityError();
    if (frozenBinding.signal?.aborted) throw frozenBinding.signal.reason;
  } catch (error) {
    return Promise.reject(error);
  }
  const key = JSON.stringify([runId, reportLanguage, frozenBinding.commitSha,
    frozenBinding.canonicalTruthSha256, Boolean(frozenBinding.requiresNewApproval)]);
  const existing = inFlight.get(key);
  if (existing && existing.binding.signal === frozenBinding.signal
    && existing.binding.isCurrent === frozenBinding.isCurrent) return existing.operation;
  const operation = retrieveExactRunPdf(runId, reportLanguage, frozenBinding)
    .finally(() => {
      if (inFlight.get(key)?.operation === operation) inFlight.delete(key);
    });
  inFlight.set(key, {operation, binding: frozenBinding});
  return operation;
}

function pendingReviewBindingMatches(
  button: HTMLButtonElement,
  actions: Element,
  runId: string,
  reportLanguage: ReportLanguage,
  binding: DownloadBinding,
): boolean {
  return button.isConnected && actions.isConnected
    && button.closest(REPORT_ACTIONS_SELECTOR) === actions
    && button.getAttribute("data-assessment-pdf-kind") === REVIEW_PDF_KIND
    && actions.getAttribute("data-assessment-report-ready") === "true"
    && actions.getAttribute("data-assessment-pdf-available") !== "false"
    && visibleRunId(actions) === runId
    && String(actions.getAttribute("data-commit-sha") || "").trim() === binding.commitSha
    && String(actions.getAttribute("data-canonical-truth-sha256") || "").trim().toLowerCase() === binding.canonicalTruthSha256
    && button.getAttribute("data-report-language") === reportLanguage
    && (actions.getAttribute("data-requested-report-language") === null
      || actions.getAttribute("data-requested-report-language") === reportLanguage)
    && (actions.getAttribute("data-assessment-locale-reapproval-required") === "true") === Boolean(binding.requiresNewApproval);
}

/** The guard and Workspace fallback share one bounded, exact pending-review path. */
function downloadPendingReviewPdf(button: HTMLButtonElement, requiresNewApproval = false): Promise<void> {
  const actions = button.closest(REPORT_ACTIONS_SELECTOR);
  const runId = visibleRunId(actions);
  const commitSha = String(actions?.getAttribute("data-commit-sha") || "").trim();
  const canonicalTruthSha256 = String(actions?.getAttribute("data-canonical-truth-sha256") || "").trim().toLowerCase();
  const requestedLanguage = button.getAttribute("data-report-language");
  const reportLanguage = requestedLanguage === "en" || requestedLanguage === "es-MX"
    ? requestedLanguage : activeReportLanguage();
  const binding: DownloadBinding = {
    commitSha, canonicalTruthSha256,
    requiresNewApproval: requiresNewApproval
      || actions?.getAttribute("data-assessment-locale-reapproval-required") === "true",
  };
  if (!actions || !runId.startsWith("comprun_") || !/^[0-9a-f]{40}$/.test(commitSha)
    || !/^[0-9a-f]{64}$/.test(canonicalTruthSha256)
    || !pendingReviewBindingMatches(button, actions, runId, reportLanguage, binding)) {
    return Promise.reject(integrityError());
  }
  const key = JSON.stringify([runId, reportLanguage, commitSha, canonicalTruthSha256,
    Boolean(binding.requiresNewApproval)]);
  const existing = pendingReviewPromises.get(key);
  if (existing?.isCurrent()) return existing.operation;
  // An explicit click on a replacement binding cancels the stale retained read.
  existing?.controller.abort();
  buttonOwners.get(button)?.abort();
  const controller = new AbortController();
  pendingReviewOperations.set(key, controller);
  buttonOwners.set(button, controller);
  const isCurrent = () => pendingReviewOperations.get(key) === controller
    && buttonOwners.get(button) === controller
    && pendingReviewBindingMatches(button, actions, runId, reportLanguage, binding);
  const timeout = window.setTimeout(() => controller.abort(
    new DOMException("PDF download deadline exceeded", "TimeoutError")), DOWNLOAD_TIMEOUT_MS);
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  statusOwners.set(actions, controller);
  showStatus(actions, spanishUi()
    ? "Descargando y verificando el PDF… Puedes seguir usando esta página."
    : "Downloading and verifying the PDF… You can keep using this page.");
  const operation = startExactRunDownload(runId, reportLanguage, {
    ...binding, signal: controller.signal, isCurrent,
  }).then(() => {
    if (isCurrent() && !controller.signal.aborted) showStatus(actions, spanishUi()
      ? "PDF verificado y enviado a tus descargas."
      : "PDF verified and sent to your downloads.");
  }).catch((error: unknown) => {
    // A stale completion belongs to its original page, including its status.
    if (!isCurrent()) return;
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    showStatus(actions, timedOut
      ? (spanishUi()
        ? "La descarga del PDF excedió el tiempo límite. Vuelve a intentarlo; no inicies otra evaluación."
        : "The PDF download timed out. Retry this download; do not start another assessment.")
      : error instanceof PdfDownloadFailure ? error.message
        : (spanishUi() ? "La descarga se interrumpió. Vuelve a intentarlo." : "The download was interrupted. Retry this download."),
    true);
    throw error;
  }).finally(() => {
    if (!isCurrent() && statusOwners.get(actions) === controller) {
      actions.querySelector(`[${STATUS_ATTR}]`)?.remove();
    }
    if (statusOwners.get(actions) === controller) statusOwners.delete(actions);
    // Dispose this fetch even when validation stopped before body consumption.
    controller.abort();
    window.clearTimeout(timeout);
    if (pendingReviewOperations.get(key) === controller) pendingReviewOperations.delete(key);
    if (pendingReviewPromises.get(key)?.operation === operation) pendingReviewPromises.delete(key);
    if (buttonOwners.get(button) === controller) {
      buttonOwners.delete(button);
      // React can reuse this element for a different run or an accepted edition.
      const desiredDisabled = button.getAttribute("data-assessment-action-disabled");
      button.disabled = desiredDisabled === null
        ? !pendingReviewBindingMatches(button, actions, runId, reportLanguage, binding)
        : desiredDisabled === "true";
      button.removeAttribute("aria-busy");
    }
  });
  pendingReviewPromises.set(key, {operation, isCurrent, controller});
  return operation;
}

/** Track pending-review downloads through response validation and byte delivery. */
export default function AssessmentReviewPdfDownload() {
  const pending = useRef(pendingReviewOperations);
  useEffect(() => {
    const active = pending.current;
    function handleReviewPdfClick(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const actions = button.closest(REPORT_ACTIONS_SELECTOR);
      if (!actions || button.getAttribute("data-assessment-pdf-kind") !== REVIEW_PDF_KIND
        || !REVIEW_PDF_LABEL.test(String(button.textContent || "").trim())
        || actions.getAttribute("data-assessment-report-ready") !== "true") return;
      const runId = visibleRunId(actions);
      const commitSha = String(actions.getAttribute("data-commit-sha") || "").trim();
      const truthSha = String(actions.getAttribute("data-canonical-truth-sha256") || "").trim();
      if (!runId.startsWith("comprun_") || !/^[0-9a-f]{40}$/.test(commitSha)
        || !/^[0-9a-f]{64}$/i.test(truthSha)) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      void downloadPendingReviewPdf(button).catch(() => {
        // The shared owner has already shown the current operation's error.
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

export {activeReportLanguage, downloadPendingReviewPdf, exactRunPdfHref, spanishUi, startExactRunDownload, visibleRunId};
