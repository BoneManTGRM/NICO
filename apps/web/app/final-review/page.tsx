"use client";

import {useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type ReviewResponse = {
  status?: string;
  run_id?: string;
  review_status?: string;
  approval_id?: string;
  approver?: string;
  approval_count?: number;
  approval?: {
    approval_id?: string;
    status?: string;
    approver?: string;
    run_id?: string;
    report_id?: string;
    review_snapshot?: Record<string, unknown>;
    evidence?: string[];
  };
  review?: ReviewResponse;
  error?: string;
};

function statusClass(status?: string) {
  if (status === "approved" || status === "ok" || status === "complete") return "status green";
  if (status === "pending" || status === "pending_review" || status === "needs_more_evidence") return "status yellow";
  if (status === "rejected" || status === "blocked" || status === "error") return "status red";
  return "status gray";
}

function JsonBlock({data}: {data?: unknown}) {
  if (!data) return <p className="muted">No review data returned yet.</p>;
  return <pre className="json-block">{JSON.stringify(data, null, 2)}</pre>;
}

export default function FinalReviewPage() {
  const [runId, setRunId] = useState("");
  const [reportId, setReportId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [approvalId, setApprovalId] = useState("");
  const [reviewer, setReviewer] = useState("frontend_reviewer");
  const [note, setNote] = useState("Final report reviewed and accepted by human reviewer.");
  const [evidence, setEvidence] = useState("Reviewed final report\nVerified unavailable-data notes\nConfirmed client/human acceptance decision");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ReviewResponse | null>(null);

  const backendConfigured = Boolean(API_URL);
  const activeApprovalId = approvalId || result?.approval?.approval_id || result?.approval_id || "";

  async function requestReview() {
    if (!backendConfigured) { setError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment."); return; }
    if (!runId) { setError("Run ID is required before requesting final review."); return; }
    setError(""); setLoading(true);
    try {
      const response = await fetch(`${API_URL}/reports/${encodeURIComponent(runId)}/final-review/request`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({customer_id: customerId, project_id: projectId, report_id: reportId, requester: reviewer, evidence: evidence.split("\n").map((item) => item.trim()).filter(Boolean)}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Final review request failed with ${response.status}`);
      setResult(data);
      setApprovalId(data?.approval?.approval_id || "");
    } catch (err) { setError(err instanceof Error ? err.message : "Final review request failed"); }
    finally { setLoading(false); }
  }

  async function loadReviewStatus() {
    if (!backendConfigured) { setError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment."); return; }
    if (!runId) { setError("Run ID is required before checking final review status."); return; }
    setError(""); setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId, project_id: projectId});
      const response = await fetch(`${API_URL}/reports/${encodeURIComponent(runId)}/final-review?${params.toString()}`, {cache: "no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Final review status failed with ${response.status}`);
      setResult(data);
      setApprovalId(data?.approval_id || "");
    } catch (err) { setError(err instanceof Error ? err.message : "Final review status failed"); }
    finally { setLoading(false); }
  }

  async function transitionReview(state: "approved" | "needs_more_evidence" | "rejected") {
    if (!backendConfigured) { setError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment."); return; }
    if (!activeApprovalId) { setError("Approval ID is required before updating final review."); return; }
    setError(""); setLoading(true);
    try {
      const response = await fetch(`${API_URL}/reports/final-review/${encodeURIComponent(activeApprovalId)}/${state}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({actor: reviewer, note}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Final review update failed with ${response.status}`);
      setResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Final review update failed"); }
    finally { setLoading(false); }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Final Review</p>
        <h1>Approve or request more evidence for a final report</h1>
        <p className="lead">Use this after running an Express assessment. Request final review, approve it only after human review, then rerun the assessment so the Client / Human Acceptance section can become evidence-bound.</p>
        <div className="hero-actions"><a href="/" className="secondary-link">Back to Command Center</a></div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Review Target</p><h2>Run and project scope</h2></div><span className={backendConfigured ? "status green" : "status red"}>{backendConfigured ? "Backend configured" : "Backend missing"}</span></div>
        <p className="warning-box">Do not approve a report automatically. Approval should mean a human reviewed the report, evidence, unavailable-data notes, and delivery context.</p>
        <div className="form-grid">
          <label>Run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="generated_at with colons replaced, report run_id, or copied run ID" /></label>
          <label>Report ID, optional<input value={reportId} onChange={(event) => setReportId(event.target.value)} placeholder="report_..." /></label>
          <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
          <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
          <label>Reviewer / actor<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label>
          <label>Approval ID<input value={approvalId} onChange={(event) => setApprovalId(event.target.value)} placeholder="Filled after request" /></label>
        </div>
        <label className="wide-label">Review evidence, one item per line<textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label>
        <label className="wide-label">Reviewer note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="report-actions">
          <button type="button" className="primary-button" disabled={!backendConfigured || loading || !runId} onClick={requestReview}>{loading ? "Working..." : "Request final review"}</button>
          <button type="button" disabled={!backendConfigured || loading || !runId} onClick={loadReviewStatus}>Check status</button>
          <button type="button" disabled={!backendConfigured || loading || !activeApprovalId} onClick={() => transitionReview("approved")}>Approve final report</button>
          <button type="button" disabled={!backendConfigured || loading || !activeApprovalId} onClick={() => transitionReview("needs_more_evidence")}>Needs more evidence</button>
          <button type="button" disabled={!backendConfigured || loading || !activeApprovalId} onClick={() => transitionReview("rejected")}>Reject</button>
        </div>
        {error ? <p className="error-box">{error}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Review Result</p><h2>{result?.review_status || result?.approval?.status || result?.status || "No review loaded"}</h2></div><span className={statusClass(result?.review_status || result?.approval?.status || result?.status)}>{result?.approval_id || result?.approval?.approval_id || "No approval"}</span></div>
        <JsonBlock data={result} />
      </section>
    </main>
  );
}
