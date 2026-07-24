"use client";

import {FormEvent, useMemo, useState} from "react";
import styles from "./final-review.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
type Service = "express" | "comprehensive";
type Decision = "approved" | "needs_more_evidence" | "rejected";
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

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function jsonText(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function statusLabel(value: string): string {
  const normalized = value.trim().replace(/_/g, " ");
  return normalized ? normalized.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Not loaded";
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
  downloadBlob(new Blob([bytes], {type: "application/pdf"}), filename);
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
  const [notice, setNotice] = useState("");

  const approval = useMemo(() => {
    const direct = result?.approval;
    if (direct && typeof direct === "object") return direct;
    const approvals = result?.approvals;
    return Array.isArray(approvals) && approvals.length && typeof approvals[0] === "object"
      ? approvals[0]
      : null;
  }, [result]);

  const approvalId = String(result?.approval_id || approval?.approval_id || "");
  const rawStatus = String(
    result?.review_status
      || result?.acceptance_status
      || approval?.status
      || result?.status
      || "",
  );
  const normalizedStatus = rawStatus.trim().toLowerCase();
  const approvedDelivery = asRecord(
    result?.approved_delivery
      || asRecord(result?.review).approved_delivery
      || asRecord(result?.acceptance).approved_delivery,
  );
  const deliveryAllowed = result?.client_delivery_allowed === true
    || asRecord(result?.acceptance).client_delivery_allowed === true
    || approvedDelivery.client_delivery_allowed === true;
  const reviewStarted = Boolean(approvalId);
  const finalDecisionRecorded = normalizedStatus === "approved" || normalizedStatus === "rejected";
  const readyToLoad = Boolean(runId.trim() && adminToken.trim());

  function headers(json = false): HeadersInit {
    return {
      "X-NICO-Admin-Token": adminToken.trim(),
      ...(json ? {"Content-Type": "application/json"} : {}),
    };
  }

  function reviewQuery(): URLSearchParams {
    return new URLSearchParams({
      customer_id: customerId.trim() || "default_customer",
      project_id: projectId.trim() || "default_project",
    });
  }

  function reviewUrl(): string {
    return `${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}?${reviewQuery()}`;
  }

  async function requestJson(url: string, options: RequestInit = {}): Promise<ReviewResponse> {
    const response = await fetch(url, {cache: "no-store", ...options});
    let payload: ReviewResponse & {
      detail?: string | {message?: string};
      message?: string;
      error?: string;
    };
    try {
      payload = await response.json();
    } catch {
      throw new Error(`Final-review endpoint returned invalid JSON (${response.status}).`);
    }
    if (!response.ok) {
      const detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
      throw new Error(detail || payload.message || payload.error || `Final-review request failed (${response.status}).`);
    }
    return payload;
  }

  function validate(requireReviewer = false): boolean {
    if (!API_URL) {
      setError("The NICO API is not configured for this deployment.");
      return false;
    }
    if (!adminToken.trim()) {
      setError("Enter the operator admin token.");
      return false;
    }
    if (!runId.trim()) {
      setError("Enter the exact assessment run ID.");
      return false;
    }
    if (requireReviewer && !reviewer.trim()) {
      setError("Enter the authorized reviewer name and role.");
      return false;
    }
    return true;
  }

  async function fetchReviewStatus(): Promise<ReviewResponse> {
    return requestJson(reviewUrl(), {headers: headers()});
  }

  async function refreshAfterMutation(fallback: ReviewResponse): Promise<boolean> {
    try {
      setResult(await fetchReviewStatus());
      return true;
    } catch {
      setResult(fallback);
      return false;
    }
  }

  async function loadReview(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      setResult(await fetchReviewStatus());
      setNotice("Review status loaded.");
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : "Unable to load final review.");
    } finally {
      setLoading(false);
    }
  }

  async function requestReview(): Promise<void> {
    if (!validate(true)) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const payload = await requestJson(
        `${API_URL}/operations/final-review/${service}/${encodeURIComponent(runId.trim())}/request`,
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({
            customer_id: customerId.trim() || "default_customer",
            project_id: projectId.trim() || "default_project",
            requester: reviewer.trim(),
            evidence: ["Operator requested review of the exact immutable final report package."],
          }),
        },
      );
      const refreshed = await refreshAfterMutation(payload);
      setNotice(
        refreshed
          ? "Final review started. Record the authorized decision below."
          : "Final review started, but the latest status could not be refreshed. Use Reload status before deciding.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request final review.");
    } finally {
      setLoading(false);
    }
  }

  async function transition(state: Decision): Promise<void> {
    if (!validate(true)) return;
    if (!approvalId) {
      setError("Start final review before recording a decision.");
      return;
    }
    if ((state === "needs_more_evidence" || state === "rejected") && !note.trim()) {
      setError("Add a clear review note for this decision.");
      return;
    }

    setLoading(true);
    setError("");
    setNotice("");
    try {
      const payload = await requestJson(
        `${API_URL}/operations/final-review/${service}/${encodeURIComponent(approvalId)}/${state}`,
        {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({actor: reviewer.trim(), note: note.trim()}),
        },
      );
      const refreshed = await refreshAfterMutation(payload);
      setNotice(
        refreshed
          ? state === "approved"
            ? "Approval recorded. Approved delivery is now available when the package is ready."
            : state === "needs_more_evidence"
              ? "More evidence requested. Client delivery remains blocked."
              : "Rejection recorded. Client delivery remains blocked."
          : "The decision was recorded, but the latest status could not be refreshed. Use Reload status before downloading.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the review decision.");
    } finally {
      setLoading(false);
    }
  }

  function downloadApprovedPdf(): void {
    setError("");
    const encoded = String(approvedDelivery.pdf_base64 || approvedDelivery.approved_pdf_base64 || "");
    if (!encoded) {
      setError("The approved PDF is not attached yet. Reload status after the delivery package finishes.");
      return;
    }
    try {
      downloadBase64Pdf(
        encoded,
        String(approvedDelivery.pdf_filename || `nico-${service}-approved-final-report.pdf`),
      );
    } catch {
      setError("The approved PDF data is invalid. Reload status and try again.");
    }
  }

  async function downloadApprovedPackage(): Promise<void> {
    if (!validate() || service !== "comprehensive") return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        `${API_URL}/assessment/full-run/${encodeURIComponent(runId.trim())}/approved-delivery/package?${reviewQuery()}`,
        {cache: "no-store", headers: headers()},
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({})) as {
          detail?: string | {message?: string};
        };
        const detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
        throw new Error(detail || `Approved package download failed (${response.status}).`);
      }
      downloadBlob(
        await response.blob(),
        `nico-${service}-${runId.trim()}-approved-delivery.zip`,
      );
      setNotice("Approved delivery package downloaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to download approved package.");
    } finally {
      setLoading(false);
    }
  }

  function resetLoadedReview(): void {
    setResult(null);
    setNote("");
    setError("");
    setNotice("");
  }

  return <main className={styles.shell}>
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO Operator Review</p>
      <h1>Final review</h1>
      <p className={styles.lead}>Load a completed assessment, record one authorized decision, then download the approved report.</p>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}>
        <span className={styles.stepNumber}>1</span>
        <div>
          <h2>Find the report</h2>
          <p>Only the assessment type, exact run ID, admin token, and reviewer are normally needed.</p>
        </div>
      </div>

      <form className={styles.form} onSubmit={loadReview}>
        <label>
          Assessment type
          <select
            value={service}
            onChange={(event) => {
              setService(event.target.value as Service);
              resetLoadedReview();
            }}
          >
            <option value="express">Express</option>
            <option value="comprehensive">Comprehensive</option>
          </select>
        </label>

        <label>
          Exact run ID
          <input
            value={runId}
            onChange={(event) => {
              setRunId(event.target.value);
              resetLoadedReview();
            }}
            placeholder="express_run_… or comprun_…"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
          />
        </label>

        <label>
          Operator admin token
          <input
            type="password"
            value={adminToken}
            onChange={(event) => setAdminToken(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <label>
          Authorized reviewer
          <input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            placeholder="Name and role"
            autoComplete="name"
          />
        </label>

        <details className={styles.advanced}>
          <summary>Advanced options</summary>
          <div className={styles.advancedGrid}>
            <label>
              Customer ID
              <input
                value={customerId}
                onChange={(event) => {
                  setCustomerId(event.target.value);
                  resetLoadedReview();
                }}
              />
            </label>
            <label>
              Project ID
              <input
                value={projectId}
                onChange={(event) => {
                  setProjectId(event.target.value);
                  resetLoadedReview();
                }}
              />
            </label>
          </div>
        </details>

        <button className={styles.primary} type="submit" disabled={loading || !readyToLoad}>
          {loading ? "Working…" : result ? "Reload status" : "Load report"}
        </button>
      </form>

      <p className={styles.securityNote}>The admin token stays only in this open page and is not saved in URLs, browser storage, cookies, or the build.</p>

      <div className={styles.feedback} aria-live="polite">
        {error ? <div className={styles.error} role="alert">{error}</div> : null}
        {!error && notice ? <div className={styles.success}>{notice}</div> : null}
      </div>
    </section>

    <section className={styles.panel}>
      <div className={styles.stepHeading}>
        <span className={styles.stepNumber}>2</span>
        <div>
          <h2>Review and decide</h2>
          <p>The exact report remains unchanged. Approval only unlocks its bound delivery package.</p>
        </div>
      </div>

      <div className={styles.statusGrid}>
        <article className={styles.statusCard}>
          <span>Review status</span>
          <strong>{statusLabel(rawStatus)}</strong>
        </article>
        <article className={styles.statusCard}>
          <span>Client delivery</span>
          <strong>{deliveryAllowed ? "Authorized" : "Blocked"}</strong>
        </article>
      </div>

      {!result ? <div className={styles.emptyState}>Load a report to begin final review.</div> : null}

      {result && !reviewStarted ? <div className={styles.actionBlock}>
        <p>This report has not entered final review yet.</p>
        <button className={styles.primary} type="button" disabled={loading} onClick={requestReview}>
          Start final review
        </button>
      </div> : null}

      {result && reviewStarted ? <div className={styles.decisionBlock}>
        <div className={styles.reviewMeta}>
          <span>Approval ID</span>
          <strong>{approvalId}</strong>
        </div>

        <label>
          Review note
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Optional for approval. Required when requesting more evidence or rejecting delivery."
          />
        </label>

        <div className={styles.decisionActions}>
          <button
            className={styles.approve}
            type="button"
            disabled={loading || finalDecisionRecorded}
            onClick={() => transition("approved")}
          >
            Approve report
          </button>
          <button
            type="button"
            disabled={loading || normalizedStatus === "rejected"}
            onClick={() => transition("needs_more_evidence")}
          >
            Request more evidence
          </button>
          <button
            className={styles.reject}
            type="button"
            disabled={loading || finalDecisionRecorded}
            onClick={() => transition("rejected")}
          >
            Reject delivery
          </button>
        </div>
      </div> : null}

      <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>
        {deliveryAllowed
          ? "Approval is recorded and delivery is authorized for this exact run."
          : "Delivery remains blocked until an authorized approval is recorded."}
      </div>

      <div className={styles.downloadActions}>
        <button type="button" disabled={!deliveryAllowed || loading} onClick={downloadApprovedPdf}>
          Download approved final PDF
        </button>
        {service === "comprehensive" ? <button
          type="button"
          disabled={!deliveryAllowed || loading}
          onClick={downloadApprovedPackage}
        >
          Download approved delivery package
        </button> : null}
      </div>
    </section>

    {result ? <section className={styles.panel}>
      <details className={styles.record}>
        <summary>Exact review data</summary>
        <pre className={styles.code}>{jsonText(result)}</pre>
      </details>
    </section> : null}
  </main>;
}
