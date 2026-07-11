"use client";

import {useEffect, useMemo, useState} from "react";
import type {ReactNode} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

const safetyRules = [
  "Defensive-only",
  "Authorized systems only",
  "No exploitation",
  "No brute force",
  "No authentication bypass",
  "No credential theft",
  "No destructive actions",
];

const assessmentAreas = [
  "Repository mapping",
  "Dependency and library review",
  "Secrets exposure review",
  "Static analysis",
  "CI/CD evidence",
  "Architecture and technical debt",
  "Complexity and velocity",
  "Evidence ledger",
  "Human review",
  "Controlled delivery",
];

const serviceCards = [
  ["Express Assessment", "Fast technical baseline", "Current repository evidence and a rapid human-review-bound report."],
  ["Mid Assessment", "Complete evidence-bound run", "One snapshot, one run ID, full scanners, scoring, trust gates, and focused review."],
  ["Retainer Operations", "Ongoing engineering evidence", "Weekly backlog, release, blocker, and approval workflows."],
  ["Evidence coverage", "Calculated after each run", "NICO shows a percentage only when it is calculated from the actual assessment evidence."],
];

const workerTools = [
  "pip-audit",
  "npm-audit",
  "osv-scanner",
  "semgrep",
  "bandit",
  "eslint",
  "typescript",
  "gitleaks",
  "trufflehog",
  "pytest",
  "npm-test",
  "npm-build",
];

const defaultWorkerTools = [
  "pip-audit",
  "npm-audit",
  "osv-scanner",
  "bandit",
  "semgrep",
  "eslint",
  "typescript",
  "gitleaks",
  "trufflehog",
];

type AssessmentType = "express" | "mid";
type Health = {status?: string; system?: string; mode?: string};
type Section = {
  id: string;
  label: string;
  score: number;
  status: string;
  summary: string;
  evidence: string[];
  findings?: string[];
  unavailable?: string[];
};
type EvidenceCoverage = {percent?: number; calculated?: boolean; label?: string; numerator?: number; denominator?: number};
type AssessmentDocument = {
  status?: string;
  executive_summary?: string;
  maturity_signal?: {level?: string; score?: number; summary?: string};
  sections?: Section[];
  findings?: string[];
  repairs?: string[];
  unavailable_data_notes?: string[];
  human_review_required?: boolean;
  evidence_coverage?: EvidenceCoverage;
};
type ExpressAssessmentResult = AssessmentDocument & {
  repository?: string;
  generated_at?: string;
  run_id?: string;
  reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_error?: string};
};
type MidProgress = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
type MidRunResult = {
  status?: string;
  run_id?: string;
  repository?: string;
  assessment_type?: string;
  service_tier?: string;
  unified_run?: boolean;
  express_report_generated?: boolean;
  report_generation_status?: string;
  report_generation_note?: string;
  repository_snapshot?: {snapshot_id?: string; commit_sha?: string; tree_sha?: string; captured_at?: string; default_branch?: string};
  repository_evidence?: {status?: string; evidence_id?: string; unavailable_data_notes?: string[]};
  complexity_evidence?: {status?: string; evidence_id?: string; files_analyzed?: number; unavailable_data_notes?: string[]};
  scanner?: {scan_id?: string; status?: string};
  scanner_evidence?: {status?: string; scan_id?: string; snapshot_match?: boolean};
  assessment?: AssessmentDocument;
  progress?: MidProgress[];
  human_review_required?: boolean;
  client_ready?: boolean;
  evidence_coverage?: EvidenceCoverage;
  persistence?: {recorded?: boolean; durable?: boolean; adapter?: string; restored?: boolean; note?: string};
};
type WorkflowResult = {
  status?: string;
  workflow?: string;
  maturity_signal?: {level?: string; score?: number};
  sections?: Section[];
  weekly_status_report?: string[];
  release_checklist?: string[];
  human_approval_queue?: string[];
};
type RepairResult = {
  status?: string;
  issue?: string;
  risk_level?: string;
  confidence?: string;
  strategy?: string;
  root_cause_hypothesis?: string;
  suggested_fix_summary?: string;
  patch_steps?: string[];
  evidence?: string[];
  patch_prompt?: string;
  test_plan?: string;
  rollback_plan?: string;
  quality_checklist?: string[];
};
type ScannerItem = {
  scanner?: string;
  command_intent?: string;
  status?: string;
  evidence_summary?: string;
  risk_severity?: string;
  recommended_repair?: string;
  unavailable_data_notes?: string[];
};
type ScanResult = {
  scan_id?: string;
  repository?: string;
  status?: string;
  tools_requested?: string[];
  tools_run?: string[];
  unavailable_tools?: string[];
  scanner_results?: ScannerItem[];
  evidence_summary?: unknown;
  unavailable_data_notes?: string[];
  retention_note?: string;
};
type ApprovalItem = {
  approval_id?: string;
  status?: string;
  requested_action?: string;
  evidence?: string[];
  affected_files_or_systems?: string[];
  risk_level?: string;
  test_plan?: string;
  rollback_plan?: string;
};
type ReportPackage = {
  status?: string;
  report_id?: string;
  run_id?: string;
  formats?: {markdown?: string; html?: string; json?: unknown; pdf?: string | null};
};

