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

type ArtifactMode = "pending-source-frozen" | "pending-source-localized-draft";

type DownloadBinding = {
  commitSha: string;
  canonicalTruthSha256: string;
  signal?: AbortSignal;
  requiresNewApproval?: boolean;
  preparationJobId?: string;
  artifactMode?: ArtifactMode;
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

function downloadTimeoutMessage(): string {
  // A stopped HTTP wait does not cancel or establish the outcome of backend preparation.
  // Do not promise readiness, trigger a retry, or activate asynchronous preparation here.
  return spanishUi()
    ? "La descarga del PDF excedió el tiempo límite. La preparación puede continuar en el servidor; esto no confirma un fallo ni que el PDF esté listo. Espera unos minutos. Vuelve a intentarlo con este mismo botón, evaluación e idioma; no inicies otra evaluación. No se reintentará automáticamente."
    : "The PDF download timed out. Preparation may still be running on the server; this does not confirm failure or that the PDF is ready. Wait a few minutes. Retry this download using the same button, assessment and language; do not start another assessment. No automatic retry will run.";
}

async function downloadError(response: Response): Promise<Error> {
  const retryAfter = response.headers.get("retry-after") || "";
  if (response.status === 503 && /^[1-9][0-9]?$/.test(retryAfter) && Number(retryAfter) <= 60) {
    try {
      const payload = await response.clone().json();
      if (payload?.detail?.reason === "retained_pdf_preparing") {
        return new PdfDownloadFailure(spanishUi()
          ? `NICO todavía está preparando un PDF. Reintenta esta descarga dentro de al menos ${retryAfter} segundos; no inicies otra evaluación.`
          : `NICO is still preparing a PDF. Retry this download in at least ${retryAfter} seconds; do not start another assessment.`);
      }
    } catch {
      // Unrecognized or malformed busy responses retain the generic error.
    }
  }
  if (response.status === 401 || response.status === 403) {
    return new PdfDownloadFailure(spanishUi()
      ? "Inicia sesión en NICO y vuelve a descargar este PDF."
      : "Sign in to NICO, then retry this PDF download.");
  }
  if (response.status === 504 || response.status === 408) {
    return new PdfDownloadFailure(downloadTimeoutMessage());
  }
  const requestId = String(response.headers.get("x-request-id") || "");
  const reference = /^[a-zA-Z0-9_-]{1,80}$/.test(requestId)
    ? ` (${requestId})` : "";
  return new PdfDownloadFailure((spanishUi()
    ? "No se pudo descargar el PDF. Vuelve a intentarlo."
    : "The PDF could not be downloaded. Retry this download.") + reference);
}

// Read only a small JSON envelope; never render server-provided prose or raw errors.
async function boundedDiagnosticJson(response: Response, limit: number): Promise<unknown> {
  if (!response.headers.get("content-type")?.toLowerCase().startsWith("application/json")) throw new Error("invalid diagnostic");
  const reader = response.body?.getReader();
  if (!reader) throw new Error("missing diagnostic");
  let length = 0;
  const chunks: Uint8Array[] = [];
  try {
    for (;;) {
      const part = await reader.read();
      if (part.done) break;
      length += part.value.byteLength;
      if (length > limit) throw new Error("oversized diagnostic");
      chunks.push(part.value);
    }
    const joined = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {joined.set(chunk, offset); offset += chunk.byteLength;}
    return JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(joined));
  } finally {void reader.cancel().catch(() => {}); reader.releaseLock();}
}

