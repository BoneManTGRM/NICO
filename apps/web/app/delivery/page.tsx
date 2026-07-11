"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type AccessMetadata = {
  access_id?: string;
  status?: string;
  recipient_label?: string;
  expires_at?: string;
  max_downloads?: number;
  download_count?: number;
  downloads_remaining?: number;
};

type DeliveryMetadata = {
  pdf_filename?: string;
  approver?: string;
  approved_at?: string;
  disclosure?: string;
  pdf_sha256?: string;
};

type InspectResponse = {
  status?: string;
  available?: boolean;
  access?: AccessMetadata;
  delivery?: DeliveryMetadata;
  detail?: {message?: string};
};

function savePdf(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "nico-full-assessment-approved.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function ApprovedDeliveryPage() {
  const [token, setToken] = useState("");
  const [metadata, setMetadata] = useState<InspectResponse | null>(null);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("Validating the approved-delivery link...");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const rawToken = params.get("token") || "";
    window.history.replaceState(null, "", window.location.pathname);
    setToken(rawToken);
    if (!API_URL) {
      setStatus("blocked");
      setMessage("The NICO delivery service is not configured for this deployment.");
      return;
    }
    if (!rawToken) {
      setStatus("blocked");
      setMessage("This approved-delivery link is unavailable.");
      return;
    }

    let active = true;
    async function inspect() {
      try {
        const response = await fetch(`${API_URL}/delivery/approved/inspect`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({token: rawToken}),
          cache: "no-store",
          referrerPolicy: "no-referrer",
        });
        const data = await response.json() as InspectResponse;
        if (!active) return;
        if (!response.ok || !data.available) throw new Error(data.detail?.message || "This approved-delivery link is unavailable.");
        setMetadata(data);
        setStatus("available");
        setMessage("The approved artifact passed current identity and integrity verification.");
      } catch (error) {
        if (!active) return;
        setStatus("blocked");
        setMessage(error instanceof Error ? error.message : "This approved-delivery link is unavailable.");
      }
    }
    void inspect();
    return () => { active = false; };
  }, []);

  async function download() {
    if (!token || downloading || status !== "available") return;
    setDownloading(true);
    setMessage("Re-verifying the artifact and authorizing this download...");
    try {
      const response = await fetch(`${API_URL}/delivery/approved/redeem`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token}),
        cache: "no-store",
        referrerPolicy: "no-referrer",
      });
      if (!response.ok) {
        let errorMessage = "This approved-delivery link is unavailable.";
        try {
          const data = await response.json() as {detail?: {message?: string}};
          errorMessage = data.detail?.message || errorMessage;
        } catch {
          // Keep the generic public error.
        }
        throw new Error(errorMessage);
      }
      const blob = await response.blob();
      if (blob.type !== "application/pdf") throw new Error("The approved PDF response failed content validation.");
      savePdf(blob, metadata?.delivery?.pdf_filename || "nico-full-assessment-approved.pdf");
      const remaining = Math.max(0, Number(metadata?.access?.downloads_remaining || 1) - 1);
      setMetadata((current) => current ? {...current, access: {...current.access, downloads_remaining: remaining, download_count: Number(current.access?.download_count || 0) + 1}} : current);
      setMessage(remaining > 0 ? `Download authorized. ${remaining} permitted download(s) remain.` : "Download authorized. This link has reached its permitted download limit.");
      if (remaining === 0) setStatus("exhausted");
    } catch (error) {
      setStatus("blocked");
      setMessage(error instanceof Error ? error.message : "This approved-delivery link is unavailable.");
    } finally {
      setDownloading(false);
    }
  }

  const available = status === "available" && Boolean(metadata?.available);

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Secure Delivery</p>
      <h1>Approved Full Assessment</h1>
      <p className="lead">This page validates the access grant and re-verifies the exact human-approved PDF before every download.</p>
    </section>

    <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Delivery status</p><h2>{metadata?.delivery?.pdf_filename || "Approved artifact"}</h2></div>
        <span className={available ? "status green" : status === "loading" ? "status yellow" : "status red"}>{status}</span>
      </div>
      <p className={available ? "warning-box" : "error-box"}>{message}</p>

      {metadata?.delivery ? <>
        <div className="grid four target-grid">
          <article><b>Approved by</b><span>{metadata.delivery.approver || "Human reviewer"}</span></article>
          <article><b>Approved at</b><span>{metadata.delivery.approved_at || "Not recorded"}</span></article>
          <article><b>Link expires</b><span>{metadata.access?.expires_at || "Not recorded"}</span></article>
          <article><b>Downloads remaining</b><span>{metadata.access?.downloads_remaining ?? 0}</span></article>
        </div>
        {metadata.access?.recipient_label ? <p className="muted">Prepared for: {metadata.access.recipient_label}</p> : null}
        <details className="help-details"><summary>Artifact integrity</summary><pre className="json-block">{JSON.stringify({pdf_sha256: metadata.delivery.pdf_sha256, access_id: metadata.access?.access_id, disclosure: metadata.delivery.disclosure}, null, 2)}</pre></details>
      </> : null}

      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!available || downloading} onClick={download}>{downloading ? "Authorizing..." : "Download verified approved PDF"}</button>
      </div>
      <p className="muted">The access token was removed from the browser address after validation. It is not displayed on this page.</p>
    </section>
  </main>;
}
