"use client";

import {useEffect, useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const TERMINAL = new Set(["complete", "failed", "error", "timeout", "blocked"]);
const TOOLS = ["pip-audit", "npm-audit", "osv-scanner", "semgrep", "bandit", "eslint", "pytest", "npm-test", "npm-build"];

type ScannerItem = {scanner?: string; status?: string; evidence_summary?: string; risk_severity?: string; unavailable_data_notes?: string[]};
type ScanResult = {scan_id?: string; status?: string; tools_run?: string[]; unavailable_tools?: string[]; failed_tools?: string[]; timed_out_tools?: string[]; scanner_results?: ScannerItem[]; unavailable_data_notes?: string[]; retention_note?: string};
type Section = {id?: string; label?: string; status?: string; score?: number; confidence?: string; summary?: string; evidence?: string[]; unavailable?: string[]};
type Assessment = {status?: string; maturity_signal?: {level?: string; score?: number}; sections?: Section[]; findings?: string[]; unavailable_data_notes?: string[]; worker_evidence_attachment?: {status?: string; reason?: string; mode?: string; scan_id?: string}};

function statusClass(status?: string) {
  if (["complete", "green", "passed"].includes(status || "")) return "status green";
  if (["running", "queued", "yellow"].includes(status || "")) return "status yellow";
  if (["failed", "error", "timeout", "red"].includes(status || "")) return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No items returned.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>;
}

export default function ScannerWorkflowPage() {
  const [repository, setRepository] = useState("BoneManTGRM/autonomous-betting-agent");
  const [clientName, setClientName] = useState("ABA Signal Pro");
  const [projectName, setProjectName] = useState("ABA Signal Pro");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [authorized, setAuthorized] = useState(false);
  const [authorizedBy, setAuthorizedBy] = useState("");
  const [authorizationScope, setAuthorizationScope] = useState("repository assessment only");
  const [selectedTools, setSelectedTools] = useState(["pip-audit", "npm-audit", "osv-scanner", "bandit"]);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const scanComplete = scan?.status === "complete";
  const scannerAttached = assessment?.sections?.some((item) => item.id === "scanner_worker_evidence") || assessment?.worker_evidence_attachment?.status === "complete";
  const readiness = useMemo(() => {
    if (!authorized) return "Confirm authorization first.";
    if (!authorizedBy.trim()) return "Add who authorized the work.";
    if (!scan) return "Ready to run Scanner Worker.";
    if (!scanComplete) return `Scanner status: ${scan.status || "unknown"}.`;
    if (!assessment) return "Scanner complete. Run Express to attach evidence.";
    return scannerAttached ? "Express attached worker evidence." : "Express completed, but worker evidence was unavailable or not matched.";
  }, [authorized, authorizedBy, scan, scanComplete, assessment, scannerAttached]);

  useEffect(() => {
    if (!API_URL || !scan?.scan_id || TERMINAL.has(scan.status || "")) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/worker/scan/${scan.scan_id}`, {cache: "no-store"});
        const data = await response.json();
        if (response.ok) setScan(data);
      } catch {}
    }, 3500);
    return () => window.clearInterval(timer);
  }, [scan?.scan_id, scan?.status]);

  function toggleTool(tool: string) {
    setSelectedTools((items) => items.includes(tool) ? items.filter((item) => item !== tool) : [...items, tool]);
  }

  async function startScan() {
    if (!API_URL) throw new Error("Backend URL is not configured.");
    const response = await fetch(`${API_URL}/worker/scan`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({repository, authorized, customer_id: customerId, project_id: projectId, authorized_by: authorizedBy, authorization_scope: authorizationScope, tools: selectedTools})});
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Scanner failed with ${response.status}`);
    setScan(data);
    return data as ScanResult;
  }

  async function refreshScan(scanId = scan?.scan_id) {
    if (!API_URL || !scanId) return null;
    const response = await fetch(`${API_URL}/worker/scan/${scanId}`, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(`Scan refresh failed with ${response.status}`);
    setScan(data);
    return data as ScanResult;
  }

  async function runExpress() {
    if (!API_URL) throw new Error("Backend URL is not configured.");
    const response = await fetch(`${API_URL}/assessment/github`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({repository, authorized, client_name: clientName, project_name: projectName, assessment_mode: "express", timeframe_days: 180, customer_id: customerId, project_id: projectId, authorized_by: authorizedBy || "frontend_user"})});
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Express failed with ${response.status}`);
    setAssessment(data);
    return data as Assessment;
  }

  async function runGuidedFlow() {
    setBusy(true); setError(""); setMessage("Starting Scanner Worker..."); setAssessment(null);
    try {
      const first = await startScan();
      let current = first;
      for (let i = 0; i < 45 && current.scan_id && !TERMINAL.has(current.status || ""); i += 1) {
        setMessage(`Scanner ${current.status || "queued"}; waiting for evidence...`);
        await new Promise((resolve) => window.setTimeout(resolve, 2500));
        current = await refreshScan(current.scan_id) || current;
      }
      setMessage(`Scanner status ${current.status || "unknown"}; running Express assessment...`);
      await runExpress();
      setMessage("Workflow complete. Review evidence, unavailable notes, and human-review gates.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow failed");
    } finally {
      setBusy(false);
    }
  }

  async function buttonAction(action: "scan" | "refresh" | "express") {
    setBusy(true); setError("");
    try {
      if (action === "scan") { setMessage("Starting Scanner Worker..."); await startScan(); }
      if (action === "refresh") { setMessage("Refreshing scanner status..."); await refreshScan(); }
      if (action === "express") { setMessage("Running Express assessment..."); await runExpress(); }
    } catch (err) { setError(err instanceof Error ? err.message : "Action failed"); }
    finally { setBusy(false); }
  }

  return <main className="shell">
    <section className="hero"><p className="eyebrow">NICO Scanner Workflow</p><h1>Scanner → Express accuracy flow</h1><p className="lead">Run a controlled worker pass first, then run Express so NICO can attach completed worker evidence without guessing or starting hidden scans.</p><div className="hero-actions"><a href="/" className="secondary-link">Back to dashboard</a><a href="#workflow" className="primary-link">Run guided flow</a></div></section>

    <section id="workflow" className="section panel"><div className="section-head"><div><p className="eyebrow">Guided Accuracy Flow</p><h2>Evidence-first workflow</h2></div><span className={scannerAttached ? "status green" : scanComplete ? "status yellow" : "status gray"}>{scannerAttached ? "evidence attached" : readiness}</span></div><p className="warning-box">Use only on repositories you own or are explicitly authorized to review. Scanner results are evidence, not a guarantee that no bugs exist.</p><div className="grid four target-grid"><article><b>1. Authorization</b><small>{authorized ? "Confirmed" : "Required"}</small></article><article><b>2. Scanner Worker</b><small>{scan?.status || "Not run"}</small></article><article><b>3. Express Assessment</b><small>{assessment?.status || "Not run"}</small></article><article><b>4. Evidence Attachment</b><small>{scannerAttached ? "Attached" : assessment?.worker_evidence_attachment?.status || "Pending"}</small></article></div>{message ? <p className="summary-box">{message}</p> : null}{error ? <p className="error-box">{error}</p> : null}</section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Scope</p><h2>Repository and authorization</h2></div><span className={authorized ? "status green" : "status red"}>{authorized ? "authorized" : "not authorized"}</span></div><div className="form-grid"><label>Repository<input value={repository} onChange={(event) => setRepository(event.target.value)} /></label><label>Client name<input value={clientName} onChange={(event) => setClientName(event.target.value)} /></label><label>Project name<input value={projectName} onChange={(event) => setProjectName(event.target.value)} /></label><label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label><label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} placeholder="Name or role" /></label></div><label className="wide-label">Authorization scope<textarea value={authorizationScope} onChange={(event) => setAuthorizationScope(event.target.value)} /></label><label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm this repository is authorized for defensive assessment.</label></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Tools</p><h2>Worker evidence sources</h2></div><span className="status blue">{selectedTools.length} selected</span></div><div className="checkbox-grid">{TOOLS.map((tool) => <label key={tool}><input type="checkbox" checked={selectedTools.includes(tool)} onChange={() => toggleTool(tool)} />{tool}</label>)}</div><div className="report-actions"><button type="button" className="primary-button" disabled={!API_URL || !authorized || !authorizedBy || busy} onClick={runGuidedFlow}>{busy ? "Running..." : "Run Scanner → Express"}</button><button type="button" disabled={!API_URL || !authorized || !authorizedBy || busy} onClick={() => buttonAction("scan")}>Run Scanner only</button><button type="button" disabled={!scan?.scan_id || busy} onClick={() => buttonAction("refresh")}>Refresh Scanner</button><button type="button" disabled={!API_URL || !authorized || busy} onClick={() => buttonAction("express")}>Run Express only</button></div></section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Scanner Status</p><h2>{scan?.scan_id || "No scanner run yet"}</h2></div><span className={statusClass(scan?.status)}>{scan?.status || "not run"}</span></div>{scan ? <><div className="grid three inset-grid"><article><b>Tools run</b><span>{scan.tools_run?.length || 0}</span></article><article><b>Unavailable</b><span>{scan.unavailable_tools?.length || 0}</span></article><article><b>Failed/timed out</b><span>{(scan.failed_tools?.length || 0) + (scan.timed_out_tools?.length || 0)}</span></article></div><div className="results-grid">{scan.scanner_results?.map((item, index) => <article className="result-card" key={`${item.scanner}-${index}`}><div className="result-head"><b>{item.scanner}</b><span className={statusClass(item.status)}>{item.status}</span></div><p><b>Risk:</b> {item.risk_severity || "unknown"}</p><p>{item.evidence_summary || "No evidence summary returned."}</p>{item.unavailable_data_notes?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable_data_notes} /></> : null}</article>)}</div><ListBlock items={scan.unavailable_data_notes} /></> : <p className="muted">Run Scanner Worker first for stronger evidence.</p>}</section>

    <section className="section panel"><div className="section-head"><div><p className="eyebrow">Express Result</p><h2>{assessment?.maturity_signal?.level || "No Express result yet"}</h2></div><span className={statusClass(assessment?.status)}>{assessment?.status || "not run"}</span></div>{assessment?.worker_evidence_attachment ? <p className="summary-box">Worker evidence attachment: {assessment.worker_evidence_attachment.status}. {assessment.worker_evidence_attachment.reason || assessment.worker_evidence_attachment.mode || ""}</p> : null}<div className="grid three inset-grid"><article><b>Score</b><span>{assessment?.maturity_signal?.score ?? "N/A"}</span></article><article><b>Scanner section</b><span>{scannerAttached ? "present" : "not attached"}</span></article><article><b>Human review</b><span>required</span></article></div><div className="results-grid">{assessment?.sections?.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label || item.id}</b><span className={statusClass(item.status)}>{item.status} · {item.score}/100</span></div><p>{item.summary}</p><p><b>Confidence:</b> {item.confidence || "not returned"}</p><h3>Evidence</h3><ListBlock items={item.evidence} />{item.unavailable?.length ? <><h3>Unavailable</h3><ListBlock items={item.unavailable} /></> : null}</article>)}</div>{assessment?.unavailable_data_notes?.length ? <><h3>Unavailable notes</h3><ListBlock items={assessment.unavailable_data_notes} /></> : null}</section>
  </main>;
}