async function preparationFailure(response: Response): Promise<PdfDownloadFailure> {
  let reason = "unknown";
  try {
    const body = await boundedDiagnosticJson(response, 4096) as {detail?: unknown};
    if (typeof body?.detail === "string" && ["review_pdf_preparation_unavailable",
      "review_pdf_commit_outcome_unknown", "review_pdf_operation_unavailable_or_timed_out"].includes(body.detail)) reason = body.detail;
  } catch { /* Missing or malformed detail remains unknown; never absence. */ }
  const trace = response.headers.get("x-nico-admission-trace") || "";
  const reference = /^[0-9a-f]{32}$/.test(trace) ? ` [${trace}]` : "";
  const en = reason === "review_pdf_preparation_unavailable"
    ? "Background PDF preparation is unavailable. This does not establish an earlier job's outcome."
    : reason === "review_pdf_commit_outcome_unknown"
      ? "The server could not confirm whether preparation was recorded. A job may exist."
      : reason === "review_pdf_operation_unavailable_or_timed_out"
        ? "The preparation operation was unavailable or exceeded its deadline. Its job outcome is unknown."
        : "The preparation response was unavailable or unrecognized. Its job outcome is unknown.";
  const es = reason === "review_pdf_preparation_unavailable"
    ? "La preparación del PDF en segundo plano no está disponible. Esto no establece el resultado de un trabajo anterior."
    : reason === "review_pdf_commit_outcome_unknown"
      ? "El servidor no pudo confirmar si se registró la preparación. Puede existir un trabajo."
      : reason === "review_pdf_operation_unavailable_or_timed_out"
        ? "La operación de preparación no estuvo disponible o excedió su plazo. El resultado del trabajo es desconocido."
        : "La respuesta de preparación no estuvo disponible o no se reconoció. El resultado del trabajo es desconocido.";
  return new PdfDownloadFailure((spanishUi() ? es + " No se enviará otra solicitud de preparación automáticamente."
    : en + " No new preparation request will be sent automatically.") + reference);
}

const ledgerControls = new WeakMap<Element, {key: string; button: HTMLButtonElement; output: HTMLElement; controller?: AbortController}>();
const ledgerRequests = new Set<AbortController>();

function ledgerSummary(value: unknown): string {
  if (!value || typeof value !== "object") throw new Error("invalid ledger");
  const data = value as Record<string, unknown>;
  if (data.schema !== "nico.pdf-canary-ledger-read.v1"
    || data.search_scope !== "configured-row-tenant-and-identity-run-locale"
    || data.activation_authorized !== false || data.job_integrity_verified !== false
    || data.physical_worker_exit_confirmed !== null) throw new Error("invalid ledger");
  if (["busy", "unavailable"].includes(String(data.status)) && data.query_complete === false
    && data.scoped_rows_present === null && data.exact_source_row_present === null
    && data.rows_returned === 0 && Array.isArray(data.rows) && data.rows.length === 0) {
    return spanishUi() ? "Diagnóstico no disponible o ocupado. La existencia de un trabajo sigue siendo desconocida."
      : "Diagnostic unavailable or busy. Job existence remains unknown.";
  }
  if (!["complete", "partial"].includes(String(data.status)) || data.read_only_transaction !== true
    || data.query_complete !== (data.status === "complete") || !Array.isArray(data.rows)
    || !Number.isInteger(data.rows_returned) || data.rows_returned !== data.rows.length || data.rows.length > 32
    || typeof data.scoped_rows_present !== "boolean"
    || data.scoped_rows_present !== (data.rows.length > 0)
    || ![true, false, null].includes(data.exact_source_row_present as boolean | null)
    || (data.status === "partial" && (data.rows.length !== 32 || data.exact_source_row_present === false))
    || (data.rows.length === 0 && data.exact_source_row_present !== false)) throw new Error("invalid ledger");
  const fields = ["customer_id", "project_id", "run_id", "repository", "commit_sha", "source_revision",
    "source_integrity_sha256", "canonical_truth_sha256", "source_artifact_sha256", "language"];
  let obsolete = 0;
  for (const row of data.rows) {
    if (!row || typeof row !== "object" || !Array.isArray(row.binding_mismatches)
      || row.binding_mismatches.length > 10 || new Set(row.binding_mismatches).size !== row.binding_mismatches.length
      || !row.binding_mismatches.every((key: unknown) => typeof key === "string" && fields.includes(key))
      || row.source_binding_matches !== (row.binding_mismatches.length === 0)) throw new Error("invalid ledger");
    if (!row.source_binding_matches) obsolete++;
  }
  const complete = data.query_complete === true;
  if ((complete && data.exact_source_row_present !== (obsolete < data.rows.length))
    || (obsolete < data.rows.length && data.exact_source_row_present !== true)) throw new Error("invalid ledger");
  return spanishUi()
    ? `Lectura ${complete ? "completa" : "parcial"}: ${data.rows_returned} filas visibles; ${obsolete} con vínculo de origen distinto. Alcance: cliente/proyecto, evaluación e idioma configurados. ${data.scoped_rows_present ? "Hay filas en este alcance." : "No se observaron filas en este alcance al leerlo."} No prueba ausencia histórica, integridad del trabajo, salida del proceso ni autorización para activar. No se modificaron trabajos.`
    : `${complete ? "Complete" : "Partial"} read: ${data.rows_returned} visible rows; ${obsolete} with a different source binding. Scope: configured tenant/project, run and locale. ${data.scoped_rows_present ? "Rows exist in this scope." : "No rows were observed in this scope at the read."} This does not prove historical absence, job integrity, process exit or permission to activate. No jobs were changed.`;
}

