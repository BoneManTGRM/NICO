"use client";

import {useState} from "react";

import {MidIdentityPanel, MidStageNavigation, useMidWorkspace} from "../MidWorkspaceContext";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type Access = {
  access_id?: string;
  status?: string;
  recipient_label?: string;
  created_by?: string;
  created_at?: string;
  expires_at?: string;
  max_downloads?: number;
  download_count?: number;
  downloads_remaining?: number;
  last_redeemed_at?: string;
  revoked_at?: string;
  token_fingerprint?: string;
  artifact_identity_sha256?: string;
};
type Receipt = {
  receipt_id?: string;
  receipt_sha256?: string;
  access_id?: string;
  recipient_label?: string;
  recipient_name?: string;
  downloaded_at?: string;
  download_ordinal?: number;
  pdf_sha256?: string;
  acknowledgement_sha256?: string;
};
type CreateResponse = {status?: string; token?: string; fragment_path?: string; access?: Access; warning?: string; detail?: {message?: string}};

function statusClass(value?: string) {
  const normalized = String(value || "").toLowerCase();
  if (["active", "created"].includes(normalized)) return "status green";
  if (["revoked", "expired", "blocked"].includes(normalized)) return "status red";
  return "status gray";
}

export default function MidDeliveryAdminPage() {
  const {runId, customerId, projectId, adminToken, reviewer: createdBy} = useMidWorkspace();
  const [recipientLabel, setRecipientLabel] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [maxDownloads, setMaxDownloads] = useState(1);
  const [access, setAccess] = useState<Access[]>([]);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [privateLink, setPrivateLink] = useState("");
  const [rawToken, setRawToken] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function readJson(response: Response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.message || `Mid delivery request failed with ${response.status}.`);
    return data;
  }

  async function refresh() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
      const [accessResponse, receiptResponse] = await Promise.all([
        fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/delivery/access?${params.toString()}`, {headers: {"X-NICO-Admin-Token": adminToken}, cache: "no-store"}),
        fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/delivery/receipts?${params.toString()}`, {headers: {"X-NICO-Admin-Token": adminToken}, cache: "no-store"}),
      ]);
      const accessData = await readJson(accessResponse) as {access?: Access[]};
      const receiptData = await readJson(receiptResponse) as {receipts?: Receipt[]};
      setAccess(accessData.access || []);
      setReceipts(receiptData.receipts || []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid delivery status could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function createAccess() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || recipientLabel.trim().length < 2 || createdBy.trim().length < 2 || loading) return;
    setError("");
    setPrivateLink("");
    setRawToken("");
    setWarning("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/delivery/access`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({
          customer_id: customerId.trim() || "default_customer",
          project_id: projectId.trim() || "default_project",
          recipient_label: recipientLabel.trim(),
          created_by: createdBy.trim(),
          expires_in_hours: expiresInHours,
          max_downloads: maxDownloads,
        }),
        cache: "no-store",
      });
      const data = await readJson(response) as CreateResponse;
      const origin = typeof window === "undefined" ? "" : window.location.origin;
      setPrivateLink(`${origin}${data.fragment_path || ""}`);
      setRawToken(data.token || "");
      setWarning(data.warning || "");
      await refreshAfterCreate();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid delivery access could not be created.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshAfterCreate() {
    const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
    const [accessResponse, receiptResponse] = await Promise.all([
      fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/delivery/access?${params.toString()}`, {headers: {"X-NICO-Admin-Token": adminToken}, cache: "no-store"}),
      fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/delivery/receipts?${params.toString()}`, {headers: {"X-NICO-Admin-Token": adminToken}, cache: "no-store"}),
    ]);
    const accessData = await readJson(accessResponse) as {access?: Access[]};
    const receiptData = await readJson(receiptResponse) as {receipts?: Receipt[]};
    setAccess(accessData.access || []);
    setReceipts(receiptData.receipts || []);
  }

  async function revoke(item: Access) {
    if (!item.access_id || createdBy.trim().length < 2 || !adminToken.trim() || loading) return;
    const reason = window.prompt("Reason for revocation:", "Delivery access no longer required.") || "";
    if (reason.trim().length < 5) return;
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/delivery/access/${encodeURIComponent(item.access_id)}/revoke`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({actor: createdBy.trim(), reason: reason.trim()}),
        cache: "no-store",
      });
      await readJson(response);
      await refreshAfterCreate();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid delivery access could not be revoked.");
    } finally {
      setLoading(false);
    }
  }

  async function copy(value: string) {
    if (value) await navigator.clipboard.writeText(value);
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Controlled delivery administration</h1>
      <p className="lead">Create expiring, download-limited links only for the exact approved Mid artifact. Tokens are returned once and every completed download creates an integrity-bound receipt.</p>
    </section>

    <MidStageNavigation current="delivery" />
    <MidIdentityPanel title="Deliver the selected approved Mid run" />

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Admin scope</p><h2>Approved Mid run</h2></div><span className={access.length ? "status green" : "status gray"}>{access.length} grants</span></div>
      <p className="warning-box">Delivery remains a separate explicit action after approval. The operator identity and admin token are shared from the Mid workspace in live React memory only.</p>
      <div className="form-grid">
        <label>Recipient label<input value={recipientLabel} onChange={(event) => setRecipientLabel(event.target.value)} placeholder="Client name or delivery purpose" /></label>
        <label>Created by<input readOnly value={createdBy} placeholder="Set reviewer or operator in the shared identity panel" /></label>
        <label>Expires in hours<input type="number" min={1} max={168} value={expiresInHours} onChange={(event) => setExpiresInHours(Number(event.target.value))} /></label>
        <label>Maximum downloads<input type="number" min={1} max={20} value={maxDownloads} onChange={(event) => setMaxDownloads(Number(event.target.value))} /></label>
      </div>
      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!runId.trim() || !adminToken.trim() || recipientLabel.trim().length < 2 || createdBy.trim().length < 2 || loading} onClick={createAccess}>{loading ? "Verifying approved artifact..." : "Create private delivery link"}</button>
        <button type="button" disabled={!runId.trim() || !adminToken.trim() || loading} onClick={refresh}>Refresh grants and receipts</button>
      </div>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {privateLink ? <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">One-time token output</p><h2>Copy the private link now</h2></div><span className="status yellow">Shown once</span></div>
      <p className="warning-box">{warning}</p>
      <label>Private client link<textarea readOnly value={privateLink} /></label>
      <button type="button" onClick={() => copy(privateLink)}>Copy private link</button>
      <details className="help-details"><summary>Raw token</summary><pre className="json-block">{rawToken}</pre><button type="button" onClick={() => copy(rawToken)}>Copy raw token</button></details>
    </section> : null}

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Access grants</p><h2>Expiring delivery links</h2></div><span className="status gray">{access.length}</span></div>
      <div className="results-grid">{access.map((item) => <article className="result-card" key={item.access_id}>
        <div className="result-head"><b>{item.recipient_label || item.access_id}</b><span className={statusClass(item.status)}>{item.status}</span></div>
        <p>Expires: {item.expires_at}<br />Downloads: {item.download_count || 0}/{item.max_downloads || 0}<br />Last redeemed: {item.last_redeemed_at || "never"}</p>
        <p className="muted">Token fingerprint: {item.token_fingerprint}<br />Artifact identity: {item.artifact_identity_sha256}</p>
        <button type="button" disabled={item.status !== "active" || loading || createdBy.trim().length < 2} onClick={() => revoke(item)}>Revoke access</button>
      </article>)}</div>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Delivery receipts</p><h2>Acknowledged downloads</h2></div><span className="status gray">{receipts.length}</span></div>
      <div className="results-grid">{receipts.map((item) => <article className="result-card" key={item.receipt_id}>
        <div className="result-head"><b>{item.recipient_name || item.recipient_label}</b><span className="status green">Recorded</span></div>
        <p>Downloaded: {item.downloaded_at}<br />Download number: {item.download_ordinal}</p>
        <p className="muted">Receipt ID: {item.receipt_id}<br />Receipt SHA-256: {item.receipt_sha256}<br />PDF SHA-256: {item.pdf_sha256}<br />Acknowledgement SHA-256: {item.acknowledgement_sha256}</p>
      </article>)}</div>
    </section>
  </main>;
}
