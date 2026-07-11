"use client";

import {useMemo, useState} from "react";

type DeliveryAccess = {
  access_id?: string;
  status?: string;
  recipient_label?: string;
  created_by?: string;
  created_at?: string;
  expires_at?: string;
  revoked_at?: string;
  max_downloads?: number;
  download_count?: number;
  downloads_remaining?: number;
  last_redeemed_at?: string;
  token_fingerprint?: string;
  persistence?: {durable?: boolean; adapter?: string; note?: string};
};

type DeliveryReceipt = {
  receipt_id?: string;
  status?: string;
  receipt_version?: string;
  access_id?: string;
  run_id?: string;
  report_id?: string;
  approval_id?: string;
  recipient_label?: string;
  delivered_at?: string;
  download_number?: number;
  pdf_sha256?: string;
  source_draft_pdf_sha256?: string;
  approval_identity_sha256?: string;
  token_fingerprint?: string;
  receipt_sha256?: string;
  verified?: boolean;
  verification?: {status?: string; verified?: boolean; blockers?: string[]; checks?: Array<{id?: string; passed?: boolean; message?: string}>};
  persistence?: {durable?: boolean; adapter?: string; note?: string};
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
  verification?: {status?: string; verified?: boolean; blockers?: string[]; checks?: Array<{id?: string; passed?: boolean; message?: string}>};
  persistence?: {durable?: boolean; adapter?: string; note?: string};
  receipt_only?: boolean;
  technical_approval?: boolean;
  agreement_with_findings?: boolean;
  legal_acceptance?: boolean;
};

type AccessResponse = {status?: string; access?: DeliveryAccess[]; detail?: {message?: string}; error?: string};
type ReceiptResponse = {status?: string; receipt_count?: number; verified_count?: number; receipts?: DeliveryReceipt[]; persistence?: {durable?: boolean; adapter?: string; note?: string}; rule?: string; detail?: {message?: string}; error?: string};
type AcknowledgmentResponse = {status?: string; acknowledgment_count?: number; verified_count?: number; acknowledgments?: DeliveryAcknowledgment[]; persistence?: {durable?: boolean; adapter?: string; note?: string}; statement?: string; rule?: string; detail?: {message?: string}; error?: string};

type Props = {
  apiUrl: string;
  runId: string;
  customerId: string;
  projectId: string;
  adminToken: string;
  actor: string;
  disabled?: boolean;
};

function statusClass(status?: string) {
  if (["active", "verified", "delivered", "acknowledged", "ok"].includes(status || "")) return "status green";
  if (["exhausted", "expired", "pending"].includes(status || "")) return "status yellow";
  if (["revoked", "blocked", "failed", "tampered"].includes(status || "")) return "status red";
  return "status gray";
}

function effectiveAccessStatus(item: DeliveryAccess): string {
  if (item.status === "revoked") return "revoked";
  const expires = item.expires_at ? Date.parse(item.expires_at) : Number.NaN;
  if (Number.isFinite(expires) && expires <= Date.now()) return "expired";
  if (Number(item.downloads_remaining ?? Math.max(0, Number(item.max_downloads || 0) - Number(item.download_count || 0))) <= 0) return "exhausted";
  return item.status || "active";
}

