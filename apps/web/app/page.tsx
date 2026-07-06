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
const assessmentAreas = ["Code Audit", "Dependency / Library Ecosystem", "Secrets Exposure Review", "Static Analysis", "CI/CD Analysis", "Architecture & Technical Debt", "Velocity / Complexity", "QA / Functional Review", "Platform Parity", "Retainer Ops", "Repair Intelligence", "Markdown / HTML / PDF Reports"];
const targetCards = [["Express Technical Health Assessment", "90–95%", "Scanner/report automation with human review"], ["Mid Technical Health Assessment", "75–85%", "QA, parity, stakeholder, and roadmap evidence"], ["Ongoing Product Engineering Retainer", "55–70%", "Backlog, sprint, release, and approval workflows"], ["Full client-ready replacement", "75–85%", "Human validation before delivery"]];

type Health = {status?: string; system?: string; mode?: string};
type Section = {id: string; label: string; score: number; status: string; summary: string; evidence: string[]; findings?: string[]; unavailable?: string[]};
type AssessmentResult = {status?: string; repository?: string; generated_at?: string; executive_summary?: string; maturity_signal?: {level?: string; score?: number; summary?: string}; sections?: Section[]; findings?: string[]; repairs?: string[]; reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string}; human_review_required?: boolean};
type WorkflowResult = {status?: string; workflow?: string; target_coverage?: string; maturity_signal?: {level?: string; score?: number}; sections?: Section[]; qa_checklist?: string[]; parity_checklist?: string[]; six_month_roadmap?: string[]; weekly_status_report?: string[]; release_checklist?: string[]; human_approval_queue?: string[]};
type RepairResult = {status?: string; suggestion_id?: string; issue?: string; risk_level?: string; confidence?: string; strategy?: string; root_cause_hypothesis?: string; suggested_fix_summary?: string; patch_steps?: string[]; affected_files_or_systems?: string[]; evidence?: string[]; patch_prompt?: string; test_plan?: string; rollback_plan?: string; quality_checklist?: string[]; next_step?: string; human_review_required?: boolean};

