"use client";

import {useEffect, useState} from "react";

type PdfAction = "review" | "approve" | "redownload";
type OutcomeKind =
  | "draft-pending"
  | "draft-ready"
  | "approval-pending"
  | "approval-failed"
  | "approval-unconfirmed"
  | "approval-recorded"
  | "approved-pdf-not-presented"
  | "approved-pdf-ready"
  | "approved-redownload-pending";

type PendingPdf = {
  url: string;
  filename: string;
  action: PdfAction;
};

type ArtifactOutcome = {
  kind: OutcomeKind;
  httpStatus?: number;
};

const REVOKE_DELAY_MS = 5 * 60 * 1000;
const RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000;
const APPROVED_PDF_PRESENTATION_TIMEOUT_MS = 60 * 1000;
const REVIEW_PDF_LABELS = new Set([
  "Download exact PDF to review",
  "Descargar PDF exacto para revisión",
]);
const APPROVAL_PDF_LABELS = new Set([
  "Approve and download final PDF",
  "Aprobar y descargar PDF final",
]);
const REDOWNLOAD_PDF_LABELS = new Set([
  "Download approved PDF again",
  "Descargar nuevamente el PDF aprobado",
]);
const PDF_ACTION_LABELS = new Set([
  ...REVIEW_PDF_LABELS,
  ...APPROVAL_PDF_LABELS,
  ...REDOWNLOAD_PDF_LABELS,
]);

function pdfActionForLabel(label: string): PdfAction | null {
  if (REVIEW_PDF_LABELS.has(label)) return "review";
  if (APPROVAL_PDF_LABELS.has(label)) return "approve";
  if (REDOWNLOAD_PDF_LABELS.has(label)) return "redownload";
  return null;
}

