"use client";

import {useEffect, useState} from "react";

type PendingPdf = {
  url: string;
  filename: string;
};

const REVOKE_DELAY_MS = 5 * 60 * 1000;
const RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000;
const PDF_ACTION_LABELS = new Set([
  "Download exact PDF to review",
  "Approve and download final PDF",
  "Download approved PDF again",
  "Descargar PDF exacto para revisión",
  "Aprobar y descargar PDF final",
  "Descargar nuevamente el PDF aprobado",
]);

function isIOSFamilyWebKit(): boolean {
  const userAgent = navigator.userAgent || "";
  return /iPad|iPhone|iPod/i.test(userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export default function FinalReviewDownloadHandoff() {
  const [pendingPdf, setPendingPdf] = useState<PendingPdf | null>(null);
  const [locale, setLocale] = useState<"en" | "es-MX">("en");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setLocale(requestedLocale);

    const originalClick = HTMLAnchorElement.prototype.click;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const delayedRevocations = new Map<string, number>();
    let reservedPdfWindow: Window | null = null;
    let reservedPdfWindowTimer = 0;

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
      if (!isIOSFamilyWebKit()) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const label = String(button.textContent || "").replace(/\s+/g, " ").trim();
      if (!PDF_ACTION_LABELS.has(label)) return;

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

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        setPendingPdf({url: href, filename});
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

    return () => {
      document.removeEventListener("click", reservePdfWindow, true);
      clearReservedPdfWindow(true);
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
        bottom: "max(8px, env(safe-area-inset-bottom))",
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
        {isSpanish ? "El PDF está listo" : "PDF is ready"}
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
        {isSpanish ? "Abrir PDF" : "Open PDF"}
      </a>
    </aside>
  );
}
