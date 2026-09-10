"use client";

import {useEffect, useState} from "react";

type PendingPdf = {
  url: string;
  filename: string;
};

const REVOKE_DELAY_MS = 5 * 60 * 1000;
const RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000;
const APPROVE_LABELS = new Set([
  "Approve and download final PDF",
  "Aprobar y descargar PDF final",
]);

export default function FinalReviewDownloadHandoff() {
  const [pendingPdf, setPendingPdf] = useState<PendingPdf | null>(null);
  const [locale, setLocale] = useState<"en" | "es-MX">("en");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setLocale(query.get("lang") === "es-MX" ? "es-MX" : "en");

    const originalClick = HTMLAnchorElement.prototype.click;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const delayedRevocations = new Map<string, number>();
    let reservedPdfWindow: Window | null = null;
    let reservedPdfWindowTimeout: number | null = null;

    function clearReservedWindow(closeWindow: boolean): void {
      if (reservedPdfWindowTimeout !== null) {
        window.clearTimeout(reservedPdfWindowTimeout);
        reservedPdfWindowTimeout = null;
      }
      if (closeWindow && reservedPdfWindow && !reservedPdfWindow.closed) {
        try {
          reservedPdfWindow.close();
        } catch {
          // Browser policy may prevent closing a window after navigation.
        }
      }
      reservedPdfWindow = null;
    }

    function reservePdfWindow(event: MouseEvent): void {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const label = String(button.textContent || "").trim();
      if (!APPROVE_LABELS.has(label)) return;

      clearReservedWindow(true);
      try {
        // iPhone/WebKit will often reject a new tab created after the asynchronous
        // approval request finishes. Reserve the tab while the original user gesture
        // is still active, then navigate that already-open tab when the verified PDF
        // Blob is produced.
        reservedPdfWindow = window.open("about:blank", "_blank");
        if (reservedPdfWindow) {
          reservedPdfWindow.document.title = "NICO approved final PDF";
          reservedPdfWindow.document.body.textContent =
            query.get("lang") === "es-MX"
              ? "NICO está preparando el PDF final aprobado…"
              : "NICO is preparing the approved final PDF…";
          reservedPdfWindowTimeout = window.setTimeout(() => {
            clearReservedWindow(true);
          }, RESERVED_WINDOW_TIMEOUT_MS);
        }
      } catch {
        reservedPdfWindow = null;
      }
    }

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        setPendingPdf({url: href, filename});
        if (reservedPdfWindow && !reservedPdfWindow.closed) {
          try {
            reservedPdfWindow.location.href = href;
            clearReservedWindow(false);
          } catch {
            clearReservedWindow(true);
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

    return () => {
      document.removeEventListener("click", reservePdfWindow, true);
      clearReservedWindow(true);
      if (HTMLAnchorElement.prototype.click === guardedClick) {
        HTMLAnchorElement.prototype.click = originalClick;
      }
      if (URL.revokeObjectURL === delayedRevoke) {
        URL.revokeObjectURL = originalRevokeObjectURL;
      }
      for (const [url, timer] of delayedRevocations) {
        window.clearTimeout(timer);
        originalRevokeObjectURL.call(URL, url);
      }
      delayedRevocations.clear();
    };
  }, []);

  if (!pendingPdf) return null;

  const isSpanish = locale === "es-MX";
  return (
    <aside
      role="status"
      aria-live="polite"
      data-final-review-pdf-handoff="ready"
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
        {isSpanish ? "El PDF final aprobado está listo" : "Approved final PDF is ready"}
      </strong>
      <span style={{display: "block", marginBottom: 12, lineHeight: 1.45}}>
        {isSpanish
          ? "Si iPhone o el navegador no abrió el informe automáticamente, toca el enlace de abajo."
          : "If iPhone or the browser did not open the report automatically, tap the link below."}
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
        {isSpanish ? "Abrir PDF final aprobado" : "Open approved final PDF"}
      </a>
    </aside>
  );
}