function statusClass(status?: string) { if (status === "green") return "status green"; if (status === "yellow") return "status yellow"; if (status === "red") return "status red"; return "status gray"; }
function ListBlock({items}: {items?: string[]}) { if (!items?.length) return <p className="muted">No evidence returned yet.</p>; return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>; }
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
    setAssessmentError(""); setCopied(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/assessment/github`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({repository, authorized, client_name: clientName, project_name: projectName, assessment_mode: "express", timeframe_days: 180})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Assessment failed with ${response.status}`); setAssessment(data); }
    catch (error) { setAssessmentError(error instanceof Error ? error.message : "Assessment failed"); }
    finally { setLoading(false); }
  }

  async function runMidWorkflow() {
    if (!backendConfigured) { setOpsError("Backend URL is not configured in Vercel."); return; }
    setOpsError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/assessment/mid`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({authorized, client_name: clientName, project_name: projectName, qa_evidence: extractBlock(midNotes, "QA evidence"), parity_notes: extractBlock(midNotes, "Parity notes"), stakeholder_notes: extractBlock(midNotes, "Stakeholder notes"), roadmap_notes: extractBlock(midNotes, "Roadmap notes"), known_risks: extractBlock(midNotes, "Known risks")})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Mid workflow failed with ${response.status}`); setMidResult(data); }
    catch (error) { setOpsError(error instanceof Error ? error.message : "Mid workflow failed"); }
    finally { setLoading(false); }
  }

  async function runRetainerWorkflow() {
    if (!backendConfigured) { setOpsError("Backend URL is not configured in Vercel."); return; }
    setOpsError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/retainer/ops`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({authorized, client_name: clientName, project_name: projectName, commit_summary: extractBlock(retainerNotes, "Commit summary"), pr_summary: extractBlock(retainerNotes, "PR summary"), issue_summary: extractBlock(retainerNotes, "Issue summary"), blockers: extractBlock(retainerNotes, "Blockers"), release_notes: extractBlock(retainerNotes, "Release notes"), roadmap_notes: extractBlock(retainerNotes, "Roadmap notes")})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Retainer workflow failed with ${response.status}`); setRetainerResult(data); }
    catch (error) { setOpsError(error instanceof Error ? error.message : "Retainer workflow failed"); }
    finally { setLoading(false); }
  }

  async function runRepairSuggestion() {
    if (!backendConfigured) { setRepairError("Backend URL is not configured in Vercel."); return; }
    setRepairError(""); setLoading(true);
    try { const response = await fetch(`${API_URL}/repair/suggest`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({issue: repairIssue, evidence: splitLines(repairEvidence), affected_files: splitLines(affectedFiles), customer_id: "default_customer", project_id: "default_project"})}); const data = await response.json(); if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Repair suggestion failed with ${response.status}`); setRepairResult(data); }
    catch (error) { setRepairError(error instanceof Error ? error.message : "Repair suggestion failed"); }
    finally { setLoading(false); }
  }

  async function copyReport(kind: "markdown" | "html") { const text = assessment?.reports?.[kind]; if (!text) return; await navigator.clipboard?.writeText(text); setCopied(`${kind.toUpperCase()} report copied`); }
  function downloadPdf() { const encoded = assessment?.reports?.pdf_base64; if (!encoded) return; const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0)); const blob = new Blob([bytes], {type: "application/pdf"}); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = assessment?.reports?.pdf_filename || "nico-assessment.pdf"; anchor.click(); URL.revokeObjectURL(url); }

  return (
    <main className="shell">
      <section className="hero"><p className="eyebrow">NICO Hosted Command Center</p><h1>Highest realistic assessment targets</h1><p className="lead">NICO targets Express, Mid, Retainer, and repair-intelligence workflows with evidence-bound results, approval gates, and detailed section help.</p><div className="hero-actions"><a href="#hosted" className="primary-link">Run Express</a><a href="#repair" className="secondary-link">Repair Intelligence</a><a href="#guide" className="secondary-link">How to use</a></div></section>

      <section id="guide" className="section panel"><div className="section-head"><div><p className="eyebrow">Clicky Guide</p><h2>How to use each section</h2></div><span className="status blue">Dropdown help</span></div><div className="help-grid"><HelpDetails title="Dashboard / System Status"><ol><li>Confirm backend health says ok.</li><li>Check target coverage and storage status.</li><li>If storage says unavailable, do not treat latest results as permanent.</li><li>Use this before client demos or customer work.</li></ol></HelpDetails><HelpDetails title="Express Assessment"><ol><li>Get written authorization.</li><li>Enter owner/repo.</li><li>Check authorization.</li><li>Run Express.</li><li>Review maturity, sections, unavailable notes, repairs, and exports.</li><li>Human-review before sending to a client.</li></ol></HelpDetails><HelpDetails title="Repair Intelligence"><ol><li>Paste the exact issue or failing CI/test symptom.</li><li>Add evidence lines.</li><li>Add affected files if known.</li><li>Generate the repair suggestion.</li><li>Review root-cause hypothesis, patch steps, test plan, rollback plan, confidence, and risk.</li><li>Create approval only if a human agrees.</li></ol></HelpDetails><HelpDetails title="Mid Assessment"><ol><li>Paste QA evidence, parity notes, stakeholder notes, roadmap notes, and known risks under the headings.</li><li>Run Mid workflow.</li><li>Missing evidence stays unavailable.</li><li>Use output as draft client material only after review.</li></ol></HelpDetails><HelpDetails title="Retainer Ops"><ol><li>Paste commit, PR, issue, blocker, release, and roadmap evidence.</li><li>Run Retainer Ops.</li><li>Review weekly status, release checklist, and approval needs.</li><li>Use monthly/weekly reports after human review.</li></ol></HelpDetails><HelpDetails title="Approval and code-change policy"><ol><li>NICO suggests fixes and draft PR plans.</li><li>NICO should not push to main, auto-merge, deploy, or edit production.</li><li>Use suggest → approval queue → draft branch/PR → CI → human review → customer merge.</li></ol></HelpDetails></div></section>

      <section id="targets" className="section panel status-panel"><div className="section-head"><div><p className="eyebrow">Coverage Targets</p><h2>Realistic upper-end goals</h2></div><span className="status blue">Human review required</span></div><div className="grid four target-grid">{targetCards.map(([title, target, note]) => <article key={title}><b>{title}</b><span className="target-number">{target}</span><small>{note}</small></article>)}</div><HelpDetails title="How to read these targets"><p>These are realistic service coverage targets, not claims of full automation. NICO can collect evidence, draft reports, suggest repairs, and prepare approval-gated workflows. Humans still validate conclusions and code changes.</p></HelpDetails></section>

      <section className="section panel status-panel"><div className="section-head"><div><p className="eyebrow">System Status</p><h2>Frontend / Railway backend</h2></div><span className={backendOnline ? "status green" : backendConfigured ? "status yellow" : "status red"}>{backendOnline ? "Backend online" : backendConfigured ? "Backend configured" : "Backend missing"}</span></div><div className="grid three"><article><b>Frontend</b><span>https://app.nicoaudit.com</span></article><article><b>Backend URL</b><span>{API_URL || "Not configured"}</span></article><article><b>Health</b><span>{health?.status || healthError || "Checking"}</span></article></div><button type="button" className="small-button" onClick={checkBackend}>Check backend</button>{healthError ? <p className="error-box">{healthError}</p> : null}</section>

      <section id="hosted" className="section panel"><div className="section-head"><div><p className="eyebrow">Express Assessment</p><h2>Assess an authorized GitHub repository</h2></div><span className="status gray">90–95%</span></div><HelpDetails title="Express instructions"><ul><li>Use for fast repo health checks.</li><li>Best input is exact owner/repo plus client/project names.</li><li>Review every evidence item and unavailable-data note.</li><li>Use repair suggestions for findings that need code changes.</li></ul></HelpDetails><p className="warning-box">Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.</p><div className="form-grid"><label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label><label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" /></label><label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" /></label></div><label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this target or have explicit permission to assess it.</label><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runHostedAssessment}>{loading ? "Running..." : "Run Express assessment"}</button>{assessmentError ? <p className="error-box">{assessmentError}</p> : null}</section>

      <section className="section panel"><div className="section-head"><div><p className="eyebrow">Express Result</p><h2>{assessment?.maturity_signal?.level ? `${assessment.maturity_signal.level} maturity signal` : "Awaiting assessment"}</h2></div><span className={assessment?.maturity_signal?.level ? "status blue" : "status gray"}>{assessment?.status || "No report"}</span></div>{assessment?.human_review_required ? <p className="warning-box">Human review is required before client-facing delivery.</p> : null}{assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}<div className="results-grid">{assessment?.sections?.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{item.status} · {item.score}/100</span></div><p>{item.summary}</p><h3>Evidence</h3><ListBlock items={item.evidence} />{item.unavailable?.length ? <><h3>Unavailable data</h3><ListBlock items={item.unavailable} /></> : null}</article>)}</div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Findings</p><ListBlock items={assessment?.findings} /></div><div className="mini-panel"><p className="eyebrow">Repairs</p><ListBlock items={assessment?.repairs} /></div></div><div className="report-actions"><button type="button" disabled={!assessment?.reports?.markdown} onClick={() => copyReport("markdown")}>Copy Markdown</button><button type="button" disabled={!assessment?.reports?.html} onClick={() => copyReport("html")}>Copy HTML</button><button type="button" disabled={!assessment?.reports?.pdf_base64} onClick={downloadPdf}>Download PDF</button>{copied ? <span className="muted">{copied}</span> : null}</div></section>

      <section id="repair" className="section panel"><div className="section-head"><div><p className="eyebrow">Repair Intelligence</p><h2>Best code-fix suggestions with approval gates</h2></div><span className="status gray">Suggest only</span></div><HelpDetails title="How to get the best repair suggestion"><ol><li>Paste the exact failing symptom, CI error, or finding.</li><li>Add evidence as separate lines.</li><li>Add affected files if known.</li><li>Run suggestion.</li><li>Use the patch prompt for a draft repair branch only after human approval.</li></ol></HelpDetails><div className="form-grid repair-grid"><label>Issue / failing symptom<textarea value={repairIssue} onChange={(event) => setRepairIssue(event.target.value)} /></label><label>Evidence, one item per line<textarea value={repairEvidence} onChange={(event) => setRepairEvidence(event.target.value)} /></label><label>Affected files, one per line<textarea value={affectedFiles} onChange={(event) => setAffectedFiles(event.target.value)} /></label></div><button type="button" className="primary-button" disabled={!backendConfigured || loading} onClick={runRepairSuggestion}>{loading ? "Generating..." : "Generate repair suggestion"}</button>{repairError ? <p className="error-box">{repairError}</p> : null}{repairResult ? <div className="repair-result"><p className="summary-box"><b>{repairResult.strategy}</b> · risk {repairResult.risk_level} · confidence {repairResult.confidence}</p><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Root-cause hypothesis</p><p>{repairResult.root_cause_hypothesis}</p><p className="eyebrow">Suggested fix</p><p>{repairResult.suggested_fix_summary}</p></div><div className="mini-panel"><p className="eyebrow">Patch steps</p><ListBlock items={repairResult.patch_steps} /></div></div><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Test plan</p><p>{repairResult.test_plan}</p></div><div className="mini-panel"><p className="eyebrow">Rollback plan</p><p>{repairResult.rollback_plan}</p></div></div><HelpDetails title="Patch prompt for a draft branch / PR"><textarea readOnly value={repairResult.patch_prompt || ""} /></HelpDetails><HelpDetails title="Quality checklist"><ListBlock items={repairResult.quality_checklist} /></HelpDetails></div> : null}</section>

      <section id="mid" className="section panel"><div className="section-head"><div><p className="eyebrow">Mid Assessment</p><h2>QA, parity, stakeholder, and roadmap workflow</h2></div><span className="status gray">75–85%</span></div><HelpDetails title="Mid instructions"><p>Paste real evidence under each heading. Empty sections become unavailable instead of invented. Use this for QA, platform parity, stakeholder discovery, and roadmap draft work.</p></HelpDetails><div className="command-card"><textarea value={midNotes} onChange={(event) => setMidNotes(event.target.value)} aria-label="Mid assessment evidence" /></div><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runMidWorkflow}>Run Mid workflow</button>{midResult ? <><p className="summary-box">Mid workflow target: {midResult.target_coverage}. Maturity: {midResult.maturity_signal?.level} {midResult.maturity_signal?.score}/100.</p><ResultSections result={midResult} /><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">QA checklist</p><ListBlock items={midResult.qa_checklist} /></div><div className="mini-panel"><p className="eyebrow">Parity checklist</p><ListBlock items={midResult.parity_checklist} /></div></div></> : null}</section>

      <section id="retainer" className="section panel"><div className="section-head"><div><p className="eyebrow">Retainer Ops</p><h2>Weekly status, backlog health, release, and approval queue</h2></div><span className="status gray">55–70%</span></div><HelpDetails title="Retainer instructions"><p>Use this for ongoing support. Paste weekly operating evidence and review status, blockers, release readiness, and approval needs before client delivery.</p></HelpDetails><div className="command-card"><textarea value={retainerNotes} onChange={(event) => setRetainerNotes(event.target.value)} aria-label="Retainer operating evidence" /></div><button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runRetainerWorkflow}>Run Retainer Ops</button>{opsError ? <p className="error-box">{opsError}</p> : null}{retainerResult ? <><p className="summary-box">Retainer target: {retainerResult.target_coverage}. Maturity: {retainerResult.maturity_signal?.level} {retainerResult.maturity_signal?.score}/100.</p><ResultSections result={retainerResult} /><div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Weekly status</p><ListBlock items={retainerResult.weekly_status_report} /></div><div className="mini-panel"><p className="eyebrow">Release checklist</p><ListBlock items={retainerResult.release_checklist} /></div></div><div className="mini-panel inset-grid"><p className="eyebrow">Human approval queue</p><ListBlock items={retainerResult.human_approval_queue} /></div></> : null}</section>

      <section className="section panel"><div className="section-head"><div><p className="eyebrow">Assessment Scope</p><h2>Evidence-bound checks</h2></div><span className="status gray">No fake data</span></div><div className="scope-grid">{assessmentAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}</div></section>

      <section id="commands" className="section panel"><div className="section-head"><div><p className="eyebrow">No-server fallback</p><h2>Run NICO from your local CLI</h2></div><span className="status blue">CLI ready</span></div><HelpDetails title="When to use CLI mode"><p>Use local CLI when hosted assessment is unavailable or when you need local folder/archive/passive URL assessment. Keep authorization proof and do not use it on unrelated systems.</p></HelpDetails><div className="command-grid"><div className="command-card"><b>First test with NICO test lab</b><textarea readOnly defaultValue={quickStartCommands} /></div><div className="command-card"><b>Assess authorized systems locally</b><textarea readOnly defaultValue={assessmentCommands} /></div></div></section>

      <section id="safety" className="section two-col"><div className="panel"><p className="eyebrow">Safety Boundary</p><h2>Allowed use</h2><ul className="tight-list">{safetyRules.map((rule) => <li key={rule}>{rule}</li>)}</ul></div><div className="panel"><p className="eyebrow">Human Review</p><h2>Required for client delivery</h2><ul className="tight-list"><li>Validate facts and evidence before delivery.</li><li>Confirm stakeholder context.</li><li>Approve production-impacting changes.</li><li>Review roadmap and resourcing recommendations.</li></ul></div></section>
    </main>
  );
}
