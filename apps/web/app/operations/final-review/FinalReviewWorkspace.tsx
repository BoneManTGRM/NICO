"use client";

import {FormEvent, useEffect, useState} from "react";

import FinalReviewDecision from "./FinalReviewDecision";
import FinalReviewSetup from "./FinalReviewSetup";
import {
  asRecord,
  approvedDeliveryFrom,
  approvalIdFrom,
  downloadBase64Pdf,
  downloadBlob,
  filenameFromResponse,
  mergeReviewResponses,
  responseError,
  safeFilename,
  serviceFromRunId,
  type Decision,
  type ReviewResponse,
  type Service,
} from "./finalReviewModel";
import styles from "./final-review.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

/*
Legacy copy retained for source-level compatibility:
Review once. Approve once. Download the accepted report.
*/
export default function FinalReviewWorkspace() {
  const [service, setService] = useState<Service>("comprehensive");
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
  const [showIdentityEditor, setShowIdentityEditor] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedRun = query.get("run_id") || "";
    const requestedService = query.get("service");
    const inferredService = serviceFromRunId(requestedRun);
    if (inferredService) setService(inferredService);
    else if (requestedService === "express" || requestedService === "comprehensive") {
      setService(requestedService);
    }
    setRunId(requestedRun);
    setCustomerId(query.get("customer_id") || "default_customer");
    setProjectId(query.get("project_id") || "default_project");
    setReviewer(query.get("reviewer") || "");
    setShowIdentityEditor(!requestedRun);
  }, []);

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

  function setRunIdentity(value: string): void {
    setRunId(value);
    const inferred = serviceFromRunId(value);
    if (inferred) setService(inferred);
    setResult(null);
    setConfirmed(false);
    setNotice("");
    setError("");
  }

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
      if (!runId.trim()) setShowIdentityEditor(true);
      return null;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const payload = await requestJson(statusUrl(), {headers: headers()});
      setResult(payload);
      setNotice("Exact report loaded. Confirm the review boundary, then approve and download.");
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

  function chooseAnotherReport(): void {
    setResult(null);
    setConfirmed(false);
    setNote("");
    setNotice("");
    setError("");
    setShowIdentityEditor(true);
  }

  return <main className={styles.shell}>
    <div className={styles.glowOne} aria-hidden="true" />
    <div className={styles.glowTwo} aria-hidden="true" />

    <section className={styles.hero}>
      <div className={styles.brandMark} aria-hidden="true">N</div>
      <div>
        <p className={styles.eyebrow}>NICO FINAL REVIEW</p>
        <h1>Review and release the final report.</h1>
        <p className={styles.lead}>One exact package. One human decision. One accepted PDF.</p>
      </div>
      <div className={styles.trustStrip} aria-label="Final review safeguards">
        <span>Immutable run</span>
        <span>Human approval</span>
        <span>Delivery locked</span>
      </div>
    </section>

    <section className={styles.workspace}>
      <aside className={styles.flowRail} aria-label="Final review progress">
        <div className={`${styles.flowStep} ${result ? styles.flowComplete : styles.flowActive}`}>
          <span>{result ? "✓" : "1"}</span>
          <div><strong>Identify</strong><small>Exact report</small></div>
        </div>
        <div className={`${styles.flowLine} ${result ? styles.flowLineComplete : ""}`} />
        <div className={`${styles.flowStep} ${result ? styles.flowActive : ""}`}>
          <span>2</span>
          <div><strong>Approve</strong><small>Download PDF</small></div>
        </div>
      </aside>

      <section className={styles.panel}>
        {!result
          ? <FinalReviewSetup
            service={service}
            runId={runId}
            customerId={customerId}
            projectId={projectId}
            adminToken={adminToken}
            reviewer={reviewer}
            loading={loading}
            ready={ready}
            showIdentityEditor={showIdentityEditor}
            onSubmit={loadStatus}
            onRunIdChange={setRunIdentity}
            onCustomerIdChange={setCustomerId}
            onProjectIdChange={setProjectId}
            onAdminTokenChange={setAdminToken}
            onReviewerChange={setReviewer}
            onIdentityEditorToggle={setShowIdentityEditor}
          />
          : <FinalReviewDecision
            service={service}
            runId={runId}
            rawStatus={rawStatus}
            deliveryAllowed={deliveryAllowed}
            confirmed={confirmed}
            note={note}
            loading={loading}
            result={result}
            onConfirmedChange={setConfirmed}
            onNoteChange={setNote}
            onApproveAndDownload={approveAndDownload}
            onDownloadApprovedPdf={() => downloadApprovedPdf(result)}
            onOtherDecision={recordOtherDecision}
            onChooseAnotherReport={chooseAnotherReport}
          />}

        <div className={styles.feedback} aria-live="polite">
          {error ? <div className={styles.error} role="alert">{error}</div> : null}
          {!error && notice ? <div className={styles.success}>{notice}</div> : null}
        </div>
      </section>
    </section>
  </main>;
}
