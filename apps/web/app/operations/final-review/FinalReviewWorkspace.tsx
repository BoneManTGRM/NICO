"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import styles from "./final-review.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
type Service = "express" | "comprehensive";
type Decision = "needs_more_evidence" | "rejected";
type JsonRecord = Record<string, unknown>;

type ReviewResponse = {
  status?: string;
  service?: Service;
  review_status?: string;
  acceptance_status?: string;
  approval_id?: string;
  client_delivery_allowed?: boolean;
  approval?: JsonRecord;
  review?: JsonRecord;
  acceptance?: JsonRecord;
  approved_delivery?: JsonRecord;
  approvals?: JsonRecord[];
};

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function approvedDeliveryFrom(value: ReviewResponse | null | undefined): JsonRecord {
  if (!value) return {};
  return asRecord(
    value.approved_delivery
      || asRecord(value.review).approved_delivery
      || asRecord(value.acceptance).approved_delivery,
  );
}

function approvalIdFrom(value: ReviewResponse | null | undefined): string {
  if (!value) return "";
  const direct = String(value.approval_id || "");
  if (direct) return direct;
  const approval = asRecord(value.approval);
  if (approval.approval_id) return String(approval.approval_id);
  const first = Array.isArray(value.approvals) ? asRecord(value.approvals[0]) : {};
  return String(first.approval_id || "");
}

function mergeReviewResponses(latest: ReviewResponse, mutation: ReviewResponse): ReviewResponse {
  const mutationDelivery = approvedDeliveryFrom(mutation);
  const latestDelivery = approvedDeliveryFrom(latest);
  const merged: ReviewResponse = {...mutation, ...latest};
  if (Object.keys(mutationDelivery).length) merged.approved_delivery = {...latestDelivery, ...mutationDelivery};
  return merged;
}

function safeFilename(value: string, fallback: string): string {
  const normalized = value.replace(/[\r\n]/g, "").replace(/[\\/:*?\"<>|]/g, "-").trim();
  return normalized || fallback;
}

function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  const candidate = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    || disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]
    || "";
  try {
    return safeFilename(decodeURIComponent(candidate), fallback);
  } catch {
    return safeFilename(candidate, fallback);
  }
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function downloadBase64Pdf(encoded: string, filename: string): void {
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const binary = window.atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
    throw new Error("Approved PDF signature is invalid.");
  }
  downloadBlob(new Blob([bytes], {type: "application/pdf"}), filename);
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => ({})) as {
    detail?: string | {message?: string}; message?: string; error?: string;
  };
  const detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
  return new Error(detail || payload.message || payload.error || `${fallback} (${response.status}).`);
}

