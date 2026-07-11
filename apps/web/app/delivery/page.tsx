"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

const ACKNOWLEDGMENT_STATEMENT = "I acknowledge that I received access to the NICO Full Assessment identified by this delivery receipt. This acknowledgment confirms receipt only; it is not technical approval, agreement with every finding, a waiver, legal acceptance, or acceptance of liability.";

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

type DeliveryReceipt = {
  receipt_id: string;
  receipt_sha256: string;
  receipt_version: string;
  delivered_at: string;
  download_number: number;
  persistence: string;
  pdf_sha256: string;
  access_id: string;
  recipient_label: string;
};

type DeliveryAcknowledgment = {
  acknowledgment_id?: string;
  status?: string;
  acknowledgment_version?: string;
  receipt_id?: string;
  receipt_sha256?: string;
  access_id?: string;
  run_id?: string;
  report_id?: string;
  approval_id?: string;
  recipient_label?: string;
  acknowledged_by?: string;
  acknowledged_at?: string;
  statement?: string;
  statement_sha256?: string;
  pdf_sha256?: string;
  token_fingerprint?: string;
  acknowledgment_sha256?: string;
  verified?: boolean;
  persistence?: {durable?: boolean; adapter?: string; note?: string};
  receipt_only?: boolean;
  technical_approval?: boolean;
  agreement_with_findings?: boolean;
  legal_acceptance?: boolean;
};

type InspectResponse = {
  status?: string;
  available?: boolean;
  access?: AccessMetadata;
  delivery?: DeliveryMetadata;
  detail?: {message?: string};
};

function saveJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

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
  const [receipt, setReceipt] = useState<DeliveryReceipt | null>(null);
  const [acknowledgment, setAcknowledgment] = useState<DeliveryAcknowledgment | null>(null);
  const [acknowledgedBy, setAcknowledgedBy] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [acknowledging, setAcknowledging] = useState(false);
  const [acknowledgmentError, setAcknowledgmentError] = useState("");
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
        setAcknowledgedBy(data.access?.recipient_label || "");
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
    setMessage("Re-verifying the artifact, recording the delivery receipt, and authorizing this download...");
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

      const issuedReceipt: DeliveryReceipt = {
        receipt_id: response.headers.get("X-NICO-Receipt-ID") || "",
        receipt_sha256: response.headers.get("X-NICO-Receipt-SHA256") || "",
        receipt_version: response.headers.get("X-NICO-Receipt-Version") || "",
        delivered_at: response.headers.get("X-NICO-Delivered-At") || "",
        download_number: Number(response.headers.get("X-NICO-Download-Number") || 0),
        persistence: response.headers.get("X-NICO-Receipt-Persistence") || "unknown",
        pdf_sha256: response.headers.get("X-NICO-PDF-SHA256") || metadata?.delivery?.pdf_sha256 || "",
        access_id: metadata?.access?.access_id || "",
        recipient_label: metadata?.access?.recipient_label || "",
      };
      if (!issuedReceipt.receipt_id || !issuedReceipt.receipt_sha256 || !issuedReceipt.delivered_at || issuedReceipt.download_number < 1) {
        throw new Error("The PDF response did not include a complete verified delivery receipt.");
      }

      const blob = await response.blob();
      if (blob.type !== "application/pdf") throw new Error("The approved PDF response failed content validation.");
      savePdf(blob, metadata?.delivery?.pdf_filename || "nico-full-assessment-approved.pdf");
      setReceipt(issuedReceipt);
      setAcknowledgment(null);
      setAcknowledgmentError("");
      const remaining = Math.max(0, Number(metadata?.access?.downloads_remaining || 1) - 1);
      setMetadata((current) => current ? {...current, access: {...current.access, downloads_remaining: remaining, download_count: Number(current.access?.download_count || 0) + 1}} : current);
      setMessage(remaining > 0 ? `Download authorized and receipt recorded. ${remaining} permitted download(s) remain.` : "Download authorized and receipt recorded. This link has reached its permitted download limit.");
      if (remaining === 0) setStatus("exhausted");
    } catch (error) {
      setStatus("blocked");
      setMessage(error instanceof Error ? error.message : "This approved-delivery link is unavailable.");
    } finally {
      setDownloading(false);
    }
  }

  async function acknowledgeReceipt() {
    if (!token || !receipt || !acknowledged || acknowledgedBy.trim().length < 2 || acknowledging) return;
    setAcknowledgmentError("");
    setAcknowledging(true);
    try {
      const response = await fetch(`${API_URL}/delivery/approved/acknowledge`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token, receipt_id: receipt.receipt_id, acknowledged_by: acknowledgedBy.trim(), acknowledged: true}),
        cache: "no-store",
        referrerPolicy: "no-referrer",
      });
      const data = await response.json() as {status?: string; acknowledgment?: DeliveryAcknowledgment; detail?: {message?: string}};
      if (!response.ok || data.status !== "acknowledged" || !data.acknowledgment?.verified) {
        throw new Error(data.detail?.message || "The receipt acknowledgment could not be recorded and verified.");
      }
      setAcknowledgment(data.acknowledgment);
    } catch (error) {
      setAcknowledgmentError(error instanceof Error ? error.message : "The receipt acknowledgment could not be recorded.");
    } finally {
      setAcknowledging(false);
    }
  }

  const available = status === "available" && Boolean(metadata?.available);

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Secure Delivery</p>
      <h1>Approved Full Assessment</h1>
      <p className="lead">This page validates the access grant, re-verifies the exact human-approved PDF, and records a hash-bound receipt before every download.</p>
    </section>

    <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Delivery status</p><h2>{metadata?.delivery?.pdf_filename || "Approved artifact"}</h2></div>
        <span className={available || receipt ? "status green" : status === "loading" ? "status yellow" : "status red"}>{receipt ? "delivered" : status}</span>
      </div>
      <p className={available || receipt ? "warning-box" : "error-box"}>{message}</p>

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
      <p className="muted">The access token was removed from the browser address after validation. It is not displayed on this page or included in delivery records.</p>
    </section>

    {receipt ? <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Delivery receipt</p><h2>{receipt.receipt_id}</h2></div>
        <span className="status green">recorded</span>
      </div>
      <p className="warning-box">This receipt binds the completed download to the exact approved PDF hash, access grant, recipient label, and delivery time. It contains no raw access token.</p>
      <div className="grid four target-grid">
        <article><b>Delivered at</b><span>{receipt.delivered_at}</span></article>
        <article><b>Download number</b><span>{receipt.download_number}</span></article>
        <article><b>Receipt storage</b><span>{receipt.persistence}</span></article>
        <article><b>Receipt version</b><span>{receipt.receipt_version}</span></article>
      </div>
      <details className="help-details"><summary>Receipt integrity</summary><pre className="json-block">{JSON.stringify(receipt, null, 2)}</pre></details>
      <div className="report-actions"><button type="button" onClick={() => saveJson(`nico-delivery-receipt-${receipt.receipt_id}.json`, receipt)}>Download receipt JSON</button></div>
    </section> : null}

    {receipt ? <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">Optional receipt acknowledgment</p><h2>{acknowledgment?.acknowledgment_id || "Confirm receipt"}</h2></div>
        <span className={acknowledgment?.verified ? "status green" : "status yellow"}>{acknowledgment?.verified ? "verified" : "not recorded"}</span>
      </div>
      <p className="warning-box">{ACKNOWLEDGMENT_STATEMENT}</p>
      {!acknowledgment ? <>
        <div className="form-grid"><label>Name or identifying label<input value={acknowledgedBy} onChange={(event) => setAcknowledgedBy(event.target.value)} placeholder="Recipient name or organization role" /></label></div>
        <label><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /> I confirm the receipt-only statement above.</label>
        <div className="report-actions"><button type="button" className="primary-button" disabled={!acknowledged || acknowledgedBy.trim().length < 2 || acknowledging} onClick={acknowledgeReceipt}>{acknowledging ? "Recording acknowledgment..." : "Acknowledge receipt"}</button></div>
        {acknowledgmentError ? <p className="error-box">{acknowledgmentError}</p> : null}
      </> : <>
        <div className="grid four target-grid">
          <article><b>Acknowledged by</b><span>{acknowledgment.acknowledged_by || "Not recorded"}</span></article>
          <article><b>Acknowledged at</b><span>{acknowledgment.acknowledged_at || "Not recorded"}</span></article>
          <article><b>Receipt only</b><span>{String(acknowledgment.receipt_only)}</span></article>
          <article><b>Technical approval</b><span>{String(acknowledgment.technical_approval)}</span></article>
        </div>
        <details className="help-details"><summary>Acknowledgment integrity</summary><pre className="json-block">{JSON.stringify(acknowledgment, null, 2)}</pre></details>
        <div className="report-actions"><button type="button" onClick={() => saveJson(`nico-delivery-acknowledgment-${acknowledgment.acknowledgment_id}.json`, acknowledgment)}>Download acknowledgment JSON</button></div>
      </>}
      <p className="muted">Acknowledgment is optional and does not alter the report, its technical approval, findings, evidence limitations, remediation requirements, or allocation of responsibility.</p>
    </section> : null}
  </main>;
}