function statusClass(status?: string) {
  if (["green", "passed", "approved", "complete", "attached", "verified", "available", "ok"].includes(status || "")) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "skipped"].includes(status || "")) return "status yellow";
  if (["red", "failed", "error", "rejected", "timeout", "blocked"].includes(status || "")) return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No evidence returned yet.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

function JsonBlock({data}: {data?: unknown}) {
  if (!data) return <p className="muted">No data yet.</p>;
  return <pre className="json-block">{JSON.stringify(data, null, 2)}</pre>;
}

function HelpDetails({title, children}: {title: string; children: ReactNode}) {
  return <details className="help-details"><summary>{title}</summary><div className="help-body">{children}</div></details>;
}

function ResultSections({sections}: {sections?: Section[]}) {
  if (!sections?.length) return null;
  return <div className="results-grid">{sections.map((item) => <article className="result-card" key={item.id}>
    <div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{item.status} · {item.score}/100</span></div>
    <p>{item.summary}</p>
    <h3>Evidence</h3><ListBlock items={item.evidence} />
    {item.findings?.length ? <><h3>Findings</h3><ListBlock items={item.findings} /></> : null}
    {item.unavailable?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable} /></> : null}
  </article>)}</div>;
}

function CoverageBadge({coverage}: {coverage?: EvidenceCoverage}) {
  const percent = Number(coverage?.percent);
  if (!coverage?.calculated || !Number.isFinite(percent)) return <span className="status gray">Coverage calculated after run</span>;
  return <span className="status blue">{coverage.label || "Automated evidence coverage"}: {Math.max(0, Math.min(100, percent))}%</span>;
}

function splitLines(value: string) {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}

function extractBlock(text: string, label: string) {
  const pattern = new RegExp(`${label}:\\n([\\s\\S]*?)(?=\\n[A-Za-z /]+:|$)`, "i");
  return text.match(pattern)?.[1]?.trim() || "";
}