function isIOSFamilyWebKit(): boolean {
  const userAgent = navigator.userAgent || "";
  return /iPad|iPhone|iPod/i.test(userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function approvalDecisionFromBody(body: BodyInit | null | undefined): string {
  if (typeof body !== "string") return "";
  try {
    const parsed = JSON.parse(body) as {decision?: unknown};
    return String(parsed.decision || "").trim().toLowerCase();
  } catch {
    return "";
  }
}

function isApprovalRequest(input: RequestInfo | URL, init?: RequestInit): boolean {
  const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
  if (method !== "POST") return false;
  const url = requestUrl(input);
  const reviewEndpoint = /\/assessment\/comprehensive-run\/[^/?]+(?:\/localized-editions\/[^/?]+)?\/review(?:\?|$)/.test(url);
  return reviewEndpoint && approvalDecisionFromBody(init?.body) === "approved";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function responseConfirmsApproval(payload: unknown): boolean {
  const root = asRecord(payload);
  const approval = asRecord(root.approval);
  const review = asRecord(root.review);
  const acceptedEdition = asRecord(root.accepted_edition);
  const acceptedReview = asRecord(acceptedEdition.review);
  const reviewDecision = asRecord(root.review_decision);
  const reviewDecisionReview = asRecord(reviewDecision.review);
  const candidates = [
    root.status,
    root.review_status,
    root.acceptance_status,
    approval.status,
    review.status,
    review.decision,
    acceptedReview.status,
    acceptedReview.decision,
    reviewDecision.status,
    reviewDecision.decision,
    reviewDecisionReview.status,
    reviewDecisionReview.decision,
  ];
  return candidates.some((value) => String(value || "").trim().toLowerCase() === "approved");
}

export default function FinalReviewDownloadHandoff() {
  const [pendingPdf, setPendingPdf] = useState<PendingPdf | null>(null);
  const [outcome, setOutcome] = useState<ArtifactOutcome | null>(null);
  const [locale, setLocale] = useState<"en" | "es-MX">("en");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setLocale(requestedLocale);

    const originalClick = HTMLAnchorElement.prototype.click;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const originalFetch = window.fetch;
    const delayedRevocations = new Map<string, number>();
    let reservedPdfWindow: Window | null = null;
    let reservedPdfWindowTimer = 0;
    let approvedPdfPresentationTimer = 0;
    let activePdfAction: PdfAction | null = null;

    function clearApprovedPdfPresentationTimer(): void {
      if (!approvedPdfPresentationTimer) return;
      window.clearTimeout(approvedPdfPresentationTimer);
      approvedPdfPresentationTimer = 0;
    }

    function beginApprovedPdfPresentationTimer(): void {
      clearApprovedPdfPresentationTimer();
      approvedPdfPresentationTimer = window.setTimeout(() => {
        setOutcome((current) => current?.kind === "approval-recorded"
          ? {kind: "approved-pdf-not-presented"}
          : current);
        approvedPdfPresentationTimer = 0;
      }, APPROVED_PDF_PRESENTATION_TIMEOUT_MS);
    }

    function clearReservedPdfWindow(close = false): void {
      if (reservedPdfWindowTimer) {
        window.clearTimeout(reservedPdfWindowTimer);
        reservedPdfWindowTimer = 0;
      }
      if (close && reservedPdfWindow && !reservedPdfWindow.closed) {
        reservedPdfWindow.close();
      }
      reservedPdfWindow = null;
    }

    function reservePdfWindow(event: MouseEvent): void {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const label = String(button.textContent || "").replace(/\s+/g, " ").trim();
      if (!PDF_ACTION_LABELS.has(label)) return;
      const action = pdfActionForLabel(label);
      if (!action) return;

      activePdfAction = action;
      setPendingPdf(null);
      if (action === "review") setOutcome({kind: "draft-pending"});
      if (action === "approve") setOutcome({kind: "approval-pending"});
      if (action === "redownload") setOutcome({kind: "approved-redownload-pending"});

      if (!isIOSFamilyWebKit()) return;
      clearReservedPdfWindow(true);
      const popup = window.open("about:blank", "nico-comprehensive-pdf");
      if (!popup) return;
      reservedPdfWindow = popup;
      try {
        popup.document.title = requestedLocale === "es-MX"
          ? "NICO — preparando PDF verificado"
          : "NICO — preparing verified PDF";
        popup.document.body.textContent = requestedLocale === "es-MX"
          ? "NICO está verificando el PDF exacto. Esta pestaña mostrará el informe cuando esté listo."
          : "NICO is verifying the exact PDF. This tab will show the report when it is ready.";
      } catch {
        // A reserved browsing context is still useful even when its placeholder cannot be edited.
      }
      reservedPdfWindowTimer = window.setTimeout(() => {
        if (reservedPdfWindow === popup) clearReservedPdfWindow(true);
      }, RESERVED_WINDOW_TIMEOUT_MS);
    }

    const trackedFetch: typeof window.fetch = async (input, init) => {
      const approvalRequest = isApprovalRequest(input, init);
      let response: Response;
      try {
        response = await originalFetch(input, init);
      } catch (caught) {
        if (approvalRequest) {
          clearApprovedPdfPresentationTimer();
          clearReservedPdfWindow(true);
          activePdfAction = null;
          setOutcome({kind: "approval-failed"});
        }
        throw caught;
      }

      if (!approvalRequest) return response;

      if (!response.ok) {
        clearApprovedPdfPresentationTimer();
        clearReservedPdfWindow(true);
        activePdfAction = null;
        setOutcome({kind: "approval-failed", httpStatus: response.status});
        return response;
      }

      void response.clone().json().then((payload: unknown) => {
        if (responseConfirmsApproval(payload)) {
          setOutcome({kind: "approval-recorded"});
          beginApprovedPdfPresentationTimer();
        } else {
          clearApprovedPdfPresentationTimer();
          clearReservedPdfWindow(true);
          activePdfAction = null;
          setOutcome({kind: "approval-unconfirmed", httpStatus: response.status});
        }
      }).catch(() => {
        clearApprovedPdfPresentationTimer();
        setOutcome({kind: "approval-unconfirmed", httpStatus: response.status});
      });
      return response;
    };

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        const action = activePdfAction
          || (/approved|accepted-edition/i.test(filename) ? "redownload" : "review");
        setPendingPdf({url: href, filename, action});
        clearApprovedPdfPresentationTimer();
        setOutcome({kind: action === "review" ? "draft-ready" : "approved-pdf-ready"});
        activePdfAction = null;
        if (reservedPdfWindow && !reservedPdfWindow.closed) {
          const targetWindow = reservedPdfWindow;
          clearReservedPdfWindow(false);
          try {
            // iPhone/iPad WebKit can discard a programmatic download that occurs only
            // after awaited approval/hash work. The browsing context was synchronously
            // reserved by the original user click, so navigating it now preserves that
            // user activation and presents the verified PDF instead of silently losing it.
            targetWindow.location.replace(href);
            return;
          } catch {
            targetWindow.close();
          }
        }
      }
      originalClick.call(this);
    }

    function delayedRevoke(url: string): void {
      if (!url.startsWith("blob:")) {
        originalRevokeObjectURL.call(URL, url);
        return;
      }
      const existing = delayedRevocations.get(url);
      if (existing) window.clearTimeout(existing);
      const timer = window.setTimeout(() => {
        originalRevokeObjectURL.call(URL, url);
        delayedRevocations.delete(url);
      }, REVOKE_DELAY_MS);
      delayedRevocations.set(url, timer);
    }

    document.addEventListener("click", reservePdfWindow, true);
    HTMLAnchorElement.prototype.click = guardedClick;
    URL.revokeObjectURL = delayedRevoke;
    window.fetch = trackedFetch;

    return () => {
      document.removeEventListener("click", reservePdfWindow, true);
      clearReservedPdfWindow(true);
      clearApprovedPdfPresentationTimer();
      if (HTMLAnchorElement.prototype.click === guardedClick) {
        HTMLAnchorElement.prototype.click = originalClick;
      }
      if (URL.revokeObjectURL === delayedRevoke) {
        URL.revokeObjectURL = originalRevokeObjectURL;
      }
      if (window.fetch === trackedFetch) {
        window.fetch = originalFetch;
      }
      for (const [url, timer] of delayedRevocations) {
        window.clearTimeout(timer);
        originalRevokeObjectURL.call(URL, url);
      }
      delayedRevocations.clear();
    };
  }, []);

  if (!pendingPdf && !outcome) return null;

  const isSpanish = locale === "es-MX";
  const outcomeMessage = (() => {
    switch (outcome?.kind) {
      case "draft-pending":
        return isSpanish
          ? "NICO está verificando el borrador previo a la aprobación. Aún no existe un PDF final aprobado."
          : "NICO is verifying the pre-approval draft. No approved-final PDF exists yet.";
      case "draft-ready":
        return isSpanish
          ? "BORRADOR verificado. La aprobación humana sigue pendiente; este archivo no es el PDF FINAL APROBADO."
          : "Verified DRAFT. Human approval is still pending; this file is not the APPROVED FINAL PDF.";
      case "approval-pending":
        return isSpanish
          ? "Registrando la aprobación. No se considerará creado ningún PDF final aprobado hasta que NICO confirme la aprobación."
          : "Recording approval. No approved-final PDF is considered created until NICO confirms the approval.";
      case "approval-failed":
        return isSpanish
          ? `La aprobación NO se completó. Esta acción no creó un PDF final aprobado${outcome.httpStatus ? ` (HTTP ${outcome.httpStatus})` : ""}. La entrega permanece bloqueada.`
          : `Approval DID NOT complete. This action did not create an approved-final PDF${outcome.httpStatus ? ` (HTTP ${outcome.httpStatus})` : ""}. Delivery remains blocked.`;
      case "approval-unconfirmed":
        return isSpanish
          ? "El servidor respondió a la solicitud, pero la respuesta no confirmó una edición aprobada. No trates ningún archivo como final aprobado."
          : "The server answered the approval request, but the response did not confirm an approved edition. Do not treat any file as an approved final.";
      case "approval-recorded":
        return isSpanish
          ? "La aprobación está registrada para la edición exacta. NICO todavía está verificando y presentando el PDF FINAL APROBADO. La entrega sigue separada y bloqueada."
          : "Approval is recorded for the exact edition. NICO is still verifying and presenting the APPROVED FINAL PDF. Delivery remains separate and blocked.";
      case "approved-pdf-not-presented":
        return isSpanish
          ? "La aprobación está registrada, pero el PDF FINAL APROBADO aún no fue presentado al navegador. Usa “Descargar nuevamente el PDF aprobado”. La entrega permanece bloqueada."
          : "Approval is recorded, but the APPROVED FINAL PDF was not handed to the browser. Use “Download approved PDF again”. Delivery remains blocked.";
      case "approved-pdf-ready":
        return isSpanish
          ? "PDF FINAL APROBADO verificado y listo para abrir. La autorización de entrega al cliente sigue siendo una acción separada."
          : "APPROVED FINAL PDF verified and ready to open. Client-delivery authorization remains a separate action.";
      case "approved-redownload-pending":
        return isSpanish
          ? "Recuperando y verificando nuevamente el PDF FINAL APROBADO ya registrado. La entrega no cambia."
          : "Retrieving and re-verifying the already recorded APPROVED FINAL PDF. Delivery is unchanged.";
      default:
        return "";
    }
  })();

  return (
    <aside
      role="status"
      aria-live="polite"
      data-final-review-pdf-handoff={pendingPdf ? "ready" : "pending"}
      data-final-review-artifact-outcome={outcome?.kind || "unknown"}
      style={{
        position: "fixed",
        left: "max(16px, env(safe-area-inset-left))",
        right: "max(16px, env(safe-area-inset-right))",
        bottom: "max(16px, env(safe-area-inset-bottom))",
        zIndex: 1000,
        margin: "0 auto",
        maxWidth: 760,
        padding: 16,
        borderRadius: 14,
        border: "1px solid rgba(148, 163, 184, 0.45)",
        background: "rgba(15, 23, 42, 0.97)",
        boxShadow: "0 18px 48px rgba(0, 0, 0, 0.35)",
        color: "#f8fafc",
      }}
    >
      <strong style={{display: "block", marginBottom: 6}}>
        {pendingPdf ? (isSpanish ? "El PDF está listo" : "PDF is ready") : (isSpanish ? "Estado exacto del artefacto" : "Exact artifact status")}
      </strong>
      <span style={{display: "block", marginBottom: pendingPdf ? 8 : 0, lineHeight: 1.45, fontWeight: 650}}>
        {outcomeMessage}
      </span>
      {pendingPdf ? <>
        <span style={{display: "block", marginBottom: 12, lineHeight: 1.45, opacity: 0.9}}>
          {isSpanish
            ? `Archivo: ${pendingPdf.filename}. Si iPhone o el navegador no abrió el informe automáticamente, toca el enlace de abajo.`
            : `File: ${pendingPdf.filename}. If iPhone or the browser did not open the report automatically, tap the link below.`}
        </span>
        <a
          href={pendingPdf.url}
          download={pendingPdf.filename}
          target="_blank"
          rel="noopener noreferrer"
          data-final-review-pdf-open="true"
          style={{
            display: "inline-block",
            padding: "10px 14px",
            borderRadius: 10,
            background: "#f8fafc",
            color: "#0f172a",
            fontWeight: 700,
            textDecoration: "none",
          }}
        >
          {isSpanish ? "Abrir PDF" : "Open PDF"}
        </a>
      </> : null}
    </aside>
  );
}