function attachLedgerDiagnostic(button: HTMLButtonElement): void {
  const actions = button.closest(REPORT_ACTIONS_SELECTOR);
  if (!actions || button.getAttribute("data-assessment-pdf-kind") !== REVIEW_PDF_KIND) return;
  const runId = visibleRunId(actions);
  const locale = button.getAttribute("data-report-language");
  if ((locale !== "en" && locale !== "es-MX") || !canaryTargetMatches(runId, locale)) return;
  const binding = {commitSha: actions.getAttribute("data-commit-sha") || "",
    canonicalTruthSha256: actions.getAttribute("data-canonical-truth-sha256") || "",
    requiresNewApproval: actions.getAttribute("data-assessment-locale-reapproval-required") === "true"};
  if (!/^[0-9a-f]{40}$/.test(binding.commitSha) || !/^[0-9a-f]{64}$/.test(binding.canonicalTruthSha256)) return;
  const key = JSON.stringify([runId, locale, binding.commitSha, binding.canonicalTruthSha256, binding.requiresNewApproval]);
  const old = ledgerControls.get(actions);
  if (old?.key === key && old.button.isConnected) return;
  old?.controller?.abort(); old?.button.remove(); old?.output.remove();
  const control = document.createElement("button");
  control.type = "button";
  control.setAttribute("data-review-pdf-diagnostic", "true");
  control.textContent = spanishUi() ? "Consultar diagnóstico de preparación (solo lectura)" : "Read preparation diagnostic";
  const output = document.createElement("pre");
  output.setAttribute("aria-live", "polite");
  output.style.whiteSpace = "pre-wrap";
  output.style.userSelect = "text";
  const entry = {key, button: control, output, controller: undefined as AbortController | undefined};
  ledgerControls.set(actions, entry);
  const current = () => control.isConnected && ledgerControls.get(actions) === entry
    && pendingReviewBindingMatches(button, actions, runId, locale, binding);
  control.onclick = async () => {
    if (control.disabled || !current()) return;
    const controller = new AbortController(); entry.controller = controller; ledgerRequests.add(controller);
    control.disabled = true;
    output.textContent = spanishUi() ? "Consultando; no se iniciará ninguna preparación…" : "Reading; no preparation will be started…";
    try {
      const response = await fetch(preparationHref(runId, locale) + "?canary_ledger=true", {
        method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error",
        headers: {Accept: "application/json"}, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
      });
      if (!response.ok) throw new Error("diagnostic unavailable");
      const summary = ledgerSummary(await boundedDiagnosticJson(response, 24 * 1024));
      if (current() && !controller.signal.aborted) output.textContent = summary;
    } catch {
      if (current() && !controller.signal.aborted) output.textContent = spanishUi()
        ? "No se obtuvo un diagnóstico válido. El resultado sigue siendo desconocido. La preparación debe estar desactivada; puede ser necesario iniciar sesión."
        : "No valid diagnostic was obtained. The outcome remains unknown. Preparation must be disabled; sign-in may be required.";
    } finally {
      ledgerRequests.delete(controller); controller.abort();
      if (current()) control.disabled = false;
    }
  };
  actions.appendChild(control); actions.appendChild(output);
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
  const prepared = binding.preparationJobId;
  if (prepared && !/^reviewpdfprep_[0-9a-f]{64}$/.test(prepared)) throw integrityError();
  const href = prepared ? `${preparationHref(runId, reportLanguage)}/pdf?${preparationQuery(prepared, binding)}`
    : exactRunPdfHref(runId, reportLanguage);
  const response = await fetch(href, {
    method: "GET", cache: "no-store", credentials: "same-origin",
    headers: {Accept: "application/pdf"}, signal,
  });
  if (signal.aborted) throw signal.reason;
  if (binding.isCurrent && !binding.isCurrent()) throw integrityError();
  if (!response.ok) throw await downloadError(response);
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
    || (prepared && (Array.from(response.headers.entries()).some(([name, value]) => name.startsWith("x-nico-accepted-") && value !== "")
      || header("x-nico-human-review-completed") === "true" || header("x-nico-human-reviewed") === "true"))
    || (prepared && (!binding.artifactMode || header("x-nico-review-pdf-artifact-mode") !== binding.artifactMode))
    || (prepared && binding.artifactMode === "pending-source-localized-draft" && (
      header("x-nico-localized-artifact-requires-new-approval") !== "true"
      || header("x-nico-localized-artifact-approval-invalidated") !== "true"
      || header("x-nico-artifact-finality") !== "automated_draft"
      || !["", "false"].includes(header("x-nico-frozen-source-artifact"))))
    || (prepared && binding.artifactMode === "pending-source-frozen" && (
      header("x-nico-frozen-source-artifact") !== "true"
      || header("x-nico-localized-artifact-requires-new-approval") !== "false"
      || header("x-nico-localized-artifact-approval-invalidated") !== "false"))
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
    frozenBinding.canonicalTruthSha256, Boolean(frozenBinding.requiresNewApproval), frozenBinding.preparationJobId, frozenBinding.artifactMode]);
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
function downloadPendingReviewPdf(button: HTMLButtonElement, requiresNewApproval = false, resumeOnly = false): Promise<void> {
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
  const asynchronous = asyncPreparationEnabled(runId, reportLanguage);
  if (resumeOnly && (!asynchronous || !savedPreparation(key)
    || ["ready", "not_started", "cancelled"].includes(cancellationState(key)))) return Promise.resolve();
  // Only a new explicit user click can clear a positively resolved cancellation.
  if (!resumeOnly && ["ready", "not_started"].includes(cancellationState(key))) {
    saveCancellation(key, "");
  }
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
  let timeout: number | undefined;
  const startDownloadDeadline = () => {timeout = window.setTimeout(() => controller.abort(
    new DOMException("PDF download deadline exceeded", "TimeoutError")), DOWNLOAD_TIMEOUT_MS);};
  if (!asynchronous) startDownloadDeadline();
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  statusOwners.set(actions, controller);
  showStatus(actions, asynchronous ? (spanishUi()
    ? "Consultando la preparación del PDF…" : "Checking PDF preparation…") : spanishUi()
    ? "Descargando y verificando el PDF… Puedes seguir usando esta página."
    : "Downloading and verifying the PDF… You can keep using this page.");
  const operation = (async () => {
    let preparationJobId: string | undefined;
    let artifactMode: ArtifactMode | undefined;
    if (asynchronous) {
      ({jobId: preparationJobId, artifactMode} = await prepareReviewPdf(runId, reportLanguage, {...binding, isCurrent}, key, actions, controller, resumeOnly));
      if (cancellationRequested(key)) throw cancellationMessage();
      startDownloadDeadline();
      showStatus(actions, spanishUi() ? "Descargando y verificando el PDF…" : "Downloading and verifying the PDF…");
    }
    await startExactRunDownload(runId, reportLanguage, {
      ...binding, preparationJobId, artifactMode, signal: controller.signal, isCurrent,
    });
    if (asynchronous) savePreparation(key, "");
  })().then(() => {
    if (isCurrent() && !controller.signal.aborted) showStatus(actions, spanishUi()
      ? "PDF verificado y enviado a tus descargas."
      : "PDF verified and sent to your downloads.");
  }).catch((error: unknown) => {
    // A stale completion belongs to its original page, including its status.
    if (!isCurrent()) return;
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    showStatus(actions, timedOut
      ? downloadTimeoutMessage()
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
    if (timeout !== undefined) window.clearTimeout(timeout);
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

function asyncPreparationEnabled(runId?: string, language?: ReportLanguage): boolean {
  if (typeof process === "undefined" || process.env.NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION !== "true") return false;
  return canaryTargetMatches(runId, language);
}
function canaryTargetMatches(runId?: string, language?: ReportLanguage): boolean {
  if (typeof process === "undefined") return false;
  const target = process.env.NEXT_PUBLIC_NICO_REVIEW_PDF_CANARY_RUN_ID;
  const locale = process.env.NEXT_PUBLIC_NICO_REVIEW_PDF_CANARY_LANGUAGE;
  if (!target || !/^comprun_[a-zA-Z0-9_-]{1,160}$/.test(target)
    || !["en", "es-MX"].includes(locale || "")) return false;
  return runId === undefined || (target === runId && locale === language);
}
function preparationHref(runId: string, language: ReportLanguage): string {
  return `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/review-pdf/${language}`;
}
function preparationQuery(jobId: string, binding: DownloadBinding): string {
  return new URLSearchParams({...(jobId === "requested" ? {} : {job_id: jobId}), commit_sha: binding.commitSha,
    canonical_truth_sha256: binding.canonicalTruthSha256}).toString();
}
function savedPreparation(key: string): string {
  try {
    const value = window.sessionStorage.getItem(`nico-review-preparation:${key}`) || "";
    if (value === "requested" || /^requested:v1:[0-9]{1,16}$/.test(value)) return "requested";
    return /^reviewpdfprep_[0-9a-f]{64}$/.test(value) ? value : "";
  } catch { return ""; }
}
function savedAdmissionDeadline(key: string): number {
  try {
    const value = window.sessionStorage.getItem(`nico-review-preparation:${key}`) || "";
    return /^requested:v1:[0-9]{1,16}$/.test(value) ? Number(value.split(":")[2]) : 0;
  } catch { return 0; }
}
function savePreparation(key: string, jobId: string): void {
  try {
    if (jobId) window.sessionStorage.setItem(`nico-review-preparation:${key}`, jobId);
    else window.sessionStorage.removeItem(`nico-review-preparation:${key}`);
  } catch { /* Durable backend status remains authoritative. */ }
}
function cancellationState(key: string): string {
  try { return window.sessionStorage.getItem(`nico-review-cancel:${key}`) || ""; }
  catch { return ""; }
}
function saveCancellation(key: string, state: string): void {
  try {
    if (state) window.sessionStorage.setItem(`nico-review-cancel:${key}`, state);
    else window.sessionStorage.removeItem(`nico-review-cancel:${key}`);
  } catch { /* In-memory intent still fences the current operation. */ }
}
function cancellationRequested(key: string): boolean {
  return cancellationState(key) === "requested";
}
function cancellationMessage(): PdfDownloadFailure {
  return new PdfDownloadFailure(spanishUi()
    ? "Se solicitó cancelar. No se descargará el PDF automáticamente. Consulta el estado; no inicies otra evaluación."
    : "Cancellation was requested. The PDF will not download automatically. Check its status; do not start another assessment.");
}
async function prepareReviewPdf(runId: string, language: ReportLanguage, binding: DownloadBinding,
  key: string, actions: Element, controller: AbortController, resumeOnly = false): Promise<{jobId: string; artifactMode: ArtifactMode}> {
  let jobId = savedPreparation(key);
  let artifactMode: ArtifactMode | undefined;
  let qualifiedJobId: string | undefined;
  let cancelIntent = cancellationRequested(key);
  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.setAttribute("data-review-pdf-cancel", "true");
  cancelButton.textContent = spanishUi() ? "Cancelar preparación" : "Cancel preparation";
  cancelButton.onclick = () => {
    if (controller.signal.aborted || (binding.isCurrent && !binding.isCurrent())) return;
    cancelIntent = true;
    // Intent survives an interrupted POST/status response; it never creates a job.
    saveCancellation(key, "requested");
    cancelButton.disabled = true;
    showStatus(actions, spanishUi()
      ? "Cancelación solicitada localmente; el servidor aún no la ha confirmado."
      : "Cancellation requested locally; the server has not confirmed it yet.");
  };
  actions.appendChild(cancelButton);
  const wantsCancel = () => cancelIntent || cancellationRequested(key);
  const admissionDeadline = savedAdmissionDeadline(key) || Date.now() + 900_000;
  if (jobId === "requested") savePreparation(key, `requested:v1:${admissionDeadline}`);
  const singleStatusCheck = jobId === "requested" && admissionDeadline <= Date.now() && !resumeOnly;
  const preparationDeadline = singleStatusCheck ? Date.now() + 30_000
    : jobId === "requested" ? Math.min(admissionDeadline, Date.now() + 900_000) : Date.now() + 900_000;
  const stillPending = () => new PdfDownloadFailure(spanishUi()
    ? "La preparación sigue pendiente. Selecciona descargar de nuevo para consultar su estado."
    : "Preparation is still pending. Select download again to check its status.");
  const read = async (prepare: boolean, qualify = false) => {
    if (controller.signal.aborted) throw controller.signal.reason;
    if (binding.isCurrent && !binding.isCurrent()) throw integrityError();
    const remaining = preparationDeadline - Date.now();
    if (remaining <= 0) throw stillPending();
    if (prepare && wantsCancel()) {
      saveCancellation(key, "not_started");
      throw cancellationMessage();
    }
    if (prepare) savePreparation(key, `requested:v1:${preparationDeadline}`);
    const response = await fetch(preparationHref(runId, language) + (prepare ? "" : `?${preparationQuery(qualify ? "requested" : jobId, binding)}${qualify ? "&qualify=true" : ""}`), {
      method: prepare ? "POST" : "GET", cache: "no-store", credentials: "same-origin",
      headers: {Accept: "application/json", ...(prepare ? {"Content-Type": "application/json"} : {})},
      body: prepare ? JSON.stringify({prepare: true, commit_sha: binding.commitSha,
        canonical_truth_sha256: binding.canonicalTruthSha256}) : undefined,
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(Math.min(30_000, remaining))]),
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && error instanceof DOMException && error.name === "TimeoutError") {
        throw stillPending();
      }
      throw error;
    });
    if (!response.ok) {
      // An unlocked lookup miss cannot rule out an admission COMMIT in flight.
      if (!prepare && jobId === "requested" && response.status === 404) return "admission_unknown";
      if ([404, 409, 422].includes(response.status)) savePreparation(key, "");
      if (response.status === 503) throw await preparationFailure(response);
      throw await downloadError(response);
    }
    const status = await response.json();
    if (controller.signal.aborted) throw controller.signal.reason;
    if ((binding.isCurrent && !binding.isCurrent()) || status.run_id !== runId
      || status.report_language !== language || status.commit_sha !== binding.commitSha
      || status.canonical_truth_sha256 !== binding.canonicalTruthSha256
      || status.client_delivery_allowed !== false || status.human_review_required !== true
      || !/^reviewpdfprep_[0-9a-f]{64}$/.test(status.job_id)
      || (jobId && jobId !== "requested" && status.job_id !== jobId)) throw integrityError();
    if (!["pending-source-frozen", "pending-source-localized-draft"].includes(status.artifact_mode)
      || (binding.requiresNewApproval && status.artifact_mode !== "pending-source-localized-draft")
      || (artifactMode && artifactMode !== status.artifact_mode)
      || (qualifiedJobId && qualifiedJobId !== status.job_id)) throw integrityError();
    artifactMode = status.artifact_mode;
    if (qualify) {
      if (status.state !== "eligible") throw integrityError();
      qualifiedJobId = status.job_id;
      return "eligible";
    }
    jobId = status.job_id;
    savePreparation(key, jobId);
    if (wantsCancel()) {
      const cancelled = await fetch(preparationHref(runId, language) + "/cancel", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {Accept: "application/json", "Content-Type": "application/json"},
        body: JSON.stringify({job_id: jobId, commit_sha: binding.commitSha,
          canonical_truth_sha256: binding.canonicalTruthSha256}),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(Math.min(30_000, Math.max(1, preparationDeadline - Date.now())))]),
      });
      if (!cancelled.ok) throw cancellationMessage();
      const result = await cancelled.json();
      if (controller.signal.aborted) throw controller.signal.reason;
      if ((binding.isCurrent && !binding.isCurrent()) || result.job_id !== jobId
        || result.run_id !== runId || result.report_language !== language
        || result.commit_sha !== binding.commitSha || result.canonical_truth_sha256 !== binding.canonicalTruthSha256
        || result.artifact_mode !== artifactMode || result.human_review_required !== true
        || result.client_delivery_allowed !== false) throw integrityError();
      if (result.state === "cancelled") {
        saveCancellation(key, "cancelled");
        throw new PdfDownloadFailure(spanishUi()
        ? "Cancelación registrada. La salida del proceso no está confirmada; la capacidad permanece protegida. La evaluación no cambió."
        : "Cancellation recorded. Process exit is not confirmed; capacity remains protected. The assessment is unchanged.");
      }
      if (result.state === "ready") {
        saveCancellation(key, "ready");
        throw new PdfDownloadFailure(spanishUi()
        ? "La preparación terminó antes de la cancelación. No se descargó ningún PDF automáticamente. Selecciona descargar si deseas el PDF."
        : "Preparation finished before cancellation. No PDF was downloaded automatically. Select download if you want the PDF.");
      }
      throw cancellationMessage();
    }
    return String(status.state);
  };
  try {
  // A derivative is admitted only after the server proves a pending source.
  // Resume uses the already admitted, source-bound job; it never posts again.
  if (binding.requiresNewApproval && !jobId) await read(false, true);
  let state = await read(!jobId);
  const messages: Record<string, [string, string]> = {
    admission_unknown: ["Checking whether PDF preparation was accepted…", "Comprobando si se aceptó la preparación del PDF…"],
    queued: ["PDF preparation is queued. You can return to this page later.", "La preparación del PDF está en cola. Puedes volver a esta página más tarde."],
    preparing: ["Preparing the complete review PDF…", "Preparando el PDF completo para revisión…"],
    verifying: ["Verifying the prepared PDF…", "Verificando el PDF preparado…"],
  };
  for (let attempt = 0; ; attempt++) {
    if (state === "ready" && artifactMode) return {jobId, artifactMode};
    if (!messages[state]) {
      if (state !== "cancelled") savePreparation(key, "");
      throw new PdfDownloadFailure(spanishUi()
        ? "La preparación del PDF falló o se canceló. La evaluación no cambió."
        : "PDF preparation failed or was cancelled. The assessment is unchanged.");
    }
    const remaining = preparationDeadline - Date.now();
    if (singleStatusCheck || attempt >= 360 || remaining <= 0) throw stillPending();
    showStatus(actions, messages[state][spanishUi() ? 1 : 0]);
    await new Promise<void>((resolve, reject) => {
      const abort = () => {window.clearTimeout(timer); reject(controller.signal.reason);};
      const timer = window.setTimeout(() => {controller.signal.removeEventListener("abort", abort); resolve();}, Math.min(2500, remaining));
      controller.signal.addEventListener("abort", abort, {once: true});
      if (controller.signal.aborted) abort();
    });
    state = await read(false);
  }
  } finally { cancelButton.remove(); }
}