export default function FinalReviewWorkspace() {
  const [service, setService] = useState<Service>("express");
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedService = query.get("service");
    if (requestedService === "express" || requestedService === "comprehensive") setService(requestedService);
    setRunId(query.get("run_id") || "");
    setCustomerId(query.get("customer_id") || "default_customer");
    setProjectId(query.get("project_id") || "default_project");
  }, []);

  const approvalId = useMemo(() => approvalIdFrom(result), [result]);
  const rawStatus = String(
    result?.review_status
      || result?.acceptance_status
      || asRecord(result?.approval).status
      || result?.status
      || "",
  ).trim().toLowerCase();
  const delivery = approvedDeliveryFrom(result);
  const deliveryAllowed = result?.client_delivery_allowed === true
    || asRecord(result?.acceptance).client_delivery_allowed === true
    || delivery.client_delivery_allowed === true;
  const ready = Boolean(API_URL && runId.trim() && adminToken.trim() && reviewer.trim());

  function headers(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken.trim(),
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  function scopeQuery(): URLSearchParams {
    return new URLSearchParams({
      customer_id: customerId.trim() || "default_customer",
      project_id: projectId.trim() || "default_project",
    });
  }

  function statusUrl(): string {
    return `${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}?${scopeQuery()}`;
  }

  async function requestJson(url: string, options: RequestInit = {}): Promise<ReviewResponse> {
    const response = await fetch(url, {cache: "no-store", ...options});
    if (!response.ok) throw await responseError(response, "Final-review request failed");
    return await response.json() as ReviewResponse;
  }

  async function loadStatus(event?: FormEvent): Promise<ReviewResponse | null> {
    event?.preventDefault();
    if (!ready) {
      setError("Enter the exact run, operator token, and authorized reviewer.");
      return null;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const payload = await requestJson(statusUrl(), {headers: headers()});
      setResult(payload);
      setNotice("Exact report package loaded. Review the report and limitations before approval.");
      return payload;
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : "Unable to load final review.");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function ensureReview(current: ReviewResponse): Promise<ReviewResponse> {
    if (approvalIdFrom(current)) return current;
    return requestJson(
      `${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/request`,
      {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({
          customer_id: customerId.trim() || "default_customer",
          project_id: projectId.trim() || "default_project",
          requester: reviewer.trim(),
          evidence: ["Authorized reviewer confirmed review of the exact immutable report and disclosed limitations."],
        }),
      },
    );
  }

  async function approvedStatus(mutation: ReviewResponse): Promise<ReviewResponse> {
    try {
      const latest = await requestJson(statusUrl(), {headers: headers()});
      return mergeReviewResponses(latest, mutation);
    } catch {
      return mutation;
    }
  }

  async function downloadApprovedPdf(source: ReviewResponse): Promise<void> {
    const approved = approvedDeliveryFrom(source);
    const fallback = `nico-${service}-${runId.trim()}-approved-final-report.pdf`;
    const embedded = String(approved.pdf_base64 || approved.approved_pdf_base64 || "");
    if (embedded) {
      downloadBase64Pdf(embedded, safeFilename(String(approved.pdf_filename || ""), fallback));
      return;
    }
    const response = await fetch(
      `${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/approved-pdf?${scopeQuery()}`,
      {cache: "no-store", headers: headers()},
    );
    if (!response.ok) throw await responseError(response, "Approved PDF download failed");
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
      throw new Error("The approved PDF failed browser integrity validation.");
    }
    downloadBlob(new Blob([bytes], {type: "application/pdf"}), filenameFromResponse(response, fallback));
  }

  async function approveAndDownload(): Promise<void> {
    if (!ready || !confirmed) {
      setError("Confirm that you reviewed the exact report and its disclosed limitations.");
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      let current = result || await requestJson(statusUrl(), {headers: headers()});
      current = await ensureReview(current);
      const exactApprovalId = approvalIdFrom(current);
      if (!exactApprovalId) throw new Error("Final review did not return an approval identity.");
      const approved = await requestJson(
        `${API_URL}/operations/final-review/${service}/${encodeURIComponent(exactApprovalId)}/approved`,
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
        },
      );
      const latest = await approvedStatus(approved);
      setResult(latest);
      await downloadApprovedPdf(latest);
      setNotice("Approval recorded. The accepted final report was downloaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to approve and download the final report.");
    } finally {
      setLoading(false);
    }
  }

  async function recordOtherDecision(state: Decision): Promise<void> {
    if (!ready || !note.trim()) {
      setError("Add a clear review note before requesting more evidence or rejecting delivery.");
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      let current = result || await requestJson(statusUrl(), {headers: headers()});
      current = await ensureReview(current);
      const exactApprovalId = approvalIdFrom(current);
      if (!exactApprovalId) throw new Error("Final review did not return an approval identity.");
      const mutation = await requestJson(
        `${API_URL}/operations/final-review/${service}/${encodeURIComponent(exactApprovalId)}/${state}`,
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
        },
      );
      setResult(await approvedStatus(mutation));
      setNotice(state === "needs_more_evidence"
        ? "More evidence requested. Delivery remains blocked."
        : "Report rejected. Delivery remains blocked.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the review decision.");
    } finally {
      setLoading(false);
    }
  }

  return <main className={styles.shell}>
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO FINAL REVIEW</p>
      <h1>Review once. Approve once. Download the accepted report.</h1>
      <p className={styles.lead}>The assessment report is not rewritten. Approval binds the authorized reviewer to the exact run, immutable report, evidence package, and disclosed limitations.</p>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>1</span><div><h2>Load the exact report</h2><p>Opening Final Review from a completed assessment automatically fills the service and run ID.</p></div></div>
      <form className={styles.form} onSubmit={loadStatus}>
        <label>Assessment type<select value={service} onChange={(event) => {setService(event.target.value as Service); setResult(null);}}><option value="express">Express</option><option value="comprehensive">Comprehensive</option></select></label>
        <label>Exact run ID<input value={runId} onChange={(event) => {setRunId(event.target.value); setResult(null);}} placeholder="express_run_… or comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        <label>Operator admin token<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} /></label>
        <label>Authorized reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Name and role" autoComplete="name" /></label>
        <details className={styles.advanced}><summary>Advanced scope</summary><div className={styles.advancedGrid}><label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label></div></details>
        <button className={styles.primary} type="submit" disabled={loading || !ready}>{loading ? "Loading…" : result ? "Reload exact status" : "Load exact report"}</button>
      </form>
      <p className={styles.securityNote}>The operator token remains only in this open page. It is not stored in the URL, browser storage, cookies, or build output.</p>
      <div className={styles.feedback} aria-live="polite">{error ? <div className={styles.error} role="alert">{error}</div> : null}{!error && notice ? <div className={styles.success}>{notice}</div> : null}</div>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}><span className={styles.stepNumber}>2</span><div><h2>Approve and receive the final report</h2><p>Review the PDF and evidence limitations first. The button records approval and downloads the accepted PDF in one controlled action.</p></div></div>
      <div className={styles.statusGrid}><article className={styles.statusCard}><span>Review status</span><strong>{rawStatus ? rawStatus.replaceAll("_", " ") : "Not loaded"}</strong></article><article className={styles.statusCard}><span>Client delivery</span><strong>{deliveryAllowed ? "Authorized" : "Blocked"}</strong></article></div>
      {!result ? <div className={styles.emptyState}>Load the report above, review its exact PDF and limitations, then approve it here.</div> : null}
      <label className="check-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed the exact report, scorecard, evidence limitations, and delivery boundary for this run.</label>
      <label>Approval note, optional<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional approval context. Required only for other decisions." /></label>
      <div className={styles.downloadActions}><button className={styles.approve} type="button" disabled={!result || !confirmed || loading || deliveryAllowed} onClick={approveAndDownload}>{loading ? "Recording approval…" : deliveryAllowed ? "Report already approved" : "Approve and download final report"}</button>{deliveryAllowed ? <button type="button" disabled={loading} onClick={() => result && downloadApprovedPdf(result)}>Download approved final PDF again</button> : null}</div>
      <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>{deliveryAllowed ? "Approval is recorded for this exact run and the accepted report is available." : "Delivery remains blocked until the authorized reviewer approves this exact package."}</div>
      <details className={styles.advanced}><summary>Other decisions</summary><div className={styles.decisionActions}><button type="button" disabled={!result || loading} onClick={() => recordOtherDecision("needs_more_evidence")}>Request more evidence</button><button className={styles.reject} type="button" disabled={!result || loading} onClick={() => recordOtherDecision("rejected")}>Reject delivery</button></div></details>
    </section>

    {result ? <section className={styles.panel}><details className={styles.record}><summary>Exact review record</summary><pre className={styles.code}>{JSON.stringify(result, null, 2)}</pre></details></section> : null}
  </main>;
}
