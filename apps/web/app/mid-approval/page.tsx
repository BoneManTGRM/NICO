"use client";

import {useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type Validation = {status?: string; ready_for_approval?: boolean; blockers?: string[]; exception_item_ids?: string[]; exception_item_count?: number};
type Approval = {
  approval_id?: string;
  status?: string;
  run_id?: string;
  repository?: string;
  snapshot_id?: string;
  snapshot_commit_sha?: string;
  draft_report_id?: string;
  draft_pdf_sha256?: string;
  truth_sha256?: string;
  review_packet_id?: string;
  review_packet_sha256?: string;
  exception_item_ids?: string[];
  exception_item_count?: number;
  validation?: Validation;
  review_decision?: {state?: string; actor?: string; note?: string; reviewed_item_ids?: string[]; approved_report_id?: string};
  approved_report?: {report_id?: string; pdf_sha256?: string; pdf_filename?: string; approval_identity_sha256?: string; delivery_eligible?: boolean; client_delivery_allowed?: boolean};
  approved?: boolean;
  delivery_eligible?: boolean;
  client_delivery_allowed?: boolean;
};
type ReviewItem = {
  item_id: string;
  title?: string;
  category?: string;
  section_id?: string;
  severity?: string;
  reason?: string;
  evidence?: string[];
  blockers?: string[];
  inference_based?: boolean;
  score_change_material?: boolean;
  decision_status?: string;
  disposition?: {actor?: string; note?: string; decided_at?: string; disposition_sha256?: string};
};
type ReviewSummary = {
  status?: string;
  approval_ready?: boolean;
  expected_item_count?: number;
  accepted_item_count?: number;
  pending_item_count?: number;
  blocking_item_count?: number;
  stale_item_count?: number;
  accepted_item_ids?: string[];
  pending_item_ids?: string[];
  blocking_item_ids?: string[];
  items?: ReviewItem[];
  disposition_set_sha256?: string;
  rule?: string;
};
type ApiResponse = {
  status?: string;
  approval?: Approval;
  review_dispositions?: ReviewSummary;
  detail?: {message?: string; validation?: Validation; review_dispositions?: ReviewSummary; missing_reviewed_item_ids?: string[]};
};

function statusClass(value?: string) {
  const normalized = String(value || "").toLowerCase();
  if (["approved", "ready", "accepted", "accepted_inference_only"].includes(normalized)) return "status green";
  if (["pending", "review_required", "needs_more_evidence", "requested"].includes(normalized)) return "status yellow";
  if (["rejected", "blocked", "failed"].includes(normalized)) return "status red";
  return "status gray";
}

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

export default function MidApprovalPage() {
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [actor, setActor] = useState("");
  const [note, setNote] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null);
  const [itemNotes, setItemNotes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [activeItem, setActiveItem] = useState("");
  const [error, setError] = useState("");

  const allItems = reviewSummary?.items || [];
  const acceptedIds = reviewSummary?.accepted_item_ids || [];
  const structuredReviewReady = Boolean(reviewSummary?.approval_ready);
  const reviewProgress = useMemo(() => `${reviewSummary?.accepted_item_count || 0}/${reviewSummary?.expected_item_count || approval?.exception_item_count || 0}`, [reviewSummary, approval]);

  async function json(response: Response) {
    const data = await response.json() as ApiResponse;
    if (!response.ok) throw new Error(data.detail?.message || `Mid approval request failed with ${response.status}.`);
    return data;
  }

  async function loadReviewItems(approvalId: string) {
    const response = await fetch(`${API_URL}/assessment/mid-run/approval/${encodeURIComponent(approvalId)}/review-items`, {
      headers: {"X-NICO-Admin-Token": adminToken},
      cache: "no-store",
    });
    const data = await json(response);
    const summary = data.review_dispositions || null;
    setReviewSummary(summary);
    if (summary?.items) {
      setItemNotes((current) => {
        const next = {...current};
        summary.items?.forEach((item) => {
          if (!(item.item_id in next) && item.disposition?.note) next[item.item_id] = item.disposition.note;
        });
        return next;
      });
    }
  }

  async function requestApproval() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval/request`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"}),
        cache: "no-store",
      });
      const data = await json(response);
      const current = data.approval || null;
      setApproval(current);
      if (current?.approval_id) await loadReviewItems(current.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid approval request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshApproval() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      const data = await json(response);
      const current = data.approval || null;
      setApproval(current);
      if (current?.approval_id) await loadReviewItems(current.approval_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid approval status failed.");
    } finally {
      setLoading(false);
    }
  }

  async function recordDisposition(item: ReviewItem, decision: "accepted" | "accepted_inference_only" | "needs_more_evidence" | "rejected") {
    if (!approval?.approval_id || !adminToken.trim() || !actor.trim() || loading) return;
    const itemNote = (itemNotes[item.item_id] || "").trim();
    setError("");
    setLoading(true);
    setActiveItem(item.item_id);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/approval/${encodeURIComponent(approval.approval_id)}/review-items/${encodeURIComponent(item.item_id)}`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({decision, actor, note: itemNote}),
        cache: "no-store",
      });
      const data = await json(response);
      setReviewSummary(data.review_dispositions || null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid review disposition failed.");
    } finally {
      setActiveItem("");
      setLoading(false);
    }
  }

  async function decide(state: "approved" | "needs_more_evidence" | "rejected") {
    if (!approval?.approval_id || !adminToken.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/approval/${encodeURIComponent(approval.approval_id)}/${state}`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({actor, note, reviewed_item_ids: acceptedIds}),
        cache: "no-store",
      });
      const data = await json(response);
      setApproval(data.approval || null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid approval decision failed.");
    } finally {
      setLoading(false);
    }
  }

  async function downloadApprovedPdf() {
    if (!approval?.approved_report?.report_id || !adminToken.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/report/approved/pdf?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      if (!response.ok) {
        const data = await response.json() as {detail?: {message?: string}};
        throw new Error(data.detail?.message || "Approved Mid PDF download failed.");
      }
      const reportId = response.headers.get("X-NICO-Report-ID") || "";
      const pdfSha = response.headers.get("X-NICO-PDF-SHA256") || "";
      const approvalId = response.headers.get("X-NICO-Approval-ID") || "";
      const approvalIdentity = response.headers.get("X-NICO-Approval-Identity-SHA256") || "";
      if (reportId !== approval.approved_report.report_id || pdfSha !== approval.approved_report.pdf_sha256 || approvalId !== approval.approval_id || approvalIdentity !== approval.approved_report.approval_identity_sha256) {
        throw new Error("The approved PDF response did not match the approval identity.");
      }
      const blob = await response.blob();
      if (!blob.size || blob.type !== "application/pdf") throw new Error("The approved PDF failed content validation.");
      savePdf(blob, approval.approved_report.pdf_filename || "nico-mid-assessment-APPROVED.pdf");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approved Mid PDF download failed.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Human approval</h1>
      <p className="lead">Record a decision for every current exception before approving the exact run, snapshot, truth model, draft PDF, and review packet.</p>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Exact approval source</p><h2>Load or request approval</h2></div><span className={statusClass(approval?.status)}>{approval?.status || "not requested"}</span></div>
      <div className="form-grid">
        <label>Mid run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="midrun_..." /></label>
        <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
        <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
        <label>NICO admin token<input type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
      </div>
      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!API_URL || !runId.trim() || !adminToken.trim() || loading} onClick={requestApproval}>{loading ? "Validating exact state..." : "Request Mid approval"}</button>
        <button type="button" disabled={!runId.trim() || !adminToken.trim() || loading} onClick={refreshApproval}>Refresh approval</button>
      </div>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {approval ? <>
      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Validation</p><h2>{approval.approval_id}</h2></div><span className={statusClass(approval.validation?.status)}>{approval.validation?.status || "unknown"}</span></div>
        <div className="grid four target-grid">
          <article><b>Exception decisions</b><span>{reviewProgress}</span></article>
          <article><b>Structured review ready</b><span>{String(structuredReviewReady)}</span></article>
          <article><b>Approved artifact</b><span>{approval.approved_report?.report_id || "not created"}</span></article>
          <article><b>Client delivery</b><span>{String(Boolean(approval.client_delivery_allowed))}</span></article>
        </div>
        <details className="help-details"><summary>Exact identity</summary><pre className="json-block">{JSON.stringify({
          run_id: approval.run_id,
          snapshot_id: approval.snapshot_id,
          snapshot_commit_sha: approval.snapshot_commit_sha,
          draft_report_id: approval.draft_report_id,
          draft_pdf_sha256: approval.draft_pdf_sha256,
          truth_sha256: approval.truth_sha256,
          review_packet_id: approval.review_packet_id,
          review_packet_sha256: approval.review_packet_sha256,
          disposition_set_sha256: reviewSummary?.disposition_set_sha256,
        }, null, 2)}</pre></details>
        {approval.validation?.blockers?.length ? <div className="error-box">{approval.validation.blockers.join(" ")}</div> : null}
        {reviewSummary?.blocking_item_count ? <div className="error-box">{reviewSummary.blocking_item_count} item-level decision(s) currently block approval.</div> : null}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Review by exception</p><h2>Decide each current item</h2></div><span className={structuredReviewReady ? "status green" : "status yellow"}>{reviewProgress}</span></div>
        <div className="form-grid">
          <label>Reviewer name or role<input value={actor} onChange={(event) => setActor(event.target.value)} /></label>
        </div>
        {allItems.map((item) => <article className="result-card" key={item.item_id}>
          <div className="section-head">
            <div><p className="eyebrow">{item.severity || "medium"} · {item.category || "review"}</p><h3>{item.title || item.item_id}</h3></div>
            <span className={statusClass(item.decision_status)}>{item.decision_status || "pending"}</span>
          </div>
          <p>{item.reason}</p>
          <p><b>Section:</b> {item.section_id || "report"} · <b>Score-changing:</b> {String(Boolean(item.score_change_material))} · <b>Inference-based:</b> {String(Boolean(item.inference_based))}</p>
          {item.blockers?.length ? <details className="help-details"><summary>Missing or blocking evidence</summary><ul>{item.blockers.map((value) => <li key={value}>{value}</li>)}</ul></details> : null}
          {item.evidence?.length ? <details className="help-details"><summary>Available evidence</summary><ul>{item.evidence.map((value) => <li key={value}>{value}</li>)}</ul></details> : null}
          <label>Item-level reviewer note<textarea value={itemNotes[item.item_id] || ""} onChange={(event) => setItemNotes((current) => ({...current, [item.item_id]: event.target.value}))} /></label>
          <div className="report-actions">
            <button type="button" className="primary-button" disabled={!actor.trim() || (itemNotes[item.item_id] || "").trim().length < 8 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => recordDisposition(item, "accepted")}>{activeItem === item.item_id ? "Recording..." : "Accept as represented"}</button>
            <button type="button" disabled={!item.inference_based || item.score_change_material || !actor.trim() || (itemNotes[item.item_id] || "").trim().length < 8 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => recordDisposition(item, "accepted_inference_only")}>Accept as inference only</button>
            <button type="button" disabled={!actor.trim() || (itemNotes[item.item_id] || "").trim().length < 12 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => recordDisposition(item, "needs_more_evidence")}>Request evidence</button>
            <button type="button" disabled={!actor.trim() || (itemNotes[item.item_id] || "").trim().length < 12 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => recordDisposition(item, "rejected")}>Reject item</button>
          </div>
        </article>)}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Final decision</p><h2>Approve, request evidence, or reject</h2></div><span className={structuredReviewReady ? "status green" : "status yellow"}>{reviewSummary?.status || "review required"}</span></div>
        <label>Final decision note<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="report-actions">
          <button type="button" className="primary-button" disabled={!approval.validation?.ready_for_approval || !structuredReviewReady || actor.trim().length < 2 || note.trim().length < 10 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => decide("approved")}>Approve and generate separate PDF</button>
          <button type="button" disabled={actor.trim().length < 2 || note.trim().length < 5 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => decide("needs_more_evidence")}>Request more evidence</button>
          <button type="button" disabled={actor.trim().length < 2 || note.trim().length < 5 || loading || approval.status === "approved" || approval.status === "rejected"} onClick={() => decide("rejected")}>Reject assessment</button>
        </div>
      </section>

      {approval.status === "approved" ? <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Approved artifact</p><h2>{approval.approved_report?.report_id}</h2></div><span className="status green">Human reviewed</span></div>
        <p className="warning-box">The approved PDF is separate from the retained draft. Approval does not create a client link; secure delivery remains disabled.</p>
        <button type="button" className="primary-button" disabled={!approval.approved_report?.report_id || loading} onClick={downloadApprovedPdf}>Download verified approved PDF</button>
      </section> : null}
    </> : null}
  </main>;
}
