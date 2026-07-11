"use client";

import {useState} from "react";
import ReportPathNotice, {reportPathConflictDetected} from "../ReportPathNotice";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const defaultTools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"];
const steps = ["authorization", "repo_evidence", "scanner_worker", "evidence_attachment", "scoring", "reports", "approval_request"];

type ProgressItem = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
type ReportPathConflict = {detected?: boolean; expected?: string; observed?: string[]; message?: string};
type ReviewValidation = {status?: string; ready_for_approval?: boolean; blockers?: string[]; checks?: Array<{id?: string; passed?: boolean; message?: string}>; rule?: string};
type ApprovedDelivery = {status?: string; artifact_type?: string; style_version?: string; run_id?: string; report_id?: string; approval_id?: string; approver?: string; approved_at?: string; client_delivery_allowed?: boolean; pdf_base64?: string; pdf_filename?: string; pdf_sha256?: string; source_draft_pdf_sha256?: string; approval_identity_sha256?: string; disclosure?: string};
type FullRunResult = {
  status?: string;
  status_refresh?: boolean;
  report_path?: string;
  report_path_label?: string;
  report_path_conflict?: ReportPathConflict;
  run_id?: string;
  repository?: string;
  customer_id?: string;
  project_id?: string;
  mode?: string;
  generated_at?: string;
  progress?: ProgressItem[];
  scanner?: {scan_id?: string; status?: string};
  scanner_evidence?: {status?: string; scan_id?: string; scanner_status?: string; scanner_results_count?: number};
  assessment?: {status?: string; report_path?: string; report_path_label?: string; report_path_conflict?: ReportPathConflict; maturity_signal?: {level?: string; score?: number; summary?: string}; client_delivery_verdict?: {status?: string; confidence?: string}; sections?: Array<{id?: string; label?: string; score?: number; status?: string; summary?: string}>};
  reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_style?: string; pdf_error?: string; report_id?: string; report_path?: string; report_path_label?: string; report_path_conflict?: ReportPathConflict};
  approval?: {approval_id?: string; status?: string; requested_action?: string; run_id?: string; report_id?: string; approver?: string; review_validation?: ReviewValidation; review_decision?: {state?: string; actor?: string; note?: string; decided_at?: string; client_delivery_allowed?: boolean}; approved_delivery?: ApprovedDelivery};
  approved_delivery?: ApprovedDelivery;
  human_review_required?: boolean;
  client_ready?: boolean;
};
type ReviewTransitionResponse = {status?: string; error?: string; approval?: FullRunResult["approval"]; approved_delivery?: ApprovedDelivery; review_validation?: ReviewValidation};

function statusClass(status?: string) {
  if (["complete", "approved", "green", "attached", "ready_for_human_decision"].includes(status || "")) return "status green";
  if (["running", "queued", "pending", "pending_review", "planned", "yellow", "needs_more_evidence"].includes(status || "")) return "status yellow";
  if (["failed", "blocked", "error", "rejected", "red"].includes(status || "")) return "status red";
  return "status gray";
}

