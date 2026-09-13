"use client";

import {useEffect} from "react";

const REVOKE_DELAY_MS = 5 * 60 * 1000;
const PDF_ACTION_FINISHED = "nico:pdf-action-finished";
const PDF_ACTION_LABELS = new Set([
  "Download final assessment PDF",
  "Approve exact downloaded report",
  "Descargar PDF final de la evaluación",
  "Aprobar informe exacto descargado",
  "Download report for review",
  "Download approved final PDF",
  "Approve and download final PDF",
  "Descargar informe para revisión",
  "Descargar PDF final aprobado",
  "Aprobar y descargar PDF final",
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
    let reservationFailed = false;

    function clearReservedPdfWindow(close = false): void {
      if (close && reservedPdfWindow && !reservedPdfWindow.closed) {
        reservedPdfWindow.close();
      }
      reservedPdfWindow = null;
      reservationFailed = false;
    }

    function finishPdfAction(): void { clearReservedPdfWindow(true); }

    function reservePdfWindow(event: MouseEvent): void {
      if (!isIOSFamilyWebKit()) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("button");
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      const label = String(button.textContent || "").replace(/\s+/g, " ").trim();
      // Prefer the stable action marker; keep legacy labels for mixed cached builds.
      if (button.dataset.nicoPdfAction !== "true" && !PDF_ACTION_LABELS.has(label)) return;

      if (reservedPdfWindow && !reservedPdfWindow.closed) return;
      const popup = window.open("about:blank", "nico-comprehensive-pdf");
      reservationFailed = !popup;
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
    }

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        if (isIOSFamilyWebKit() && (reservationFailed || !reservedPdfWindow || reservedPdfWindow.closed)) {
          throw new Error(requestedLocale === "es-MX"
            ? "No se pudo presentar el PDF. Vuelva a intentar la descarga."
            : "The PDF could not be presented. Retry the download.");
        }
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
            throw new Error(requestedLocale === "es-MX"
              ? "No se pudo presentar el PDF. Vuelva a intentar la descarga."
              : "The PDF could not be presented. Retry the download.");
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
    document.addEventListener(PDF_ACTION_FINISHED, finishPdfAction);
    HTMLAnchorElement.prototype.click = guardedClick;
    URL.revokeObjectURL = delayedRevoke;

    return () => {
      document.removeEventListener("click", reservePdfWindow, true);
      document.removeEventListener(PDF_ACTION_FINISHED, finishPdfAction);
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
