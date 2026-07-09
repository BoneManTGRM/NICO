"use client";

import {useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

const REQUIRED_SECTIONS = [
  ["dependency_health", "Dependency scanners"],
  ["secrets_review", "Full-history secrets"],
  ["static_analysis", "Static analysis"],
  ["velocity_complexity", "Complexity / velocity"],
] as const;

const REQUIRED_TOOLS = [
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

type Section = {
  id?: string;
  label?: string;
  score?: number;
  status?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
};

type RefreshResult = {
  status?: string;
  repository?: string;
  generated_at?: string;
  maturity_signal?: {level?: string; score?: number; summary?: string};
  sections?: Section[];
  reports?: {pdf_base64?: string; pdf_filename?: string; markdown?: string; html?: string};
  scanner_artifact_summary?: {completed_tools?: string[]; unavailable_tools?: string[]};
  report_quality_guards?: Record<string, unknown>;
  evidence_ledger?: {coverage_by_section?: Record<string, {complete?: boolean; verified_tools?: string[]; missing_required_tools?: string[]}>};
  human_review_required?: boolean;
};

function statusClass(status?: string) {
  if (status === "green" || status === "passed" || status === "complete" || status === "available" || status === "attached") return "status green";
  if (status === "yellow" || status === "pending" || status === "running" || status === "queued" || status === "partial") return "status yellow";
  if (status === "red" || status === "failed" || status === "error" || status === "timeout" || status === "blocked") return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No items returned.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

function findSection(result: RefreshResult | null, id: string) {
  return result?.sections?.find((section) => section.id === id);
}

function sectionReady(result: RefreshResult | null, id: string) {
  const section = findSection(result, id);
  const coverage = result?.evidence_ledger?.coverage_by_section?.[id];
  if (coverage?.complete) return true;
  return section?.status === "green" && !(section.unavailable?.length);
}

function downloadPdf(result: RefreshResult | null) {
  const encoded = result?.reports?.pdf_base64;
  if (!encoded) return;
  const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
  const blob = new Blob([bytes], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = result?.reports?.pdf_filename || "nico-full-evidence-report.pdf";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function RefreshFullEvidencePage() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [authorizedBy, setAuthorizedBy] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RefreshResult | null>(null);

  const completedTools = result?.scanner_artifact_summary?.completed_tools || [];
  const unavailableTools = result?.scanner_artifact_summary?.unavailable_tools || [];
  const missingTools = useMemo(() => REQUIRED_TOOLS.filter((tool) => !completedTools.includes(tool)), [completedTools]);

  async function refreshFullEvidence() {
    if (!API_URL) { setError("Backend URL is not configured in Vercel."); return; }
    setError("");
    setLoading(true);
    try {
      const refreshActor = authorizedBy ? `${authorizedBy} via frontend-refresh-full-evidence` : "frontend-refresh-full-evidence";
      const response = await fetch(`${API_URL}/assessment/github`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          repository,
          authorized,
          authorized_by: refreshActor,
          client_name: clientName,
          project_name: projectName,
          assessment_mode: "express",
          timeframe_days: 180,
          run_scanner_worker: true,
          scanner_worker_autorun: true,
          full_history_secret_scan: true,
          refresh_full_evidence: true,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Refresh failed with ${response.status}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh Full Evidence failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">One-click evidence refresh</p>
        <h1>Refresh Full Evidence</h1>
        <p className="lead">Re-run the authorized Express assessment path with hosted scanner evidence, full-history secret scanning, static analysis, dependency proof, complexity evidence, report rebuilding, and final trust gates.</p>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Authorized repository</p><h2>Run the full evidence path</h2></div><span className={API_URL ? "status green" : "status red"}>{API_URL ? "Backend configured" : "Backend missing"}</span></div>
        <p className="warning-box">Only use this on repositories you own or are explicitly authorized to assess. Missing scanner output remains missing evidence; this button does not fake clean results.</p>
        <div className="form-grid">
          <label>Repository owner/name<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" /></label>
          <label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" /></label>
          <label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" /></label>
          <label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} placeholder="Name or role" /></label>
        </div>
        <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this target or have explicit permission to assess it.</label>
        <button type="button" className="primary-button" disabled={!API_URL || !authorized || loading} onClick={refreshFullEvidence}>{loading ? "Refreshing full evidence..." : "Refresh Full Evidence"}</button>
        {error ? <p className="error-box">{error}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Refresh status</p><h2>{result?.maturity_signal?.level ? `${result.maturity_signal.level} · ${result.maturity_signal.score}/100` : "Awaiting refresh"}</h2></div><span className={statusClass(result?.status)}>{result?.status || "not run"}</span></div>
        {result?.human_review_required ? <p className="warning-box">Human review is still required before client-facing delivery.</p> : null}
        <div className="grid four target-grid">
          {REQUIRED_SECTIONS.map(([id, label]) => {
            const section = findSection(result, id);
            const ready = sectionReady(result, id);
            return <article key={id}><b>{label}</b><span className={ready ? "status green" : result ? "status yellow" : "status gray"}>{ready ? "verified" : result ? "needs evidence" : "pending"}</span><small>{section ? `${section.status} · ${section.score}/100` : "No section yet"}</small></article>;
          })}
        </div>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Completed scanner tools</p><ListBlock items={completedTools} /></div>
          <div className="mini-panel"><p className="eyebrow">Still missing / unavailable</p><ListBlock items={unavailableTools.length ? unavailableTools : missingTools} /></div>
        </div>
        <div className="report-actions"><button type="button" disabled={!result?.reports?.pdf_base64} onClick={() => downloadPdf(result)}>Download refreshed PDF</button></div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Evidence details</p><h2>Current report sections</h2></div><span className="status blue">Evidence-bound</span></div>
        <div className="results-grid">
          {result?.sections?.map((section) => <article className="result-card" key={section.id}><div className="result-head"><b>{section.label}</b><span className={statusClass(section.status)}>{section.status} · {section.score}/100</span></div><p>{section.summary}</p><h3>Evidence</h3><ListBlock items={section.evidence} />{section.findings?.length ? <><h3>Findings</h3><ListBlock items={section.findings} /></> : null}{section.unavailable?.length ? <><h3>Unavailable</h3><ListBlock items={section.unavailable} /></> : null}</article>)}
        </div>
      </section>
    </main>
  );
}