function ProgressTimeline({progress}: {progress?: ProgressItem[]}) {
  const byStep = new Map((progress || []).map((item) => [item.step, item]));
  return <div className="results-grid">{steps.map((step) => {
    const item = byStep.get(step) || {step, status: "waiting", message: "Waiting for this step."};
    return <article className="result-card" key={step}><div className="result-head"><b>{step.replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{item.status || "waiting"}</span></div><p>{item.message || "No message returned."}</p>{item.evidence ? <pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre> : null}</article>;
  })}</div>;
}

function saveBase64Pdf(pdfBase64: string, filename: string) {
  const binary = window.atob(pdfBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const blob = new Blob([bytes], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "nico-full-assessment.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function FullRunPage() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [authorizedBy, setAuthorizedBy] = useState("frontend_reviewer");
  const [authorized, setAuthorized] = useState(false);
  const [runScanners, setRunScanners] = useState(true);
  const [buildReports, setBuildReports] = useState(true);
  const [requestReview, setRequestReview] = useState(true);
  const [reviewerActor, setReviewerActor] = useState("human_reviewer");
  const [reviewNote, setReviewNote] = useState("");
  const [result, setResult] = useState<FullRunResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const backendConfigured = Boolean(API_URL);
  const reportPath = result?.report_path || result?.reports?.report_path || result?.assessment?.report_path || "full_run";
  const reportPathLabel = result?.report_path_label || result?.reports?.report_path_label || result?.assessment?.report_path_label || "Full Assessment";
  const reportPathConflict = result?.report_path_conflict || result?.reports?.report_path_conflict || result?.assessment?.report_path_conflict;
  const deliveryActionsBlocked = reportPathConflictDetected(reportPathConflict);
  const approvalStatus = result?.approval?.status || "not_requested";
  const approvalTerminal = ["approved", "rejected"].includes(approvalStatus);
  const reviewValidation = result?.approval?.review_validation;
  const approvedDelivery = result?.approved_delivery || result?.approval?.approved_delivery;

  async function postFullRun(path: string, body: Record<string, unknown>) {
    const response = await fetch(`${API_URL}${path}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.code || data?.detail?.message || data?.error || `Full-run request failed with ${response.status}`);
    return data as FullRunResult;
  }

  async function runFullAssessment() {
    if (!backendConfigured) { setError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment."); return; }
    setError(""); setResult(null); setLoading(true);
    try {
      const data = await postFullRun("/assessment/full-run", {repository, authorization_confirmed: authorized, authorized, authorized_by: authorizedBy, customer_id: customerId, project_id: projectId, mode: "express", run_scanners: runScanners, refresh_full_evidence: true, build_reports: buildReports, create_final_review_request: requestReview, tools: defaultTools});
      setResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Full-run failed"); }
    finally { setLoading(false); }
  }

  async function refreshFullRun() {
    if (!backendConfigured || !result?.run_id) return;
    setError(""); setLoading(true);
    try {
      const data = await postFullRun(`/assessment/full-run/${result.run_id}/status`, {repository: result.repository || repository, authorization_confirmed: true, authorized: true, authorized_by: authorizedBy, customer_id: result.customer_id || customerId, project_id: result.project_id || projectId, scan_id: result.scanner?.scan_id || result.scanner_evidence?.scan_id || "", build_reports: false, create_final_review_request: false});
      setResult((current) => ({...data, approval: current?.approval || data.approval, approved_delivery: current?.approved_delivery || data.approved_delivery}));
    } catch (err) { setError(err instanceof Error ? err.message : "Full-run refresh failed"); }
    finally { setLoading(false); }
  }

  async function submitReviewDecision(state: "approved" | "needs_more_evidence" | "rejected") {
    const approvalId = result?.approval?.approval_id;
    if (!backendConfigured || !approvalId) return;
    if (!reviewerActor.trim()) { setError("A human reviewer identity is required."); return; }
    if (["needs_more_evidence", "rejected"].includes(state) && !reviewNote.trim()) { setError("A review note is required for this decision."); return; }
    setError(""); setReviewLoading(true);
    try {
      const response = await fetch(`${API_URL}/reports/final-review/${approvalId}/${state}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({actor: reviewerActor.trim(), note: reviewNote.trim()}), cache: "no-store"});
      const data = await response.json() as ReviewTransitionResponse;
      if (!response.ok || data.status === "blocked" || data.status === "not_found") throw new Error(data.error || `Final-review decision failed with ${response.status}`);
      setResult((current) => current ? {...current, approval: data.approval || current.approval, approved_delivery: data.approved_delivery || current.approved_delivery} : current);
      setReviewNote("");
    } catch (err) { setError(err instanceof Error ? err.message : "Final-review decision failed"); }
    finally { setReviewLoading(false); }
  }

  async function copyMarkdown() {
    if (deliveryActionsBlocked || !result?.reports?.markdown) return;
    await navigator.clipboard?.writeText(result.reports.markdown);
  }

  function downloadDraftPdf() {
    if (deliveryActionsBlocked || !result?.reports?.pdf_base64) return;
    try {
      saveBase64Pdf(result.reports.pdf_base64, result.reports.pdf_filename || "nico-full-assessment.pdf");
    } catch {
      setError("The Full Assessment draft PDF could not be decoded for download.");
    }
  }

  function downloadApprovedPdf() {
    if (deliveryActionsBlocked || !approvedDelivery?.client_delivery_allowed || !approvedDelivery.pdf_base64) return;
    try {
      saveBase64Pdf(approvedDelivery.pdf_base64, approvedDelivery.pdf_filename || "nico-full-assessment-approved.pdf");
    } catch {
      setError("The approved Full Assessment PDF could not be decoded for download.");
    }
  }

  return <main className="shell">
    <section className="hero"><p className="eyebrow">NICO Full Run</p><h1>One-click full assessment</h1><p className="lead">Run the full evidence-bound chain: authorization, repository evidence, scanner worker, evidence attachment, draft scoring, report package, and final human-review request.</p><div className="hero-actions"><a className="secondary-link" href="/">Back to dashboard</a></div></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Authorized target</p><h2>Full assessment setup</h2></div><span className={backendConfigured ? "status green" : "status red"}>{backendConfigured ? "Backend configured" : "Backend missing"}</span></div><p className="warning-box">Only assess repositories you own or are explicitly authorized to review. Client delivery remains blocked until human review approval and approved-artifact generation.</p><div className="form-grid"><label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label><label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label><label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} /></label></div><div className="checkbox-grid"><label><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} /> I confirm authorization.</label><label><input type="checkbox" checked={runScanners} onChange={(event) => setRunScanners(event.target.checked)} /> Run scanner worker.</label><label><input type="checkbox" checked={buildReports} onChange={(event) => setBuildReports(event.target.checked)} /> Build report package.</label><label><input type="checkbox" checked={requestReview} onChange={(event) => setRequestReview(event.target.checked)} /> Request final review.</label></div><div className="report-actions"><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runFullAssessment}>{loading ? "Running..." : "Run full assessment"}</button><button type="button" disabled={!result?.run_id || loading} onClick={refreshFullRun}>Refresh full-run status</button><button type="button" disabled={!result?.reports?.markdown || deliveryActionsBlocked} title={deliveryActionsBlocked ? "Disabled because report-path metadata conflicts." : "Copy the Full Assessment Markdown report."} onClick={copyMarkdown}>Copy Markdown</button><button type="button" disabled={!result?.reports?.pdf_base64 || deliveryActionsBlocked} title={deliveryActionsBlocked ? "Disabled because report-path metadata conflicts." : "Download the review-only Full Assessment PDF."} onClick={downloadDraftPdf}>Download draft PDF</button><button type="button" className="primary-button" disabled={!approvedDelivery?.client_delivery_allowed || !approvedDelivery?.pdf_base64 || deliveryActionsBlocked} title="Download the separately rendered, human-approved client-delivery PDF." onClick={downloadApprovedPdf}>Download approved PDF</button></div>{error ? <p className="error-box">{error}</p> : null}</section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Full-run result</p><h2>{result?.run_id ? `run_id=${result.run_id}` : "Awaiting full run"}</h2></div><span className={statusClass(result?.status)}>{result?.status || "not started"}</span></div>{result?.human_review_required && approvalStatus !== "approved" ? <p className="warning-box">Human review is required. client_ready={String(result.client_ready)}</p> : null}<ReportPathNotice expectedPath="full_run" reportPath={reportPath} reportPathLabel={reportPathLabel} conflict={reportPathConflict} clientReady={Boolean(approvedDelivery?.client_delivery_allowed)} /><div className="grid four target-grid"><article><b>Repository</b><span>{result?.repository || repository}</span></article><article><b>Scan ID</b><span>{result?.scanner?.scan_id || result?.scanner_evidence?.scan_id || "not available"}</span></article><article><b>Report ID</b><span>{result?.reports?.report_id || result?.approval?.report_id || "not available"}</span></article><article><b>Approval ID</b><span>{result?.approval?.approval_id || "not requested"}</span></article></div><ProgressTimeline progress={result?.progress} /></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Human review</p><h2>Final report decision</h2></div><span className={statusClass(approvalStatus)}>{approvalStatus.replaceAll("_", " ")}</span></div><p className="warning-box">Review the draft PDF, scorecard, evidence limits, unavailable data, and action plan before deciding. Approval generates a new hash-bound client-delivery PDF; the reviewed draft remains unchanged.</p><div className="form-grid"><label>Reviewer identity<input value={reviewerActor} onChange={(event) => setReviewerActor(event.target.value)} placeholder="Human reviewer name or role" /></label><label>Decision note<textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="Required when requesting more evidence or rejecting." /></label></div>{reviewValidation ? <div className="mini-panel"><div className="result-head"><b>Pre-approval validation</b><span className={statusClass(reviewValidation.status)}>{reviewValidation.status || "unknown"}</span></div><pre className="json-block">{JSON.stringify(reviewValidation, null, 2)}</pre></div> : <p className="muted">No final-review validation record is available yet.</p>}<div className="report-actions"><button type="button" className="primary-button" disabled={!result?.approval?.approval_id || !result?.reports?.pdf_base64 || deliveryActionsBlocked || approvalTerminal || reviewLoading} onClick={() => submitReviewDecision("approved")}>{reviewLoading ? "Generating approved artifact..." : "Approve and generate delivery PDF"}</button><button type="button" disabled={!result?.approval?.approval_id || !reviewNote.trim() || approvalTerminal || reviewLoading} onClick={() => submitReviewDecision("needs_more_evidence")}>Request more evidence</button><button type="button" disabled={!result?.approval?.approval_id || !reviewNote.trim() || approvalTerminal || reviewLoading} onClick={() => submitReviewDecision("rejected")}>Reject report</button></div>{result?.approval?.review_decision ? <p className="warning-box">Decision: {result.approval.review_decision.state || approvalStatus}; reviewer={result.approval.review_decision.actor || result.approval.approver || "not recorded"}; decided_at={result.approval.review_decision.decided_at || "not recorded"}.</p> : null}</section>

    {approvedDelivery?.status === "complete" ? <section className="section panel"><div className="section-head"><div><p className="eyebrow">Approved delivery</p><h2>{approvedDelivery.pdf_filename || "Approved Full Assessment PDF"}</h2></div><span className="status green">client delivery allowed</span></div><p className="warning-box">This is a separate approved artifact. The original draft remains preserved as the exact source reviewed by {approvedDelivery.approver || "the human reviewer"}.</p><div className="grid four target-grid"><article><b>Approved at</b><span>{approvedDelivery.approved_at || "not recorded"}</span></article><article><b>PDF SHA-256</b><span>{approvedDelivery.pdf_sha256 || "not recorded"}</span></article><article><b>Source draft SHA-256</b><span>{approvedDelivery.source_draft_pdf_sha256 || "not recorded"}</span></article><article><b>Approval identity SHA-256</b><span>{approvedDelivery.approval_identity_sha256 || "not recorded"}</span></article></div><div className="report-actions"><button type="button" className="primary-button" disabled={!approvedDelivery.pdf_base64 || deliveryActionsBlocked} onClick={downloadApprovedPdf}>Download approved PDF</button></div><p className="muted">{approvedDelivery.disclosure || "Evidence limitations and remediation requirements remain part of the approved assessment."}</p></section> : null}

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Evidence / output</p><h2>Scanner, score, report, approval</h2></div><span className={statusClass(result?.approval?.status)}>{result?.approval?.status || "approval not requested"}</span></div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Scanner evidence</p><pre className="json-block">{JSON.stringify(result?.scanner_evidence || {}, null, 2)}</pre></div><div className="mini-panel"><p className="eyebrow">Assessment</p><pre className="json-block">{JSON.stringify(result?.assessment?.maturity_signal || {}, null, 2)}</pre></div></div>{result?.reports?.markdown ? <details className="help-details"><summary>Report Markdown</summary><pre className="json-block">{result.reports.markdown}</pre></details> : <p className="muted">No report package returned yet.</p>}{result?.reports?.pdf_base64 ? <p className="warning-box">Draft PDF ready: {result.reports.pdf_filename || "nico-full-assessment.pdf"}. Human review is still required before client delivery.</p> : null}{result?.reports?.pdf_error ? <p className="warning-box">PDF: {result.reports.pdf_error}</p> : null}</section>
  </main>;
}
