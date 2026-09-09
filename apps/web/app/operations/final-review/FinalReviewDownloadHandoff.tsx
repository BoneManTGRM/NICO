"use client";

import {useEffect, useState} from "react";

type PendingPdf = {
  url: string;
  filename: string;
};

const REVOKE_DELAY_MS = 5 * 60 * 1000;

export default function FinalReviewDownloadHandoff() {
  const [pendingPdf, setPendingPdf] = useState<PendingPdf | null>(null);
  const [locale, setLocale] = useState<"en" | "es-MX">("en");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setLocale(query.get("lang") === "es-MX" ? "es-MX" : "en");

    const originalClick = HTMLAnchorElement.prototype.click;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const delayedRevocations = new Map<string, number>();

    function guardedClick(this: HTMLAnchorElement): void {
      const href = this.href || "";
      const filename = this.download || "nico-comprehensive-report.pdf";
      if (href.startsWith("blob:") && filename.toLowerCase().endsWith(".pdf")) {
        setPendingPdf({url: href, filename});
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

    HTMLAnchorElement.prototype.click = guardedClick;
    URL.revokeObjectURL = delayedRevoke;

    return () => {
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
        {isSpanish ? "El PDF está listo" : "PDF ready"}
      </strong>
      <span style={{display: "block", marginBottom: 12, lineHeight: 1.45}}>
        {isSpanish
          ? "Si el navegador no abrió o guardó el informe automáticamente, usa este enlace explícito."
          : "If the browser did not open or save the report automatically, use this explicit link."}
      </span>
      <a
        href={pendingPdf.url}
        download={pendingPdf.filename}
        target="_blank"
        rel="noopener noreferrer"
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
        {isSpanish ? "Abrir / descargar PDF" : "Open / download PDF"}
      </a>
    </aside>
  );
}
