"use client";

import {useEffect, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const ACKNOWLEDGEMENT = "I acknowledge receipt of this NICO Mid Assessment and the disclosed evidence limitations.";

type DeliveryInfo = {
  status?: string;
  available?: boolean;
  access?: {
    access_id?: string;
    recipient_label?: string;
    expires_at?: string;
    downloads_remaining?: number;
  };
  delivery?: {
    report_id?: string;
    pdf_filename?: string;
    pdf_sha256?: string;
    approval_id?: string;
    approval_identity_sha256?: string;
    review_packet_sha256?: string;
    snapshot_commit_sha?: string;
    approved_by?: string;
    approved_at?: string;
    disclosure?: string;
    acknowledgement_required?: boolean;
  };
  detail?: {message?: string};
};

function savePdf(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function MidDeliveryPage() {
  const [token, setToken] = useState("");
  const [delivery, setDelivery] = useState<DeliveryInfo | null>(null);
  const [recipientName, setRecipientName] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<{id: string; sha: string; remaining: string} | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const value = params.get("token") || "";
    setToken(value);
    if (value) void inspect(value);
  }, []);

  async function inspect(value = token) {
    if (!API_URL || !value || loading) return;
    setError("");
    setDelivery(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/delivery/inspect`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token: value}),
        cache: "no-store",
      });
      const data = await response.json() as DeliveryInfo;
      if (!response.ok || !data.available) throw new Error(data.detail?.message || "This Mid delivery link is unavailable.");
      setDelivery(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This Mid delivery link is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  async function download() {
    if (!API_URL || !token || !delivery?.delivery || !acknowledged || recipientName.trim().length < 2 || loading) return;
    setError("");
    setReceipt(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/delivery/redeem`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          token,
          recipient_name: recipientName.trim(),
          acknowledged: true,
          acknowledgement_text: ACKNOWLEDGEMENT,
        }),
        cache: "no-store",
      });
      if (!response.ok) {
        const data = await response.json() as {detail?: {message?: string}};
        throw new Error(data.detail?.message || "The approved Mid PDF could not be downloaded.");
      }
      const reportId = response.headers.get("X-NICO-Report-ID") || "";
      const pdfSha = response.headers.get("X-NICO-PDF-SHA256") || "";
      const approvalId = response.headers.get("X-NICO-Approval-ID") || "";
      const approvalIdentity = response.headers.get("X-NICO-Approval-Identity-SHA256") || "";
      const reviewPacket = response.headers.get("X-NICO-Review-Packet-SHA256") || "";
      if (
        reportId !== delivery.delivery.report_id ||
        pdfSha !== delivery.delivery.pdf_sha256 ||
        approvalId !== delivery.delivery.approval_id ||
        approvalIdentity !== delivery.delivery.approval_identity_sha256 ||
        reviewPacket !== delivery.delivery.review_packet_sha256
      ) {
        throw new Error("The downloaded PDF did not match the approved delivery identity.");
      }
      const blob = await response.blob();
      if (!blob.size || blob.type !== "application/pdf") throw new Error("The approved PDF failed content validation.");
      savePdf(blob, delivery.delivery.pdf_filename || "nico-mid-assessment-APPROVED.pdf");
      setReceipt({
        id: response.headers.get("X-NICO-Delivery-Receipt-ID") || "",
        sha: response.headers.get("X-NICO-Delivery-Receipt-SHA256") || "",
        remaining: response.headers.get("X-NICO-Downloads-Remaining") || "0",
      });
      await inspect(token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The approved Mid PDF could not be downloaded.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Secure client delivery</h1>
      <p className="lead">Verify the approved artifact, acknowledge the disclosed limitations, and receive an auditable download receipt.</p>
    </section>

    {!token ? <section className="section panel"><p className="error-box">This page requires the private delivery token contained in the original link.</p></section> : null}
    {loading && !delivery ? <section className="section panel"><p>Verifying delivery access...</p></section> : null}
    {error ? <section className="section panel"><p className="error-box">{error}</p></section> : null}

    {delivery?.available ? <>
      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Approved artifact</p><h2>{delivery.access?.recipient_label || "Authorized recipient"}</h2></div><span className="status green">Verified</span></div>
        <div className="grid four target-grid">
          <article><b>Report ID</b><span>{delivery.delivery?.report_id}</span></article>
          <article><b>Approved by</b><span>{delivery.delivery?.approved_by || "Recorded reviewer"}</span></article>
          <article><b>Expires</b><span>{delivery.access?.expires_at}</span></article>
          <article><b>Downloads remaining</b><span>{delivery.access?.downloads_remaining ?? 0}</span></article>
        </div>
        <p className="warning-box">{delivery.delivery?.disclosure}</p>
        <details className="help-details"><summary>Integrity identity</summary><pre className="json-block">{JSON.stringify({
          report_id: delivery.delivery?.report_id,
          pdf_sha256: delivery.delivery?.pdf_sha256,
          approval_id: delivery.delivery?.approval_id,
          approval_identity_sha256: delivery.delivery?.approval_identity_sha256,
          review_packet_sha256: delivery.delivery?.review_packet_sha256,
          snapshot_commit_sha: delivery.delivery?.snapshot_commit_sha,
          approved_at: delivery.delivery?.approved_at,
        }, null, 2)}</pre></details>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Recipient acknowledgement</p><h2>Confirm receipt before download</h2></div><span className={acknowledged ? "status green" : "status yellow"}>{acknowledged ? "acknowledged" : "required"}</span></div>
        <label>Recipient name<input value={recipientName} onChange={(event) => setRecipientName(event.target.value)} /></label>
        <label className="check-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />{ACKNOWLEDGEMENT}</label>
        <button type="button" className="primary-button" disabled={!acknowledged || recipientName.trim().length < 2 || loading || (delivery.access?.downloads_remaining ?? 0) < 1} onClick={download}>{loading ? "Verifying and recording receipt..." : "Download approved Mid PDF"}</button>
        {receipt ? <div className="success-box"><b>Download receipt recorded.</b><br />Receipt ID: {receipt.id}<br />Receipt SHA-256: {receipt.sha}<br />Downloads remaining: {receipt.remaining}</div> : null}
      </section>
    </> : null}
  </main>;
}
