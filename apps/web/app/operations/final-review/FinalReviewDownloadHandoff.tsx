"use client";

import {useEffect} from "react";

const REVOKE_DELAY_MS = 5 * 60 * 1000;
const RESERVED_WINDOW_TIMEOUT_MS = 60 * 1000;
const PDF_ACTION_LABELS = new Set([
  "Download final assessment PDF",
  "Approve exact downloaded report",
  "Descargar PDF final de la evaluación",
  "Aprobar informe exacto descargado",
]);

function isIOSFamilyWebKit(): boolean {
  const userAgent = navigator.userAgent || "";
  return /iPad|iPhone|iPod/i.test(userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export default function FinalReviewDownloadHandoff() {
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale = query.get("lang") === "es-MX" ? "es-MX" : "en";

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
        // The synchronously reserved browsing context is still useful even if its
        // short-lived placeholder cannot be edited.
      }
      reservedPdfWindowTimer = window.setTimeout(() => {
        if (reservedPdfWindow === popup) clearReservedPdfWindow(true);
      }, RESERVED_WINDOW_TIMEOUT_MS);
    }

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        if (reservedPdfWindow && !reservedPdfWindow.closed) {
          const targetWindow = reservedPdfWindow;
          clearReservedPdfWindow(false);
          try {
            // The browsing context was synchronously reserved by the original
            // physical tap. Navigate it only after the PDF has passed the existing
            // exact-artifact integrity checks. No second-tap handoff is rendered.
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

  return null;
}