function downloadJson(filename: string, value: unknown) {
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

export default function DeliveryLedger({apiUrl, runId, customerId, projectId, adminToken, actor, disabled = false}: Props) {
  const [access, setAccess] = useState<DeliveryAccess[]>([]);
  const [receipts, setReceipts] = useState<DeliveryReceipt[]>([]);
  const [acknowledgments, setAcknowledgments] = useState<DeliveryAcknowledgment[]>([]);
  const [persistence, setPersistence] = useState<ReceiptResponse["persistence"]>();
  const [acknowledgmentPersistence, setAcknowledgmentPersistence] = useState<AcknowledgmentResponse["persistence"]>();
  const [rule, setRule] = useState("");
  const [acknowledgmentRule, setAcknowledgmentRule] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revokingId, setRevokingId] = useState("");

  const summary = useMemo(() => {
    const active = access.filter((item) => effectiveAccessStatus(item) === "active").length;
    const revoked = access.filter((item) => effectiveAccessStatus(item) === "revoked").length;
    const expiredOrExhausted = access.filter((item) => ["expired", "exhausted"].includes(effectiveAccessStatus(item))).length;
    const downloads = access.reduce((total, item) => total + Number(item.download_count || 0), 0);
    const verifiedReceipts = receipts.filter((item) => item.verified).length;
    const verifiedAcknowledgments = acknowledgments.filter((item) => item.verified).length;
    return {active, revoked, expiredOrExhausted, downloads, verifiedReceipts, verifiedAcknowledgments};
  }, [access, receipts, acknowledgments]);

  async function readJson(response: Response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.message || data?.error || `Delivery-ledger request failed with ${response.status}`);
    return data;
  }

  async function refreshLedger() {
    if (!apiUrl || !runId || !adminToken.trim() || disabled) return;
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId, project_id: projectId});
      const headers = {"X-NICO-Admin-Token": adminToken};
      const [accessResponse, receiptResponse, acknowledgmentResponse] = await Promise.all([
        fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/access?${params.toString()}`, {headers, cache: "no-store"}),
        fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/receipts?${params.toString()}`, {headers, cache: "no-store"}),
        fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/acknowledgments?${params.toString()}`, {headers, cache: "no-store"}),
      ]);
      const accessData = await readJson(accessResponse) as AccessResponse;
      const receiptData = await readJson(receiptResponse) as ReceiptResponse;
      const acknowledgmentData = await readJson(acknowledgmentResponse) as AcknowledgmentResponse;
      setAccess(Array.isArray(accessData.access) ? accessData.access : []);
      setReceipts(Array.isArray(receiptData.receipts) ? receiptData.receipts : []);
      setAcknowledgments(Array.isArray(acknowledgmentData.acknowledgments) ? acknowledgmentData.acknowledgments : []);
      setPersistence(receiptData.persistence);
      setAcknowledgmentPersistence(acknowledgmentData.persistence);
      setRule(receiptData.rule || "");
      setAcknowledgmentRule(acknowledgmentData.rule || "");
      setLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delivery ledger could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function revoke(accessId: string) {
    if (!accessId || !adminToken.trim() || disabled) return;
    setError("");
    setRevokingId(accessId);
    try {
      const response = await fetch(`${apiUrl}/assessment/full-run/approved-delivery/access/${encodeURIComponent(accessId)}/revoke`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({actor: actor || "admin"}),
        cache: "no-store",
      });
      const data = await readJson(response) as {status?: string; access?: DeliveryAccess};
      if (data.status !== "revoked") throw new Error("The selected client link was not revoked.");
      setAccess((current) => current.map((item) => item.access_id === accessId ? {...item, ...(data.access || {}), status: "revoked"} : item));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Client-link revocation failed.");
    } finally {
      setRevokingId("");
    }
  }

  function exportLedger() {
    const exportedAt = new Date().toISOString();
    downloadJson(`nico-approved-delivery-ledger-${runId}.json`, {
      schema_version: "approved-delivery-ledger-v2",
      exported_at: exportedAt,
      run_id: runId,
      customer_id: customerId,
      project_id: projectId,
      summary,
      access,
      receipts,
      acknowledgments,
      persistence,
      acknowledgment_persistence: acknowledgmentPersistence,
      receipt_rule: rule,
      acknowledgment_rule: acknowledgmentRule,
      disclosure: "This export contains access metadata, token fingerprints, receipt hashes, and receipt-only acknowledgments. It does not contain raw access tokens or convert acknowledgment into technical approval or agreement with findings.",
    });
  }

  return <div className="mini-panel">
    <div className="section-head">
      <div><p className="eyebrow">Owner delivery ledger</p><h2>Links, downloads, receipts, and acknowledgments</h2></div>
      <span className={statusClass(error ? "blocked" : loaded ? "verified" : "pending")}>{error ? "blocked" : loaded ? "loaded" : "not loaded"}</span>
    </div>
    <p className="muted">Admin-only operational history for this approved Full Assessment. Raw access tokens are never returned by these ledger endpoints.</p>
    <div className="report-actions">
      <button type="button" className="primary-button" disabled={disabled || loading || !apiUrl || !runId || !adminToken.trim()} onClick={refreshLedger}>{loading ? "Loading ledger..." : "Refresh delivery ledger"}</button>
      <button type="button" disabled={!loaded || loading} onClick={exportLedger}>Export ledger JSON</button>
    </div>
    {error ? <p className="error-box">{error}</p> : null}
    {loaded ? <>
      <div className="grid four target-grid">
        <article><b>Active links</b><span>{summary.active}</span></article>
        <article><b>Recorded downloads</b><span>{summary.downloads}</span></article>
        <article><b>Verified receipts</b><span>{summary.verifiedReceipts}/{receipts.length}</span></article>
        <article><b>Receipt acknowledgments</b><span>{summary.verifiedAcknowledgments}/{acknowledgments.length}</span></article>
      </div>
      <p className="muted">Closed links: {summary.revoked + summary.expiredOrExhausted}. Acknowledgments confirm receipt only and do not alter technical approval or report findings.</p>

      <details className="help-details" open><summary>Secure client links ({access.length})</summary>
        <div className="results-grid">{access.length ? access.map((item) => {
          const state = effectiveAccessStatus(item);
          return <article className="result-card" key={item.access_id || `${item.created_at}-${item.token_fingerprint}`}>
            <div className="result-head"><b>{item.recipient_label || "Unlabeled recipient"}</b><span className={statusClass(state)}>{state}</span></div>
            <p>Downloads: {item.download_count || 0}/{item.max_downloads || 0}; remaining={item.downloads_remaining ?? 0}</p>
            <p>Created: {item.created_at || "not recorded"}; expires: {item.expires_at || "not recorded"}</p>
            <p>Access ID: {item.access_id || "not recorded"}; token fingerprint: {item.token_fingerprint || "not recorded"}</p>
            {item.last_redeemed_at ? <p>Last delivered: {item.last_redeemed_at}</p> : null}
            <div className="report-actions"><button type="button" disabled={state !== "active" || revokingId === item.access_id || !adminToken.trim()} onClick={() => revoke(item.access_id || "")}>{revokingId === item.access_id ? "Revoking..." : "Revoke link"}</button></div>
          </article>;
        }) : <p className="muted">No secure client links exist for this run and scope.</p>}</div>
      </details>

      <details className="help-details" open><summary>Hash-bound delivery receipts ({receipts.length})</summary>
        <div className="results-grid">{receipts.length ? receipts.map((item) => <article className="result-card" key={item.receipt_id || `${item.access_id}-${item.download_number}`}>
          <div className="result-head"><b>{item.recipient_label || "Unlabeled recipient"} — download {item.download_number || 0}</b><span className={statusClass(item.verified ? "verified" : "tampered")}>{item.verified ? "verified" : "blocked"}</span></div>
          <p>Delivered: {item.delivered_at || "not recorded"}; receipt ID: {item.receipt_id || "not recorded"}</p>
          <p>Receipt SHA-256: {item.receipt_sha256 || "not recorded"}</p>
          <p>PDF SHA-256: {item.pdf_sha256 || "not recorded"}</p>
          <p>Access ID: {item.access_id || "not recorded"}; token fingerprint: {item.token_fingerprint || "not recorded"}</p>
          {item.verification ? <details className="help-details"><summary>Receipt verification</summary><pre className="json-block">{JSON.stringify(item.verification, null, 2)}</pre></details> : null}
        </article>) : <p className="muted">No completed client downloads have produced receipts for this run.</p>}</div>
      </details>

      <details className="help-details" open><summary>Receipt-only client acknowledgments ({acknowledgments.length})</summary>
        <div className="results-grid">{acknowledgments.length ? acknowledgments.map((item) => <article className="result-card" key={item.acknowledgment_id || item.receipt_id}>
          <div className="result-head"><b>{item.acknowledged_by || item.recipient_label || "Unlabeled recipient"}</b><span className={statusClass(item.verified ? "acknowledged" : "tampered")}>{item.verified ? "verified" : "blocked"}</span></div>
          <p>Acknowledged: {item.acknowledged_at || "not recorded"}; acknowledgment ID: {item.acknowledgment_id || "not recorded"}</p>
          <p>Acknowledgment SHA-256: {item.acknowledgment_sha256 || "not recorded"}</p>
          <p>Receipt ID: {item.receipt_id || "not recorded"}; receipt SHA-256: {item.receipt_sha256 || "not recorded"}</p>
          <p>Receipt only={String(item.receipt_only)}; technical approval={String(item.technical_approval)}; agreement with findings={String(item.agreement_with_findings)}.</p>
          {item.verification ? <details className="help-details"><summary>Acknowledgment verification</summary><pre className="json-block">{JSON.stringify(item.verification, null, 2)}</pre></details> : null}
        </article>) : <p className="muted">No recipient has recorded an optional receipt acknowledgment for this run.</p>}</div>
      </details>

      {persistence?.durable === false ? <p className="warning-box">{persistence.note}</p> : null}
      {acknowledgmentPersistence?.durable === false ? <p className="warning-box">{acknowledgmentPersistence.note}</p> : null}
      {rule ? <p className="muted">{rule}</p> : null}
      {acknowledgmentRule ? <p className="muted">{acknowledgmentRule}</p> : null}
    </> : null}
  </div>;
}