/** Track pending-review downloads through response validation and byte delivery. */
export default function AssessmentReviewPdfDownload() {
  const pending = useRef(pendingReviewOperations);
  useEffect(() => {
    const active = pending.current;
    function handleReviewPdfClick(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled
        || button.getAttribute("data-review-pdf-cancel") === "true") return;
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
    const recover = () => {
      for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>(`${REPORT_ACTIONS_SELECTOR} button`))) {
        attachLedgerDiagnostic(button);
        if (asyncPreparationEnabled() && !button.disabled && button.getAttribute("data-assessment-pdf-kind") === REVIEW_PDF_KIND) {
          void downloadPendingReviewPdf(button, false, true).catch(() => {});
        }
      }
    };
    recover();
    const observer = typeof MutationObserver === "undefined" ? null : new MutationObserver(recover);
    observer?.observe(document.body, {childList: true, subtree: true});
    return () => {
      observer?.disconnect();
      document.removeEventListener("click", handleReviewPdfClick, true);
      for (const controller of active.values()) controller.abort();
      active.clear();
      for (const controller of ledgerRequests) controller.abort();
      ledgerRequests.clear();
    };
  }, []);
  return null;
}

export {activeReportLanguage, downloadPendingReviewPdf, exactRunPdfHref, spanishUi, startExactRunDownload, visibleRunId};
