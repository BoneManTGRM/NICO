"use client";

import {FormEvent, useMemo, useState} from "react";
import styles from "./final-review.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
type Service = "express" | "comprehensive";
type JsonRecord = Record<string, unknown>;

type ReviewResponse = {
  status?: string;
  service?: Service;
  review_kind?: string;
  review_status?: string;
  acceptance_status?: string;
  approval_id?: string;
  approver?: string;
  client_delivery_allowed?: boolean;
  approval?: JsonRecord;
  review?: JsonRecord;
  acceptance?: JsonRecord;
  approved_delivery?: JsonRecord;
  approvals?: JsonRecord[];
  review_validation?: JsonRecord;
};

function jsonText(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function downloadBase64Pdf(encoded: string, filename: string): void {
  const binary = window.atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const blob = new Blob([bytes], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function FinalReviewOperationsPage() {
  const [service, setService] = useState<Service>("express");
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const approval = useMemo(() => {
    const direct = result?.approval;
    if (direct && typeof direct === "object") return direct;
    const approvals = result?.approvals;
    return Array.isArray(approvals) && approvals.length && typeof approvals[0] === "object" ? approvals[0] : null;
  }, [result]);
  const approvalId = String(result?.approval_id || approval?.approval_id || "");
  const status = String(result?.review_status || result?.acceptance_status || approval?.status || result?.status || "not loaded");
  const approvedDelivery = (result?.approved_delivery || result?.review?.approved_delivery || result?.acceptance?.approved_delivery || {}) as JsonRecord;
  const deliveryAllowed = result?.client_delivery_allowed === true
    || result?.acceptance?.client_delivery_allowed === true
    || approvedDelivery.client_delivery_allowed === true;

  function headers(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken,
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  async function requestJson(url: string, options: RequestInit = {}): Promise<ReviewResponse> {
    const response = await fetch(url, {cache: "no-store", ...options});
    let payload: ReviewResponse & {detail?: {message?: string}; message?: string; error?: string};
    try {
      payload = await response.json();
    } catch {
      throw new Error(`Final-review endpoint returned invalid JSON (${response.status}).`);
    }
    if (!response.ok) {
      throw new Error(payload.detail?.message || payload.message || payload.error || `Final-review request failed (${response.status}).`);
    }
    return payload;
  }

  function validate(): boolean {
    if (!API_URL) {
      setError("NEXT_PUBLIC_NICO_API_URL is not configured for this deployment.");
      return false;
    }
    if (!adminToken.trim()) {
      setError("Enter the operator admin token. It remains only in this page memory.");
      return false;
    }
    if (!runId.trim()) {
      setError("Enter the exact assessment run ID.");
      return false;
    }
    return true;
  }

  async function loadReview(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({customer_id: customerId, project_id: projectId});
      setResult(await requestJson(`${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}?${query}`, {headers: headers()}));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load final review.");
    } finally {
      setLoading(false);
    }
  }

  async function requestReview(): Promise<void> {
    if (!validate()) return;
    setLoading(true);
    setError("");
    try {
      const payload = await requestJson(`${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/request`, {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({
          customer_id: customerId,
          project_id: projectId,
          requester: reviewer.trim() || "nico_operator",
          evidence: ["Operator requested review of the exact immutable final report package."],
        }),
      });
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request final review.");
    } finally {
      setLoading(false);
    }
  }

  async function transition(state: "approved" | "needs_more_evidence" | "rejected"): Promise<void> {
    if (!validate()) return;
    if (!approvalId) {
      setError("Request final review before recording a decision.");
      return;
    }
    if (!reviewer.trim()) {
      setError("Enter the authorized reviewer identity.");
      return;
    }
    if ((state === "needs_more_evidence" || state === "rejected") && !note.trim()) {
      setError("A substantive review note is required for this decision.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await requestJson(`${API_URL}/operations/final-review/${service}/${encodeURIComponent(approvalId)}/${state}`, {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
      });
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the review decision.");
    } finally {
      setLoading(false);
    }
  }

  function downloadApprovedPdf(): void {
    const encoded = String(approvedDelivery.pdf_base64 || approvedDelivery.approved_pdf_base64 || "");
    if (!encoded) {
      setError("The approved PDF is not attached to this review response. Reload the approved delivery package after deployment finishes.");
      return;
    }
    downloadBase64Pdf(encoded, String(approvedDelivery.pdf_filename || `nico-${service}-approved-final-report.pdf`));
  }

  async function downloadApprovedPackage(): Promise<void> {
    if (!validate() || service !== "comprehensive") return;
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({customer_id: customerId, project_id: projectId});
      const response = await fetch(`${API_URL}/assessment/full-run/${encodeURIComponent(runId.trim())}/approved-delivery/package?${query}`, {
        cache: "no-store",
        headers: headers(),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as {detail?: {message?: string}};
        throw new Error(payload.detail?.message || `Approved package download failed (${response.status}).`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `nico-${service}-${runId.trim()}-approved-delivery.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to download approved package.");
    } finally {
      setLoading(false);
    }
  }

  return <main className={styles.shell}>
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO Operator Review</p>
      <h1>Approve the exact final report</h1>
      <p className={styles.lead}>Review the immutable Express or Comprehensive package, record an authorized human decision, and unlock approved delivery without rewriting the report.</p>
    </section>

    <section className={styles.panel}>
      <h2>Review identity</h2>
      <form className={styles.grid} onSubmit={loadReview}>
        <label>Service<select value={service} onChange={(event) => { setService(event.target.value as Service); setResult(null); }}><option value="express">Express</option><option value="comprehensive">Comprehensive</option></select></label>
        <label>Exact run ID<input value={runId} onChange={(event) => { setRunId(event.target.value); setResult(null); }} placeholder="express_run_… or comprun_…" /></label>
        <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
        <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
        <label>Operator admin token<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} /></label>
        <label>Authorized reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Reviewer name and role" /></label>
        <label style={{gridColumn: "1 / -1"}}>Substantive review note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Decision rationale, disclosures reviewed, or evidence requested" /></label>
        <button className={styles.primary} type="submit" disabled={loading}>{loading ? "Working…" : "Load review status"}</button>
        <button type="button" disabled={loading || !runId.trim()} onClick={requestReview}>Request final review</button>
      </form>
      <p className={styles.muted}>The admin token remains only in React memory for this open page. It is never placed in the URL, local storage, cookies, or build output.</p>
      {error ? <div className={styles.error}>{error}</div> : null}
    </section>

    <section className={styles.panel}>
      <h2>Decision and delivery</h2>
      <div className={styles.metrics}>
        <article className={styles.card}><b>Service</b><span>{service}</span></article>
        <article className={styles.card}><b>Review status</b><span>{status}</span></article>
        <article className={styles.card}><b>Approval ID</b><span>{approvalId || "Not requested"}</span></article>
        <article className={styles.card}><b>Client delivery</b><span>{deliveryAllowed ? "Authorized" : "Blocked pending approval"}</span></article>
      </div>
      <div className={styles.actions}>
        <button className={styles.approve} type="button" disabled={loading || !approvalId} onClick={() => transition("approved")}>Approve exact report</button>
        <button type="button" disabled={loading || !approvalId} onClick={() => transition("needs_more_evidence")}>Request more evidence</button>
        <button className={styles.reject} type="button" disabled={loading || !approvalId} onClick={() => transition("rejected")}>Reject delivery</button>
      </div>
      {deliveryAllowed ? <div className={styles.success}>Approval is recorded. The approved report remains bound to the exact reviewed run and evidence package.</div> : <div className={styles.warning}>Delivery remains blocked until an authorized human approval is recorded.</div>}
      <div className={styles.actions}>
        <button type="button" disabled={!deliveryAllowed} onClick={downloadApprovedPdf}>Download approved final PDF</button>
        <button type="button" disabled={!deliveryAllowed || service !== "comprehensive" || loading} onClick={downloadApprovedPackage}>Download approved delivery package</button>
      </div>
    </section>

    <section className={styles.panel}>
      <h2>Exact review record</h2>
      <pre className={styles.code}>{jsonText(result)}</pre>
    </section>
  </main>;
}