export default function Page() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [assessmentType, setAssessmentType] = useState<AssessmentType>("express");
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [assessmentError, setAssessmentError] = useState("");
  const [expressResult, setExpressResult] = useState<ExpressAssessmentResult | null>(null);
  const [midResult, setMidResult] = useState<MidRunResult | null>(null);
  const [midRunId, setMidRunId] = useState("");
  const [copied, setCopied] = useState("");

  const [workerCustomerId, setWorkerCustomerId] = useState("default_customer");
  const [workerProjectId, setWorkerProjectId] = useState("default_project");
  const [authorizedBy, setAuthorizedBy] = useState("frontend_reviewer");
  const [authorizationScope, setAuthorizationScope] = useState("repository assessment only");
  const [selectedWorkerTools, setSelectedWorkerTools] = useState<string[]>(defaultWorkerTools);
  const [scanId, setScanId] = useState("");
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState("");

  const [repairIssue, setRepairIssue] = useState("Missing dependency caused CI failure after adding upload endpoint.");
  const [repairEvidence, setRepairEvidence] = useState("NICO CI failed in Run all tests\nFastAPI UploadFile/Form endpoint requires multipart parser\nFix should be minimal and testable");
  const [affectedFiles, setAffectedFiles] = useState("requirements.txt\nnico/api/main.py");
  const [repairResult, setRepairResult] = useState<RepairResult | null>(null);
  const [repairError, setRepairError] = useState("");

  const [retainerNotes, setRetainerNotes] = useState("Commit summary:\n\nPR summary:\n\nIssue summary:\n\nBlockers:\n\nRelease notes:\n\nRoadmap notes:");
  const [retainerResult, setRetainerResult] = useState<WorkflowResult | null>(null);
  const [opsError, setOpsError] = useState("");

  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [approvalError, setApprovalError] = useState("");
  const [reportNotes, setReportNotes] = useState("Review findings.\nPrioritize repair suggestions.\nHuman-review before client delivery.");
  const [reportPackage, setReportPackage] = useState<ReportPackage | null>(null);
  const [reportExport, setReportExport] = useState("");
  const [reportError, setReportError] = useState("");

  const backendConfigured = Boolean(API_URL);
  const backendOnline = health?.status === "ok";
  const selectedDocument = assessmentType === "express" ? expressResult : midResult?.assessment;
  const selectedCoverage = assessmentType === "express" ? expressResult?.evidence_coverage : midResult?.evidence_coverage || midResult?.assessment?.evidence_coverage;
  const assessmentHeading = assessmentType === "express" ? "EXPRESS ASSESSMENT" : "MID ASSESSMENT";
  const assessmentDescription = assessmentType === "express"
    ? "Fast evidence-bound technical baseline"
    : "Complete evidence-bound technical assessment";

  const midProgress = useMemo(() => midResult?.progress || [], [midResult]);

  async function parseResponse(response: Response) {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.detail?.message || data?.detail?.error || data?.error || `Request failed with ${response.status}`);
    }
    return data;
  }

  async function checkBackend() {
    if (!backendConfigured) {
      setHealthError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment.");
      return;
    }
    setHealthError("");
    try {
      const response = await fetch(`${API_URL}/health`, {cache: "no-store"});
      setHealth(await parseResponse(response));
    } catch (error) {
      setHealth(null);
      setHealthError(error instanceof Error ? error.message : "Backend health check failed");
    }
  }

  useEffect(() => { void checkBackend(); }, []);

  function selectAssessmentType(value: AssessmentType) {
    setAssessmentType(value);
    setAssessmentError("");
    setCopied("");
  }

  async function runSelectedAssessment() {
    if (!backendConfigured) {
      setAssessmentError("Backend URL is not configured in Vercel.");
      return;
    }
    setAssessmentError("");
    setCopied("");
    setReportError("");
    setLoading(true);
    try {
      if (assessmentType === "express") {
        setExpressResult(null);
        const response = await fetch(`${API_URL}/assessment/github`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            repository,
            authorized,
            client_name: clientName,
            project_name: projectName,
            assessment_mode: "express",
            timeframe_days: 180,
            customer_id: workerCustomerId,
            project_id: workerProjectId,
            authorized_by: authorizedBy || "frontend_reviewer",
            refresh_full_evidence: true,
          }),
        });
        setExpressResult(await parseResponse(response));
      } else {
        setMidResult(null);
        setMidRunId("");
        const response = await fetch(`${API_URL}/assessment/mid-run`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            repository,
            customer_id: workerCustomerId,
            project_id: workerProjectId,
            client_name: clientName,
            project_name: projectName,
            authorized_by: authorizedBy || "frontend_reviewer",
            authorization_scope: authorizationScope || "repository assessment only",
            authorization_confirmed: authorized,
            authorized,
            timeframe_days: 180,
            run_scanners: true,
            refresh_full_evidence: true,
            auto_continue: true,
          }),
        });
        const data = await parseResponse(response) as MidRunResult;
        setMidResult(data);
        setMidRunId(data.run_id || "");
      }
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Assessment failed");
    } finally {
      setLoading(false);
    }
  }

  async function refreshMidAssessment() {
    if (!backendConfigured || !midRunId) return;
    setAssessmentError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(midRunId)}/status`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({auto_continue: true}),
        cache: "no-store",
      });
      setMidResult(await parseResponse(response));
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Mid Assessment refresh failed");
    } finally {
      setLoading(false);
    }
  }

  async function startWorkerScan() {
    if (!backendConfigured) { setScanError("Backend URL is not configured in Vercel."); return; }
    setScanError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/worker/scan`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({repository, authorized, customer_id: workerCustomerId, project_id: workerProjectId, authorized_by: authorizedBy, authorization_scope: authorizationScope, tools: selectedWorkerTools}),
      });
      const data = await parseResponse(response) as ScanResult;
      setScanResult(data);
      setScanId(data.scan_id || "");
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "Scanner worker failed");
    } finally {
      setLoading(false);
    }
  }

  async function refreshScan() {
    if (!backendConfigured || !scanId) return;
    setScanError("");
    try {
      const response = await fetch(`${API_URL}/worker/scan/${encodeURIComponent(scanId)}`, {cache: "no-store"});
      setScanResult(await parseResponse(response));
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "Scan refresh failed");
    }
  }

  async function runRepairSuggestion() {
    if (!backendConfigured) { setRepairError("Backend URL is not configured in Vercel."); return; }
    setRepairError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/repair/suggest`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({issue: repairIssue, evidence: splitLines(repairEvidence), affected_files: splitLines(affectedFiles), customer_id: workerCustomerId, project_id: workerProjectId}),
      });
      setRepairResult(await parseResponse(response));
    } catch (error) {
      setRepairError(error instanceof Error ? error.message : "Repair suggestion failed");
    } finally {
      setLoading(false);
    }
  }

  async function runRetainerWorkflow() {
    if (!backendConfigured) { setOpsError("Backend URL is not configured in Vercel."); return; }
    setOpsError("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/retainer/ops`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          authorized,
          client_name: clientName,
          project_name: projectName,
          commit_summary: extractBlock(retainerNotes, "Commit summary"),
          pr_summary: extractBlock(retainerNotes, "PR summary"),
          issue_summary: extractBlock(retainerNotes, "Issue summary"),
          blockers: extractBlock(retainerNotes, "Blockers"),
          release_notes: extractBlock(retainerNotes, "Release notes"),
          roadmap_notes: extractBlock(retainerNotes, "Roadmap notes"),
          customer_id: workerCustomerId,
          project_id: workerProjectId,
        }),
      });
      setRetainerResult(await parseResponse(response));
    } catch (error) {
      setOpsError(error instanceof Error ? error.message : "Retainer workflow failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadApprovals() {
    if (!backendConfigured) return;
    setApprovalError("");
    try {
      const response = await fetch(`${API_URL}/approvals`, {cache: "no-store"});
      const data = await parseResponse(response);
      setApprovals(Array.isArray(data) ? data : Array.isArray(data?.approvals) ? data.approvals : []);
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : "Approvals failed");
    }
  }

  async function transitionApproval(approvalId: string, action: "approve" | "reject" | "needs-more-evidence") {
    if (!backendConfigured) return;
    setApprovalError("");
    try {
      const response = await fetch(`${API_URL}/approvals/${encodeURIComponent(approvalId)}/${action}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({actor: authorizedBy || "frontend_reviewer", note: "Updated from NICO frontend"}),
      });
      await parseResponse(response);
      await loadApprovals();
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : "Approval update failed");
    }
  }

  async function createReportPackage() {
    if (!backendConfigured) { setReportError("Backend URL is not configured in Vercel."); return; }
    if (assessmentType === "mid") {
      setReportError("Mid reports must be generated by the dedicated same-run Mid report pipeline. The generic report builder is disabled for Mid to prevent identity and score mismatches.");
      return;
    }
    setReportError("");
    setReportExport("");
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/reports/package`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          customer_id: workerCustomerId,
          project_id: workerProjectId,
          client_name: clientName,
          project_name: projectName,
          repository,
          source_scope: repository,
          authorization_statement: authorized ? "User confirmed authorization in NICO frontend." : "Authorization not confirmed in frontend.",
          maturity_signal: expressResult?.maturity_signal || retainerResult?.maturity_signal || {},
          evidence_readiness: scanResult?.evidence_summary || {},
          findings: [...(expressResult?.findings || []), ...splitLines(reportNotes)],
          sections: expressResult?.sections || [],
          unavailable_data_notes: scanResult?.unavailable_data_notes || [],
          next_steps: splitLines(reportNotes),
        }),
      });
      setReportPackage(await parseResponse(response));
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Report package failed");
    } finally {
      setLoading(false);
    }
  }

  async function exportReport(format: "markdown" | "html" | "json") {
    if (!backendConfigured || !reportPackage?.run_id) return;
    try {
      const response = await fetch(`${API_URL}/reports/${encodeURIComponent(reportPackage.run_id)}/export`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({format}),
      });
      const data = await parseResponse(response);
      setReportExport(typeof data.content === "string" ? data.content : JSON.stringify(data.content, null, 2));
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Report export failed");
    }
  }

  function toggleWorkerTool(tool: string) {
    setSelectedWorkerTools((items) => items.includes(tool) ? items.filter((item) => item !== tool) : [...items, tool]);
  }

  async function copyExpressReport(kind: "markdown" | "html") {
    const text = expressResult?.reports?.[kind];
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setCopied(`${kind.toUpperCase()} report copied`);
  }

  function downloadExpressPdf() {
    const encoded = expressResult?.reports?.pdf_base64;
    if (!encoded) {
      setReportError(expressResult?.reports?.pdf_error || "PDF was not returned for this Express run.");
      return;
    }
    const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], {type: "application/pdf"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = expressResult?.reports?.pdf_filename || "nico-express-assessment.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Hosted Command Center</p>
      <h1>Evidence-bound technical oversight</h1>
      <p className="lead">Choose Express for a rapid baseline or Mid for one complete snapshot-bound assessment run. NICO never treats missing evidence as a clean result.</p>
      <div className="hero-actions">
        <a href="#assessment" className="primary-link">Run assessment</a>
        <a href="#scanner" className="secondary-link">Scanner worker</a>
        <a href="#repair" className="secondary-link">Repair intelligence</a>
        <a href="#approvals" className="secondary-link">Approvals</a>
      </div>
    </section>

    <section className="section panel status-panel">
      <div className="section-head">
        <div><p className="eyebrow">Service model</p><h2>Measured evidence, not accuracy promises</h2></div>
        <span className="status blue">Human review required</span>
      </div>
      <div className="grid four target-grid">{serviceCards.map(([title, target, note]) => <article key={title}><b>{title}</b><span>{target}</span><small>{note}</small></article>)}</div>
    </section>

    <section className="section panel status-panel">
      <div className="section-head">
        <div><p className="eyebrow">System status</p><h2>Frontend and backend</h2></div>
        <span className={backendOnline ? "status green" : backendConfigured ? "status yellow" : "status red"}>{backendOnline ? "Backend online" : backendConfigured ? "Backend configured" : "Backend missing"}</span>
      </div>
      <div className="grid three">
        <article><b>Frontend</b><span>https://app.nicoaudit.com</span></article>
        <article><b>Backend URL</b><span>{API_URL || "Not configured"}</span></article>
        <article><b>Health</b><span>{health?.status || healthError || "Checking"}</span></article>
      </div>
      <button type="button" className="small-button" onClick={checkBackend}>Check backend</button>
      {healthError ? <p className="error-box">{healthError}</p> : null}
    </section>

    <section id="assessment" className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">{assessmentHeading}</p><h2>{assessmentDescription}</h2></div>
        <CoverageBadge coverage={selectedCoverage} />
      </div>
      <div className="report-actions" aria-label="Assessment type">
        <button type="button" className={assessmentType === "express" ? "primary-button" : ""} aria-pressed={assessmentType === "express"} onClick={() => selectAssessmentType("express")}>Express</button>
        <button type="button" className={assessmentType === "mid" ? "primary-button" : ""} aria-pressed={assessmentType === "mid"} onClick={() => selectAssessmentType("mid")}>Mid</button>
      </div>
      <HelpDetails title={`${assessmentType === "express" ? "Express" : "Mid"} instructions`}>
        {assessmentType === "express" ? <ul>
          <li>Use Express for a fast authorized repository baseline.</li>
          <li>Review every evidence item and unavailable-data note.</li>
          <li>The report remains human-review-bound.</li>
        </ul> : <ul>
          <li>Mid creates one run ID and captures one exact repository commit.</li>
          <li>Repository evidence and scanners remain bound to that commit.</li>
          <li>No Express report or separate score-combination step is created.</li>
          <li>Use Check Mid status while the snapshot-bound scanner is running.</li>
        </ul>}
      </HelpDetails>
      <p className="warning-box">Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.</p>
      <div className="form-grid">
        <label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label>
        <label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" /></label>
        <label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" /></label>
      </div>
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this target or have explicit permission to assess it.</label>
      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runSelectedAssessment}>
          {loading ? "Running fresh assessment..." : assessmentType === "express" ? "Run fresh Express assessment" : "Run fresh Mid assessment"}
        </button>
        {assessmentType === "mid" ? <button type="button" disabled={!midRunId || loading} onClick={refreshMidAssessment}>Check Mid status</button> : null}
      </div>
      {assessmentError ? <p className="error-box">{assessmentError}</p> : null}
    </section>

    <section className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">{assessmentType === "express" ? "Express result" : "Mid run"}</p><h2>{selectedDocument?.maturity_signal?.level ? `${selectedDocument.maturity_signal.level} maturity signal` : assessmentType === "mid" && midRunId ? midRunId : "Awaiting assessment"}</h2></div>
        <span className={statusClass(assessmentType === "express" ? expressResult?.status : midResult?.status)}>{assessmentType === "express" ? expressResult?.status || "No report" : midResult?.status || "Not started"}</span>
      </div>
      {assessmentType === "express" ? <>
        {expressResult?.generated_at ? <p className="summary-box"><b>Fresh run generated:</b> {expressResult.generated_at}{expressResult.run_id ? ` · run_id=${expressResult.run_id}` : ""}</p> : null}
        {expressResult?.human_review_required ? <p className="warning-box">Human review is required before client-facing delivery.</p> : null}
        {expressResult?.executive_summary ? <p className="summary-box">{expressResult.executive_summary}</p> : null}
        <ResultSections sections={expressResult?.sections} />
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Findings</p><ListBlock items={expressResult?.findings} /></div>
          <div className="mini-panel"><p className="eyebrow">Repairs</p><ListBlock items={expressResult?.repairs} /></div>
        </div>
        <div className="report-actions">
          <button type="button" disabled={!expressResult?.reports?.markdown} onClick={() => copyExpressReport("markdown")}>Copy Markdown</button>
          <button type="button" disabled={!expressResult?.reports?.html} onClick={() => copyExpressReport("html")}>Copy HTML</button>
          <button type="button" disabled={!expressResult} onClick={downloadExpressPdf}>Download PDF</button>
          {copied ? <span className="muted">{copied}</span> : null}
        </div>
      </> : <>
        {midResult ? <>
          <p className="summary-box"><b>Unified Mid run:</b> {midResult.run_id || "not recorded"} · repository={midResult.repository || repository}</p>
          <div className="grid four target-grid">
            <article><b>Snapshot commit</b><span>{midResult.repository_snapshot?.commit_sha?.slice(0, 12) || "pending"}</span></article>
            <article><b>Scanner</b><span>{midResult.scanner?.status || "not started"}</span></article>
            <article><b>Repository evidence</b><span>{midResult.repository_evidence?.status || "pending"}</span></article>
            <article><b>Client ready</b><span>{String(Boolean(midResult.client_ready))}</span></article>
          </div>
          <p className="warning-box">{midResult.report_generation_note || "Mid-specific report generation remains blocked until the same-run evidence pipeline is complete and reviewed."}</p>
          <div className="results-grid">{midProgress.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
            <div className="result-head"><b>{String(item.step || "step").replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{item.status || "unknown"}</span></div>
            <p>{item.message || "No message returned."}</p>
            {item.evidence ? <HelpDetails title="Step evidence"><JsonBlock data={item.evidence} /></HelpDetails> : null}
          </article>)}</div>
          <ResultSections sections={midResult.assessment?.sections} />
          <HelpDetails title="Mid identity and persistence"><JsonBlock data={{
            run_id: midResult.run_id,
            assessment_type: midResult.assessment_type,
            unified_run: midResult.unified_run,
            express_report_generated: midResult.express_report_generated,
            report_generation_status: midResult.report_generation_status,
            repository_snapshot: midResult.repository_snapshot,
            scanner: midResult.scanner,
            scanner_evidence: midResult.scanner_evidence,
            persistence: midResult.persistence,
          }} /></HelpDetails>
        </> : <p className="muted">Select Mid and run an authorized repository assessment.</p>}
      </>}
      {reportError ? <p className="error-box">{reportError}</p> : null}
    </section>

    <section id="scanner" className="section panel">
      <div className="section-head"><div><p className="eyebrow">Scanner worker</p><h2>Controlled scanner execution and evidence collection</h2></div><span className={statusClass(scanResult?.status)}>{scanResult?.status || "not run"}</span></div>
      <HelpDetails title="Scanner instructions"><ul><li>Use only on authorized GitHub repositories.</li><li>Unavailable means missing evidence, not a clean result.</li><li>Mid normally starts its own snapshot-bound scanner; this panel is for controlled standalone diagnostics.</li></ul></HelpDetails>
      <div className="form-grid">
        <label>Customer ID<input value={workerCustomerId} onChange={(event) => setWorkerCustomerId(event.target.value)} /></label>
        <label>Project ID<input value={workerProjectId} onChange={(event) => setWorkerProjectId(event.target.value)} /></label>
        <label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} placeholder="Name or role" /></label>
      </div>
      <label className="wide-label">Authorization scope<textarea value={authorizationScope} onChange={(event) => setAuthorizationScope(event.target.value)} /></label>
      <div className="checkbox-grid">{workerTools.map((tool) => <label key={tool}><input type="checkbox" checked={selectedWorkerTools.includes(tool)} onChange={() => toggleWorkerTool(tool)} />{tool}</label>)}</div>
      <div className="report-actions">
        <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || !authorizedBy || loading} onClick={startWorkerScan}>Start scanner worker</button>
        <button type="button" disabled={!scanId} onClick={refreshScan}>Check scan status</button>
      </div>
      {scanError ? <p className="error-box">{scanError}</p> : null}
      {scanResult ? <>
        <div className="grid three inset-grid"><article><b>Scan ID</b><span>{scanResult.scan_id}</span></article><article><b>Tools run</b><span>{scanResult.tools_run?.length || 0}</span></article><article><b>Unavailable</b><span>{scanResult.unavailable_tools?.length || 0}</span></article></div>
        <HelpDetails title="Evidence summary"><JsonBlock data={scanResult.evidence_summary} /></HelpDetails>
        <div className="results-grid">{scanResult.scanner_results?.map((item, index) => <article className="result-card" key={`${item.scanner}-${index}`}>
          <div className="result-head"><b>{item.scanner}</b><span className={statusClass(item.status)}>{item.status}</span></div>
          <p>{item.command_intent}</p><p><b>Risk:</b> {item.risk_severity || "unknown"}</p><h3>Evidence</h3><p>{item.evidence_summary}</p><h3>Recommended repair</h3><p>{item.recommended_repair}</p>
          {item.unavailable_data_notes?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable_data_notes} /></> : null}
        </article>)}</div>
        <p className="warning-box">{scanResult.retention_note || "Temporary workspace should be deleted after scan completion."}</p>
      </> : null}
    </section>

    <section id="repair" className="section panel">
      <div className="section-head"><div><p className="eyebrow">Repair intelligence</p><h2>Evidence-backed code-fix suggestions</h2></div><span className="status gray">Suggest only</span></div>
      <div className="form-grid repair-grid">
        <label>Issue or failing symptom<textarea value={repairIssue} onChange={(event) => setRepairIssue(event.target.value)} /></label>
        <label>Evidence, one item per line<textarea value={repairEvidence} onChange={(event) => setRepairEvidence(event.target.value)} /></label>
        <label>Affected files, one per line<textarea value={affectedFiles} onChange={(event) => setAffectedFiles(event.target.value)} /></label>
      </div>
      <button type="button" className="primary-button" disabled={!backendConfigured || loading} onClick={runRepairSuggestion}>Generate repair suggestion</button>
      {repairError ? <p className="error-box">{repairError}</p> : null}
      {repairResult ? <div className="repair-result">
        <p className="summary-box"><b>{repairResult.strategy}</b> · risk {repairResult.risk_level} · confidence {repairResult.confidence}</p>
        <div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Root cause</p><p>{repairResult.root_cause_hypothesis}</p><p className="eyebrow">Suggested fix</p><p>{repairResult.suggested_fix_summary}</p></div><div className="mini-panel"><p className="eyebrow">Patch steps</p><ListBlock items={repairResult.patch_steps} /></div></div>
        <HelpDetails title="Patch prompt"><textarea readOnly value={repairResult.patch_prompt || ""} /></HelpDetails>
        <HelpDetails title="Quality checklist"><ListBlock items={repairResult.quality_checklist} /></HelpDetails>
      </div> : null}
    </section>

    <section id="retainer" className="section panel">
      <div className="section-head"><div><p className="eyebrow">Retainer operations</p><h2>Weekly status, backlog, release, and approvals</h2></div><span className="status gray">Ongoing evidence</span></div>
      <div className="command-card"><textarea value={retainerNotes} onChange={(event) => setRetainerNotes(event.target.value)} aria-label="Retainer operating evidence" /></div>
      <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runRetainerWorkflow}>Run Retainer Ops</button>
      {opsError ? <p className="error-box">{opsError}</p> : null}
      {retainerResult ? <><ResultSections sections={retainerResult.sections} /><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Weekly status</p><ListBlock items={retainerResult.weekly_status_report} /></div><div className="mini-panel"><p className="eyebrow">Release checklist</p><ListBlock items={retainerResult.release_checklist} /></div></div></> : null}
    </section>

    <section id="approvals" className="section panel">
      <div className="section-head"><div><p className="eyebrow">Approval queue</p><h2>Human decisions before guarded actions</h2></div><span className="status blue">{approvals.length} items</span></div>
      <button type="button" className="small-button" onClick={loadApprovals}>Load approvals</button>
      {approvalError ? <p className="error-box">{approvalError}</p> : null}
      <div className="results-grid">{approvals.map((item) => <article className="result-card" key={item.approval_id}>
        <div className="result-head"><b>{item.requested_action || "approval"}</b><span className={statusClass(item.status)}>{item.status}</span></div>
        <p><b>ID:</b> {item.approval_id}</p><p><b>Risk:</b> {item.risk_level || "unknown"}</p>
        <h3>Evidence</h3><ListBlock items={item.evidence} />
        <div className="report-actions">
          <button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "approve")}>Approve</button>
          <button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "reject")}>Reject</button>
          <button type="button" onClick={() => item.approval_id && transitionApproval(item.approval_id, "needs-more-evidence")}>Needs more evidence</button>
        </div>
      </article>)}</div>
    </section>

    <section id="reports-ui" className="section panel">
      <div className="section-head"><div><p className="eyebrow">Reports</p><h2>{assessmentType === "mid" ? "Mid report pipeline is guarded" : "Express report package"}</h2></div><span className={statusClass(reportPackage?.status)}>{reportPackage?.status || "not created"}</span></div>
      {assessmentType === "mid" ? <p className="warning-box">The generic report builder is disabled for Mid. Mid reports must retain the same midrun ID, snapshot, evidence ledger, and human-review chain.</p> : <>
        <label className="wide-label">Next steps and report notes<textarea value={reportNotes} onChange={(event) => setReportNotes(event.target.value)} /></label>
        <div className="report-actions">
          <button type="button" className="primary-button" disabled={!backendConfigured || loading} onClick={createReportPackage}>Create report package</button>
          <button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("markdown")}>Export Markdown</button>
          <button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("html")}>Export HTML</button>
          <button type="button" disabled={!reportPackage?.run_id} onClick={() => exportReport("json")}>Export JSON</button>
        </div>
      </>}
      {reportError ? <p className="error-box">{reportError}</p> : null}
      {reportPackage ? <HelpDetails title="Report package"><JsonBlock data={reportPackage} /></HelpDetails> : null}
      {reportExport ? <pre className="json-block">{reportExport}</pre> : null}
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Safety boundary</p><h2>Authorized defensive use only</h2></div><span className="status blue">Enforced</span></div>
      <div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Rules</p><ListBlock items={safetyRules} /></div><div className="mini-panel"><p className="eyebrow">Assessment areas</p><ListBlock items={assessmentAreas} /></div></div>
    </section>
  </main>;
}
