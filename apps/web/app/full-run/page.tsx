"use client";

import {useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const defaultTools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint"];
const steps = ["authorization", "repo_evidence", "scanner_worker", "evidence_attachment", "scoring", "reports", "approval_request"];

type ProgressItem = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
type FullRunResult = {
  status?: string;
  status_refresh?: boolean;
  report_path?: string;
  run_id?: string;
  repository?: string;
  customer_id?: string;
  project_id?: string;
  mode?: string;
  generated_at?: string;
  progress?: ProgressItem[];
  scanner?: {scan_id?: string; status?: string};
  scanner_evidence?: {status?: string; scan_id?: string; scanner_status?: string; scanner_results_count?: number};
  assessment?: {status?: string; report_path?: string; maturity_signal?: {level?: string; score?: number; summary?: string}; client_delivery_verdict?: {status?: string; confidence?: string}; sections?: Array<{id?: string; label?: string; score?: number; status?: string; summary?: string}>};
  reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_error?: string; report_id?: string; report_path?: string};
  approval?: {approval_id?: string; status?: string; requested_action?: string; run_id?: string; report_id?: string};
  human_review_required?: boolean;
  client_ready?: boolean;
};

function statusClass(status?: string) {
  if (["complete", "approved", "green", "attached"].includes(status || "")) return "status green";
  if (["running", "queued", "pending", "pending_review", "planned", "yellow"].includes(status || "")) return "status yellow";
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

export default function FullRunPage() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [authorizedBy, setAuthorizedBy] = useState("frontend_reviewer");
  const [authorized, setAuthorized] = useState(false);
  const [runScanners, setRunScanners] = useState(true);
  const [buildReports, setBuildReports] = useState(true);
  const [requestReview, setRequestReview] = useState(true);
  const [result, setResult] = useState<FullRunResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const backendConfigured = Boolean(API_URL);
  const reportPath = result?.report_path || result?.reports?.report_path || result?.assessment?.report_path || "full_run";

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
      setResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Full-run refresh failed"); }
    finally { setLoading(false); }
  }

  async function copyMarkdown() {
    if (result?.reports?.markdown) await navigator.clipboard?.writeText(result.reports.markdown);
  }

  return <main className="shell">
    <section className="hero"><p className="eyebrow">NICO Full Run</p><h1>One-click full assessment</h1><p className="lead">Run the full evidence-bound chain: authorization, repository evidence, scanner worker, evidence attachment, draft scoring, report package, and final human-review request.</p><div className="hero-actions"><a className="secondary-link" href="/">Back to dashboard</a></div></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Authorized target</p><h2>Full assessment setup</h2></div><span className={backendConfigured ? "status green" : "status red"}>{backendConfigured ? "Backend configured" : "Backend missing"}</span></div><p className="warning-box">Only assess repositories you own or are explicitly authorized to review. Client delivery remains blocked until human review approval.</p><div className="form-grid"><label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label><label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label><label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} /></label></div><div className="checkbox-grid"><label><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} /> I confirm authorization.</label><label><input type="checkbox" checked={runScanners} onChange={(event) => setRunScanners(event.target.checked)} /> Run scanner worker.</label><label><input type="checkbox" checked={buildReports} onChange={(event) => setBuildReports(event.target.checked)} /> Build report package.</label><label><input type="checkbox" checked={requestReview} onChange={(event) => setRequestReview(event.target.checked)} /> Request final review.</label></div><div className="report-actions"><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runFullAssessment}>{loading ? "Running..." : "Run full assessment"}</button><button type="button" disabled={!result?.run_id || loading} onClick={refreshFullRun}>Refresh full-run status</button><button type="button" disabled={!result?.reports?.markdown} onClick={copyMarkdown}>Copy Markdown</button></div>{error ? <p className="error-box">{error}</p> : null}</section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Full-run result</p><h2>{result?.run_id ? `run_id=${result.run_id}` : "Awaiting full run"}</h2></div><span className={statusClass(result?.status)}>{result?.status || "not started"}</span></div>{result?.human_review_required ? <p className="warning-box">Human review is required. client_ready={String(result.client_ready)}</p> : null}<p className="summary-box"><b>Report path:</b> {reportPath}. This page is the Full Assessment path, not the older Express PDF path.</p><div className="grid four target-grid"><article><b>Repository</b><span>{result?.repository || repository}</span></article><article><b>Scan ID</b><span>{result?.scanner?.scan_id || result?.scanner_evidence?.scan_id || "not available"}</span></article><article><b>Report ID</b><span>{result?.reports?.report_id || result?.approval?.report_id || "not available"}</span></article><article><b>Approval ID</b><span>{result?.approval?.approval_id || "not requested"}</span></article></div><ProgressTimeline progress={result?.progress} /></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Evidence / output</p><h2>Scanner, score, report, approval</h2></div><span className={statusClass(result?.approval?.status)}>{result?.approval?.status || "approval not requested"}</span></div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Scanner evidence</p><pre className="json-block">{JSON.stringify(result?.scanner_evidence || {}, null, 2)}</pre></div><div className="mini-panel"><p className="eyebrow">Assessment</p><pre className="json-block">{JSON.stringify(result?.assessment?.maturity_signal || {}, null, 2)}</pre></div></div>{result?.reports?.markdown ? <details className="help-details"><summary>Report Markdown</summary><pre className="json-block">{result.reports.markdown}</pre></details> : <p className="muted">No report package returned yet.</p>}{result?.reports?.pdf_error ? <p className="warning-box">PDF: {result.reports.pdf_error}</p> : null}</section>
  </main>;
}
