"use client";

import {useEffect, useState} from "react";
import type {ReactNode} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

const quickStartCommands = `pip install -r requirements.txt
python -m nico scan-test-lab
python -m nico assess local nico/test_lab --authorized
python -m nico assess report latest --format markdown
python -m nico assess verify latest`;

const assessmentCommands = `python -m nico assess local /path/to/project --authorized
python -m nico assess github owner/repo --authorized
python -m nico assess archive ./project.zip --authorized
python -m nico assess url https://staging.example.com --passive-only --authorized
python -m nico assess report latest --format markdown
python -m nico assess verify latest`;

const safetyRules = ["Defensive-only", "Authorized systems only", "No exploitation", "No brute force", "No authentication bypass", "No credential theft", "No destructive actions"];
const assessmentAreas = ["Code Audit", "Dependency / Library Ecosystem", "Secrets Exposure Review", "Static Analysis", "CI/CD Analysis", "Architecture & Technical Debt", "Velocity / Complexity", "QA / Functional Review", "Platform Parity", "Retainer Ops", "Repair Intelligence", "Scanner Worker", "Approval Queue", "Reports", "Markdown / HTML / PDF Reports"];
const targetCards = [["Express Technical Health Assessment", "90–95%", "Scanner/report automation with human review"], ["Mid Technical Health Assessment", "75–85%", "QA, parity, stakeholder, and roadmap evidence"], ["Ongoing Product Engineering Retainer", "55–70%", "Backlog, sprint, release, and approval workflows"], ["Full client-ready replacement", "75–85%", "Human validation before delivery"]];
const workerTools = ["pip-audit", "npm-audit", "osv-scanner", "semgrep", "bandit", "eslint", "typescript", "gitleaks", "trufflehog", "pytest", "npm-test", "npm-build"];

const defaultWorkerTools = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog"];

type Health = {status?: string; system?: string; mode?: string};
type Section = {id: string; label: string; score: number; status: string; summary: string; evidence: string[]; findings?: string[]; unavailable?: string[]};
type AssessmentResult = {status?: string; repository?: string; generated_at?: string; run_id?: string; executive_summary?: string; maturity_signal?: {level?: string; score?: number; summary?: string}; sections?: Section[]; findings?: string[]; repairs?: string[]; reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_error?: string}; human_review_required?: boolean};
type WorkflowResult = {status?: string; workflow?: string; target_coverage?: string; maturity_signal?: {level?: string; score?: number}; sections?: Section[]; qa_checklist?: string[]; parity_checklist?: string[]; six_month_roadmap?: string[]; weekly_status_report?: string[]; release_checklist?: string[]; human_approval_queue?: string[]};
type RepairResult = {status?: string; suggestion_id?: string; issue?: string; risk_level?: string; confidence?: string; strategy?: string; root_cause_hypothesis?: string; suggested_fix_summary?: string; patch_steps?: string[]; affected_files_or_systems?: string[]; evidence?: string[]; patch_prompt?: string; test_plan?: string; rollback_plan?: string; quality_checklist?: string[]; next_step?: string; human_review_required?: boolean};
type ScannerItem = {scanner?: string; command_intent?: string; status?: string; exit_code?: number | null; duration_seconds?: number; evidence_summary?: string; safe_output_preview?: string; risk_severity?: string; recommended_repair?: string; unavailable_data_notes?: string[]};
type ScanResult = {scan_id?: string; repository?: string; status?: string; tools_requested?: string[]; tools_run?: string[]; unavailable_tools?: string[]; failed_tools?: string[]; timed_out_tools?: string[]; scanner_results?: ScannerItem[]; evidence_summary?: unknown; unavailable_data_notes?: string[]; retention_note?: string; human_review_required?: boolean};
type ApprovalItem = {approval_id?: string; status?: string; requested_action?: string; evidence?: string[]; affected_files_or_systems?: string[]; risk_level?: string; test_plan?: string; rollback_plan?: string; requester?: string; approver?: string; created_at?: string; updated_at?: string; audit_log?: unknown[]};
type ReportPackage = {status?: string; report_id?: string; run_id?: string; formats?: {markdown?: string; html?: string; json?: unknown; pdf?: string | null}; unavailable_data_notes?: string[]};

function statusClass(status?: string) { if (status === "green" || status === "passed" || status === "approved" || status === "complete") return "status green"; if (status === "yellow" || status === "pending" || status === "running" || status === "queued") return "status yellow"; if (status === "red" || status === "failed" || status === "error" || status === "rejected" || status === "timeout") return "status red"; return "status gray"; }
function ListBlock({items}: {items?: string[]}) { if (!items?.length) return <p className="muted">No evidence returned yet.</p>; return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>; }
function JsonBlock({data}: {data?: unknown}) { if (!data) return <p className="muted">No data yet.</p>; return <pre className="json-block">{JSON.stringify(data, null, 2)}</pre>; }
function splitLines(value: string) { return value.split("\n").map((line) => line.trim()).filter(Boolean); }
function extractBlock(text: string, label: string) { const pattern = new RegExp(`${label}:\\n([\\s\\S]*?)(?=\\n[A-Za-z /]+:|$)`, "i"); return text.match(pattern)?.[1]?.trim() || ""; }
function HelpDetails({title, children}: {title: string; children: ReactNode}) { return <details className="help-details"><summary>{title}</summary><div className="help-body">{children}</div></details>; }
function ResultSections({result}: {result?: WorkflowResult | null}) { if (!result?.sections?.length) return null; return <div className="results-grid">{result.sections.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{item.status} · {item.score}/100</span></div><p>{item.summary}</p><h3>Evidence</h3><ListBlock items={item.evidence} />{item.findings?.length ? <><h3>Findings</h3><ListBlock items={item.findings} /></> : null}{item.unavailable?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable} /></> : null}</article>)}</div>; }

export default function Page() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  const [assessmentError, setAssessmentError] = useState("");
  const [copied, setCopied] = useState("");
  const [midNotes, setMidNotes] = useState("QA evidence:\n\nParity notes:\n\nStakeholder notes:\n\nRoadmap notes:\n\nKnown risks:");
  const [retainerNotes, setRetainerNotes] = useState("Commit summary:\n\nPR summary:\n\nIssue summary:\n\nBlockers:\n\nRelease notes:\n\nRoadmap notes:");
  const [midResult, setMidResult] = useState<WorkflowResult | null>(null);
  const [retainerResult, setRetainerResult] = useState<WorkflowResult | null>(null);
  const [opsError, setOpsError] = useState("");
  const [repairIssue, setRepairIssue] = useState("Missing dependency caused CI failure after adding upload endpoint.");
  const [repairEvidence, setRepairEvidence] = useState("NICO CI failed in Run all tests\nFastAPI UploadFile/Form endpoint requires multipart parser\nFix should be minimal and testable");
  const [affectedFiles, setAffectedFiles] = useState("requirements.txt\nnico/api/main.py");
  const [repairResult, setRepairResult] = useState<RepairResult | null>(null);
  const [repairError, setRepairError] = useState("");
  const [workerCustomerId, setWorkerCustomerId] = useState("default_customer");
  const [workerProjectId, setWorkerProjectId] = useState("default_project");
  const [authorizedBy, setAuthorizedBy] = useState("frontend_reviewer");
  const [authorizationScope, setAuthorizationScope] = useState("repository assessment only");
  const [selectedWorkerTools, setSelectedWorkerTools] = useState<string[]>(defaultWorkerTools);
  const [scanId, setScanId] = useState("");
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState("");
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [approvalError, setApprovalError] = useState("");
  const [reportNotes, setReportNotes] = useState("Review findings.\nPrioritize repair suggestions.\nHuman-review before client delivery.");
  const [reportPackage, setReportPackage] = useState<ReportPackage | null>(null);
  const [reportExport, setReportExport] = useState("");
  const [reportError, setReportError] = useState("");

  const backendConfigured = Boolean(API_URL);
  const backendOnline = health?.status === "ok";

  async function checkBackend() {
    if (!backendConfigured) { setHealthError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment."); return; }
    setHealthError("");
    try { const response = await fetch(`${API_URL}/health`, {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(`Health check failed with ${response.status}`); setHealth(data); }
    catch (error) { setHealth(null); setHealthError(error instanceof Error ? error.message : "Backend health check failed"); }
  }
  useEffect(() => { checkBackend(); }, []);

  async function runHostedAssessment() {
    if (!backendConfigured) { setAssessmentError("Backend URL is not configured in Vercel."); return; }
    setAssessmentError(""); setCopied(""); setReportError(""); setAssessment(null); setLoading(true);
    try { const response = await fetch(`${API_URL}/assessment/github`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({repository, authorized, client_name: clientName, project_name: projectName, assessment_mode: "express", timeframe_days: 180, customer_id: workerCustomerId, project_id: workerProjectId, authorized_by: authorizedBy || "frontend_reviewer", refresh_full_evidence: true})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Assessment failed with ${response.status}`); setAssessment(data); }
    catch (error) { setAssessmentError(error instanceof Error ? error.message : "Assessment failed"); }
    finally { setLoading(false); }
  }

  async function startWorkerScan() {
    if (!backendConfigured) { setScanError("Backend URL is not configured in Vercel."); return; }
    setScanError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/worker/scan`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({repository, authorized, customer_id: workerCustomerId, project_id: workerProjectId, authorized_by: authorizedBy, authorization_scope: authorizationScope, tools: selectedWorkerTools})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Scanner failed with ${response.status}`); setScanResult(data); setScanId(data.scan_id || ""); }
    catch (error) { setScanError(error instanceof Error ? error.message : "Scanner worker failed"); }
    finally { setLoading(false); }
  }

  async function refreshScan() {
    if (!backendConfigured || !scanId) return;
    setScanError("");
    try { const response = await fetch(`${API_URL}/worker/scan/${scanId}`, {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(`Scan status failed with ${response.status}`); setScanResult(data); }
    catch (error) { setScanError(error instanceof Error ? error.message : "Scan refresh failed"); }
  }

  async function runMidWorkflow() {
    if (!backendConfigured) { setOpsError("Backend URL is not configured in Vercel."); return; }
    setOpsError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/assessment/mid`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({authorized, client_name: clientName, project_name: projectName, qa_evidence: extractBlock(midNotes, "QA evidence"), parity_notes: extractBlock(midNotes, "Parity notes"), stakeholder_notes: extractBlock(midNotes, "Stakeholder notes"), roadmap_notes: extractBlock(midNotes, "Roadmap notes"), known_risks: extractBlock(midNotes, "Known risks"), customer_id: workerCustomerId, project_id: workerProjectId})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Mid workflow failed with ${response.status}`); setMidResult(data); }
    catch (error) { setOpsError(error instanceof Error ? error.message : "Mid workflow failed"); }
    finally { setLoading(false); }
  }

  async function runRetainerWorkflow() {
    if (!backendConfigured) { setOpsError("Backend URL is not configured in Vercel."); return; }
    setOpsError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/retainer/ops`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({authorized, client_name: clientName, project_name: projectName, commit_summary: extractBlock(retainerNotes, "Commit summary"), pr_summary: extractBlock(retainerNotes, "PR summary"), issue_summary: extractBlock(retainerNotes, "Issue summary"), blockers: extractBlock(retainerNotes, "Blockers"), release_notes: extractBlock(retainerNotes, "Release notes"), roadmap_notes: extractBlock(retainerNotes, "Roadmap notes"), customer_id: workerCustomerId, project_id: workerProjectId})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Retainer workflow failed with ${response.status}`); setRetainerResult(data); }
    catch (error) { setOpsError(error instanceof Error ? error.message : "Retainer workflow failed"); }
    finally { setLoading(false); }
  }

  async function runRepairSuggestion() {
    if (!backendConfigured) { setRepairError("Backend URL is not configured in Vercel."); return; }
    setRepairError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/repair/suggest`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({issue: repairIssue, evidence: splitLines(repairEvidence), affected_files: splitLines(affectedFiles), customer_id: workerCustomerId, project_id: workerProjectId})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Repair suggestion failed with ${response.status}`); setRepairResult(data); }
    catch (error) { setRepairError(error instanceof Error ? error.message : "Repair suggestion failed"); }
    finally { setLoading(false); }
  }

  async function loadApprovals() {
    if (!backendConfigured) return;
    setApprovalError("");
    try { const response = await fetch(`${API_URL}/approvals`, {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(`Approvals failed with ${response.status}`); setApprovals(Array.isArray(data) ? data : Array.isArray(data?.approvals) ? data.approvals : []); }
    catch (error) { setApprovalError(error instanceof Error ? error.message : "Approvals failed"); }
  }

  async function transitionApproval(approvalId: string, action: "approve" | "reject" | "needs-more-evidence") {
    if (!backendConfigured) return;
    setApprovalError("");
    try { const response = await fetch(`${API_URL}/approvals/${approvalId}/${action}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({actor: authorizedBy || "frontend_reviewer", note: "Updated from NICO frontend"})}); if (!response.ok) throw new Error(`Approval update failed with ${response.status}`); await loadApprovals(); }
    catch (error) { setApprovalError(error instanceof Error ? error.message : "Approval update failed"); }
  }

  async function createReportPackage() {
    if (!backendConfigured) { setReportError("Backend URL is not configured in Vercel."); return; }
    setReportError(""); setReportExport(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/reports/package`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({customer_id: workerCustomerId, project_id: workerProjectId, client_name: clientName, project_name: projectName, repository, source_scope: repository, authorization_statement: authorized ? "User confirmed authorization in NICO frontend." : "Authorization not confirmed in frontend.", maturity_signal: assessment?.maturity_signal || midResult?.maturity_signal || retainerResult?.maturity_signal || {}, evidence_readiness: scanResult?.evidence_summary || {}, findings: [...(assessment?.findings || []), ...splitLines(reportNotes)], sections: assessment?.sections || [], unavailable_data_notes: scanResult?.unavailable_data_notes || [], next_steps: splitLines(reportNotes)})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Report package failed with ${response.status}`); setReportPackage(data); }
    catch (error) { setReportError(error instanceof Error ? error.message : "Report package failed"); }
    finally { setLoading(false); }
  }

  async function exportReport(format: "markdown" | "html" | "json") {
    if (!backendConfigured || !reportPackage?.run_id) return;
    try { const response = await fetch(`${API_URL}/reports/${reportPackage.run_id}/export`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({format})}); const data = await response.json(); if (!response.ok) throw new Error(`Report export failed with ${response.status}`); setReportExport(typeof data.content === "string" ? data.content : JSON.stringify(data.content, null, 2)); }
    catch (error) { setReportError(error instanceof Error ? error.message : "Report export failed"); }
  }

  function toggleWorkerTool(tool: string) { setSelectedWorkerTools((items) => items.includes(tool) ? items.filter((item) => item !== tool) : [...items, tool]); }
  async function copyReport(kind: "markdown" | "html") { const text = assessment?.reports?.[kind]; if (!text) return; await navigator.clipboard?.writeText(text); setCopied(`${kind.toUpperCase()} report copied`); }
  async function copyScanId() { if (!scanId) return; await navigator.clipboard?.writeText(scanId); }
  function downloadPdf() { const encoded = assessment?.reports?.pdf_base64; if (!encoded) { setReportError(assessment?.reports?.pdf_error || "PDF was not returned for this assessment run. Use Copy Markdown/HTML or rerun after backend deploy finishes."); return; } const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0)); const blob = new Blob([bytes], {type: "application/pdf"}); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = assessment?.reports?.pdf_filename || "nico-assessment.pdf"; anchor.click(); URL.revokeObjectURL(url); }

  return (
    <main className="shell">
      <section className="hero"><p className="eyebrow">NICO Hosted Command Center</p><h1>Highest realistic assessment targets</h1><p className="lead">NICO targets Express, Mid, Retainer, scanner-worker, reports, approvals, and repair-intelligence workflows with evidence-bound outputs and human review.</p><div className="hero-actions"><a href="#hosted" className="primary-link">Run Express</a><a href="#scanner" className="secondary-link">Scanner Worker</a><a href="#repair" className="secondary-link">Repair Intelligence</a><a href="#guide" className="secondary-link">How to use</a></div></section>

      <section id="guide" className="section panel"><div className="section-head"><div><p className="eyebrow">Clicky Guide</p><h2>How to use each section</h2></div><span className="status blue">Dropdown help</span></div><div className="help-grid"><HelpDetails title="Dashboard / System Status"><ol><li>Confirm backend health says ok.</li><li>Check target coverage and storage status.</li><li>If storage says unavailable, do not treat latest results as permanent.</li><li>Use this before client demos or customer work.</li></ol></HelpDetails><HelpDetails title="Scanner Worker"><ol><li>Confirm authorization.</li><li>Enter repository, customer/project IDs, authorized by, and scope.</li><li>Select tools.</li><li>Start scan and copy scan ID.</li><li>Refresh until complete.</li><li>Treat unavailable tools as missing evidence, not a clean result.</li></ol></HelpDetails><HelpDetails title="Approval Queue"><ol><li>Load approvals.</li><li>Review requested action, evidence, affected files, risk, test plan, and rollback plan.</li><li>Approve, reject, or request more evidence.</li><li>This section does not create PRs automatically.</li></ol></HelpDetails><HelpDetails title="Reports"><ol><li>Run Express or scanner if possible.</li><li>Add client/project details.</li><li>Create report package.</li><li>Export Markdown, HTML, or JSON.</li><li>PDF is shown for Express when the backend returns pdf_base64.</li></ol></HelpDetails><HelpDetails title="Repair Intelligence"><ol><li>Paste exact issue or failing symptom.</li><li>Add evidence and affected files.</li><li>Review patch prompt, test plan, rollback plan, confidence, and risk.</li><li>Create approval only if a human agrees.</li></ol></HelpDetails><HelpDetails title="Code-change policy"><ol><li>NICO suggests fixes and draft PR plans.</li><li>NICO should not push to main, auto-merge, deploy, or edit production.</li><li>Use suggest → approval queue → draft branch/PR → CI → human review → customer merge.</li></ol></HelpDetails></div></section>

      <section id="targets" className="section panel status-panel"><div className="section-head"><div><p className="eyebrow">Coverage Targets</p><h2>Realistic upper-end goals</h2></div><span className="status blue">Human review required</span></div><div className="grid four target-grid">{targetCards.map(([title, target, note]) => <article key={title}><b>{title}</b><span className="target-number">{target}</span><small>{note}</small></article>)}</div></section>

      <section className="section panel status-panel"><div className="section-head"><div><p className="eyebrow">System Status</p><h2>Frontend / Railway backend</h2></div><span className={backendOnline ? "status green" : backendConfigured ? "status yellow" : "status red"}>{backendOnline ? "Backend online" : backendConfigured ? "Backend configured" : "Backend missing"}</span></div><div className="grid three"><article><b>Frontend</b><span>https://app.nicoaudit.com</span></article><article><b>Backend URL</b><span>{API_URL || "Not configured"}</span></article><article><b>Health</b><span>{health?.status || healthError || "Checking"}</span></article></div><button type="button" className="small-button" onClick={checkBackend}>Check backend</button>{healthError ? <p className="error-box">{healthError}</p> : null}</section>

      <section id="hosted" className="section panel"><div className="section-head"><div><p className="eyebrow">Express Assessment</p><h2>Assess an authorized GitHub repository</h2></div><span className="status gray">90–95%</span></div><HelpDetails title="Express instructions"><ul><li>Use for fast repo health checks.</li><li>Best input is exact owner/repo plus client/project names.</li><li>Review every evidence item and unavailable-data note.</li><li>Run Express again after backend deploys; the previous result is cleared before each new run.</li></ul></HelpDetails><p className="warning-box">Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.</p><div className="form-grid"><label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label><label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" /></label><label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" /></label></div><label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this target or have explicit permission to assess it.</label><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runHostedAssessment}>{loading ? "Running fresh assessment..." : "Run fresh Express assessment"}</button>{assessmentError ? <p className="error-box">{assessmentError}</p> : null}</section>

      <section className="section panel"><div className="section-head"><div><p className="eyebrow">Express Result</p><h2>{assessment?.maturity_signal?.level ? `${assessment.maturity_signal.level} maturity signal` : "Awaiting assessment"}</h2></div><span className={assessment?.maturity_signal?.level ? "status blue" : "status gray"}>{assessment?.status || "No report"}</span></div>{assessment?.generated_at ? <p className="summary-box"><b>Fresh run generated:</b> {assessment.generated_at}{assessment.run_id ? ` · run_id=${assessment.run_id}` : ""}</p> : null}{assessment?.human_review_required ? <p className="warning-box">Human review is required before client-facing delivery.</p> : null}{assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}<div className="results-grid">{assessment?.sections?.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{item.status} · {item.score}/100</span></div><p>{item.summary}</p><h3>Evidence</h3><ListBlock items={item.evidence} />{item.findings?.length ? <><h3>Findings</h3><ListBlock items={item.findings} /></> : null}{item.unavailable?.length ? <><h3>Unavailable data</h3><ListBlock items={item.unavailable} /></> : null}</article>)}</div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Findings</p><ListBlock items={assessment?.findings} /></div><div className="mini-panel"><p className="eyebrow">Repairs</p><ListBlock items={assessment?.repairs} /></div></div><div className="report-actions"><button type="button" disabled={!assessment?.reports?.markdown} onClick={() => copyReport("markdown")}>Copy Markdown</button><button type="button" disabled={!assessment?.reports?.html} onClick={() => copyReport("html")}>Copy HTML</button><button type="button" disabled={!assessment} onClick={downloadPdf}>Download PDF</button>{copied ? <span className="muted">{copied}</span> : null}</div>{assessment && !assessment.reports?.pdf_base64 ? <p className="warning-box">PDF is not available for this run. {assessment.reports?.pdf_error || "Use Copy Markdown/HTML, or rerun after the backend deployment finishes."}</p> : null}{reportError ? <p className="error-box">{reportError}</p> : null}</section>

      <section id="scanner" className="section panel"><div className="section-head"><div><p className="eyebrow">Scanner Worker</p><h2>Controlled scanner execution and evidence collection</h2></div><span className={statusClass(scanResult?.status)}>{scanResult?.status || "not run"}</span></div><HelpDetails title="Scanner Worker instructions"><ul><li>Use only on authorized GitHub repositories.</li><li>The default selected tools now match the Express evidence gates.</li><li>Test/build commands require stronger isolation and may be marked unavailable.</li><li>Unavailable means missing evidence, not a clean result.</li></ul></HelpDetails><div className="form-grid"><label>Customer ID<input value={workerCustomerId} onChange={(event) => setWorkerCustomerId(event.target.value)} /></label><label>Project ID<input value={workerProjectId} onChange={(event) => setWorkerProjectId(event.target.value)} /></label><label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} placeholder="Name or role" /></label></div><label className="wide-label">Authorization scope<textarea value={authorizationScope} onChange={(event) => setAuthorizationScope(event.target.value)} /></label><div className="checkbox-grid">{workerTools.map((tool) => <label key={tool}><input type="checkbox" checked={selectedWorkerTools.includes(tool)} onChange={() => toggleWorkerTool(tool)} />{tool}</label>)}</div><div className="report-actions"><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || !authorizedBy || loading} onClick={startWorkerScan}>{loading ? "Starting..." : "Start scanner worker"}</button><button type="button" disabled={!scanId} onClick={refreshScan}>Check scan status</button><button type="button" disabled={!scanId} onClick={copyScanId}>Copy scan ID</button></div>{scanError ? <p className="error-box">{scanError}</p> : null}{scanResult ? <><div className="grid three inset-grid"><article><b>Scan ID</b><span>{scanResult.scan_id}</span></article><article><b>Tools run</b><span>{scanResult.tools_run?.length || 0}</span></article><article><b>Unavailable</b><span>{scanResult.unavailable_tools?.length || 0}</span></article></div><HelpDetails title="Evidence summary"><JsonBlock data={scanResult.evidence_summary} /></HelpDetails><div className="results-grid">{scanResult.scanner_results?.map((item, index) => <article className="result-card" key={`${item.scanner}-${index}`}><div className="result-head"><b>{item.scanner}</b><span className={statusClass(item.status)}>{item.status}</span></div><p>{item.command_intent}</p><p><b>Risk:</b> {item.risk_severity || "unknown"}</p><h3>Evidence</h3><p>{item.evidence_summary}</p><h3>Recommended repair</h3><p>{item.recommended_repair}</p>{item.unavailable_data_notes?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable_data_notes} /></> : null}</article>)}</div><p className="warning-box">{scanResult.retention_note || "Temporary workspace should be deleted after scan completion."}</p></> : null}</section>

      <section id="repair" className="section panel"><div className="section-head"><div><p className="eyebrow">Repair Intelligence</p><h2>Best code-fix suggestions with approval gates</h2></div><span className="status gray">Suggest only</span></div><HelpDetails title="How to get the best repair suggestion"><ol><li>Paste the exact failing symptom, CI error, or finding.</li><li>Add evidence as separate lines.</li><li>Add affected files if known.</li><li>Run suggestion.</li><li>Use the patch prompt for a draft repair branch only after human approval.</li></ol></HelpDetails><div className="form-grid repair-grid"><label>Issue / failing symptom<textarea value={repairIssue} onChange={(event) => setRepairIssue(event.target.value)} /></label><label>Evidence, one item per line<textarea value={repairEvidence} onChange={(event) => setRepairEvidence(event.target.value)} /></label><label>Affected files, one per line<textarea value={affectedFiles} onChange={(event) => setAffectedFiles(event.target.value)} /></label></div><button type="button" className="primary-button" disabled={!backendConfigured || loading} onClick={runRepairSuggestion}>{loading ? "Generating..." : "Generate repair suggestion"}</button>{repairError ? <p className="error-box">{repairError}</p> : null}{repairResult ? <div className="repair-result"><p className="summary-box"><b>{repairResult.strategy}</b> · risk {repairResult.risk_level} · confidence {repairResult.confidence}</p><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Root-cause hypothesis</p><p>{repairResult.root_cause_hypothesis}</p><p className="eyebrow">Suggested fix</p><p>{repairResult.suggested_fix_summary}</p></div><div className="mini-panel"><p className="eyebrow">Patch steps</p><ListBlock items={repairResult.patch_steps} /></div></div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Test plan</p><p>{repairResult.test_plan}</p></div><div className="mini-panel"><p className="eyebrow">Rollback plan</p><p>{repairResult.rollback_plan}</p></div></div><HelpDetails title="Patch prompt for a draft branch / PR"><textarea readOnly value={repairResult.patch_prompt || ""} /></HelpDetails><HelpDetails title="Quality checklist"><ListBlock items={repairResult.quality_checklist} /></HelpDetails></div> : null}</section>

      <section id="mid" className="section panel"><div className="section-head"><div><p className="eyebrow">Mid Assessment</p><h2>QA, parity, stakeholder, and roadmap workflow</h2></div><span className="status gray">75–85%</span></div><HelpDetails title="Mid instructions"><p>Paste real evidence under each heading. Empty sections become unavailable instead of invented. Use this for QA, platform parity, stakeholder discovery, and roadmap draft work.</p></HelpDetails><div className="command-card"><textarea value={midNotes} onChange={(event) => setMidNotes(event.target.value)} aria-label="Mid assessment evidence" /></div><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runMidWorkflow}>Run Mid workflow</button>{midResult ? <><p className="summary-box">Mid workflow target: {midResult.target_coverage}. Maturity: {midResult.maturity_signal?.level} {midResult.maturity_signal?.score}/100.</p><ResultSections result={midResult} /><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">QA checklist</p><ListBlock items={midResult.qa_checklist} /></div><div className="mini-panel"><p className="eyebrow">Parity checklist</p><ListBlock items={midResult.parity_checklist} /></div></div></> : null}</section>

      <section id="retainer" className="section panel"><div className="section-head"><div><p className="eyebrow">Retainer Ops</p><h2>Weekly status, backlog health, release, and approval queue</h2></div><span className="status gray">55–70%</span></div><HelpDetails title="Retainer instructions"><p>Use this for ongoing support. Paste weekly operating evidence and review status, blockers, release readiness, and approval needs before client delivery.</p></HelpDetails><div className="command-card"><textarea value={retainerNotes} onChange={(event) => setRetainerNotes(event.target.value)} aria-label="Retainer operating evidence" /></div><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runRetainerWorkflow}>Run Retainer Ops</button>{opsError ? <p className="error-box">{opsError}</p> : null}{retainerResult ? <><p className="summary-box">Retainer target: {retainerResult.target_coverage}. Maturity: {retainerResult.maturity_signal?.level} {retainerResult.maturity_signal?.score}/100.</p><ResultSections result={retainerResult} /><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Weekly status</p><ListBlock items={retainerResult.weekly_status_report} /></div><div className="mini-panel"><p className="eyebrow">Release checklist</p><ListBlock items={retainerResult.release_checklist} /></div></div><div className="mini-panel inset-grid"><p className="eyebrow">Human approval queue</p><ListBlock items={retainerResult.human_approval_queue} /></div></> : null}</section>

      <section id="approvals" className="section panel"><div className="section-head"><div><p className="eyebrow">Approval Queue</p><h2>Human approval before code-change workflows</h2></div><span className="status blue">{approvals.length} items</span></div><HelpDetails title="Approval Queue instructions"><p>Use this section to approve, reject, or request more evidence. It does not create PRs automatically.</p></HelpDetails><button type="button" className="small-button" onClick={loadApprovals}>Load approvals</button>{approvalError ? <p className="error-box">{approvalError}</p> : null}<div className="results-grid">{approvals.map((item) => <article className="result-card" key={item.approval_id}><div className="result-head"><b>{item.requested_action || "approval"}</b><span className={statusClass(item.status)}>{item.status}</span></div><p><b>ID:</b> {item.approval_id}</p><p><b>Risk:</b> {item.risk_level || "unknown"}</p><h3>Evidence</h3><ListBlock items={item.evidence} /><h3>Affected files/systems</h3><ListBlock items={item.affected_files_or_systems} /><h3>Test plan</h3><p>{item.test_plan || "No test plan."}</p><h3>Rollback plan</h3><p>{item.rollback_plan || "No rollback plan."}</p><div className="report-actions"><button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "approve")}>Approve</button><button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "reject")}>Reject</button><button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "needs-more-evidence")}>Needs more evidence</button></div></article>)}</div></section>

      <section id="reports-ui" className="section panel"><div className="section-head"><div><p className="eyebrow">Reports</p><h2>Client-ready report package</h2></div><span className={statusClass(reportPackage?.status)}>{reportPackage?.status || "not created"}</span></div><HelpDetails title="Reports instructions"><p>Create a report package from current evidence. Export Markdown, HTML, or JSON. Express PDF downloads are handled in the Express Result section when the assessment response includes pdf_base64.</p></HelpDetails><label className="wide-label">Next steps / report notes<textarea value={reportNotes} onChange={(event) => setReportNotes(event.target.value)} /></label><div className="report-actions"><button type="button" className="primary-button" disabled={!backendConfigured || loading} onClick={createReportPackage}>Create report package</button><button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("markdown")}>Export Markdown</button><button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("html")}>Export HTML</button><button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("json")}>Export JSON</button></div>{reportError ? <p className="error-box">{reportError}</p> : null}{reportPackage ? <><div className="grid three inset-grid"><article><b>Report ID</b><span>{reportPackage.report_id}</span></article><article><b>Run ID</b><span>{reportPackage.run_id}</span></article><article><b>PDF</b><span>{reportPackage.formats?.pdf ? "available" : "unavailable"}</span></article></div><ListBlock items={reportPackage.unavailable_data_notes} />{reportExport ? <textarea readOnly value={reportExport} /> : null}</> : null}</section>

      <section className="section panel"><div className="section-head"><div><p className="eyebrow">Assessment Scope</p><h2>Evidence-bound checks</h2></div><span className="status gray">No fake data</span></div><div className="scope-grid">{assessmentAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}</div></section>

      <section id="commands" className="section panel"><div className="section-head"><div><p className="eyebrow">No-server fallback</p><h2>Run NICO from your local CLI</h2></div><span className="status blue">CLI ready</span></div><HelpDetails title="When to use CLI mode"><p>Use local CLI when hosted assessment is unavailable or when you need local folder/archive/passive URL assessment. Keep authorization proof and do not use it on unrelated systems.</p></HelpDetails><div className="command-grid"><div className="command-card"><b>First test with NICO test lab</b><textarea readOnly defaultValue={quickStartCommands} /></div><div className="command-card"><b>Assess authorized systems locally</b><textarea readOnly defaultValue={assessmentCommands} /></div></div></section>

      <section id="safety" className="section two-col"><div className="panel"><p className="eyebrow">Safety Boundary</p><h2>Allowed use</h2><ul className="tight-list">{safetyRules.map((rule) => <li key={rule}>{rule}</li>)}</ul></div><div className="panel"><p className="eyebrow">Human Review</p><h2>Required for client delivery</h2><ul className="tight-list"><li>Validate facts and evidence before delivery.</li><li>Confirm stakeholder context.</li><li>Approve production-impacting changes.</li><li>Review roadmap and resourcing recommendations.</li></ul></div></section>
    </main>
  );
}
