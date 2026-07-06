"use client";

import {useEffect, useState} from "react";

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
  "Code Audit",
  "Dependency / Library Ecosystem",
  "Secrets Exposure Review",
  "Static Analysis",
  "CI/CD Analysis",
  "Architecture & Technical Debt",
  "Velocity / Complexity",
  "Bug-Risk Findings",
  "Repair Recommendations",
  "Verification Checklist",
  "Markdown / HTML / PDF Reports",
];

const targetCards = [
  ["Express Technical Health Assessment", "90–95%", "Highest automation target after scanner/report upgrades"],
  ["Mid Technical Health Assessment", "75–85%", "Requires QA, parity, stakeholder intake, and roadmap evidence"],
  ["Ongoing Product Engineering Retainer", "55–70%", "Requires backlog, sprint, release, and status-report workflows"],
  ["Full client-ready replacement", "75–85%", "Requires human validation before client delivery"],
];

type Health = {
  status?: string;
  system?: string;
  mode?: string;
};

type AssessmentResult = {
  status?: string;
  repository?: string;
  generated_at?: string;
  executive_summary?: string;
  maturity_signal?: {level?: string; score?: number; summary?: string};
  maturity_semaphore?: Record<string, string>;
  sections?: Array<{id: string; label: string; score: number; status: string; summary: string; evidence: string[]; unavailable?: string[]}>;
  findings?: string[];
  repairs?: string[];
  reports?: {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string};
  safety_boundary?: string;
  human_review_required?: boolean;
};

function statusClass(status?: string) {
  if (status === "green") return "status green";
  if (status === "yellow") return "status yellow";
  if (status === "red") return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No evidence returned yet.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

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

  const backendConfigured = Boolean(API_URL);
  const backendOnline = health?.status === "ok";

  async function checkBackend() {
    if (!backendConfigured) {
      setHealthError("No NEXT_PUBLIC_NICO_API_URL is configured for this deployment.");
      return;
    }
    setHealthError("");
    try {
      const response = await fetch(`${API_URL}/health`, {cache: "no-store"});
      const data = await response.json();
      if (!response.ok) throw new Error(`Health check failed with ${response.status}`);
      setHealth(data);
    } catch (error) {
      setHealth(null);
      setHealthError(error instanceof Error ? error.message : "Backend health check failed");
    }
  }

  useEffect(() => {
    checkBackend();
  }, []);

  async function runHostedAssessment() {
    if (!backendConfigured) {
      setAssessmentError("Backend URL is not configured in Vercel.");
      return;
    }
    setAssessmentError("");
    setCopied("");
    setLoading(true);
    try {
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
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.error || data?.error || `Assessment failed with ${response.status}`);
      setAssessment(data);
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Assessment failed");
    } finally {
      setLoading(false);
    }
  }

  async function copyReport(kind: "markdown" | "html") {
    const text = assessment?.reports?.[kind];
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setCopied(`${kind.toUpperCase()} report copied`);
  }

  function downloadPdf() {
    const encoded = assessment?.reports?.pdf_base64;
    if (!encoded) return;
    const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], {type: "application/pdf"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = assessment?.reports?.pdf_filename || "nico-assessment.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Hosted Command Center</p>
        <h1>Higher-end realistic assessment targets</h1>
        <p className="lead">
          NICO now pushes Express toward the 90–95% realistic target with deeper hosted repository inspection, OSV dependency checks where versions are available, static risk patterns, secret-pattern review, workflow history, and PDF export.
        </p>
        <div className="hero-actions">
          <a href="#hosted" className="primary-link">Run hosted assessment</a>
          <a href="#targets" className="secondary-link">Coverage targets</a>
        </div>
      </section>

      <section id="targets" className="section panel status-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Coverage Targets</p>
            <h2>Realistic upper-end goals</h2>
          </div>
          <span className="status blue">Human review required</span>
        </div>
        <div className="grid four target-grid">
          {targetCards.map(([title, target, note]) => (
            <article key={title}><b>{title}</b><span className="target-number">{target}</span><small>{note}</small></article>
          ))}
        </div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">System Status</p>
            <h2>Frontend / Railway backend</h2>
          </div>
          <span className={backendOnline ? "status green" : backendConfigured ? "status yellow" : "status red"}>
            {backendOnline ? "Backend online" : backendConfigured ? "Backend configured" : "Backend missing"}
          </span>
        </div>
        <div className="grid three">
          <article><b>Frontend</b><span>https://app.nicoaudit.com</span></article>
          <article><b>Backend URL</b><span>{API_URL || "Not configured"}</span></article>
          <article><b>Health</b><span>{health?.status || healthError || "Checking"}</span></article>
        </div>
        <button type="button" className="small-button" onClick={checkBackend}>Check backend</button>
        {healthError ? <p className="error-box">{healthError}</p> : null}
      </section>

      <section id="hosted" className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Express Assessment</p>
            <h2>Assess an authorized GitHub repository</h2>
          </div>
          <span className="status gray">Read-only</span>
        </div>
        <p className="warning-box">
          Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not exploit, brute force, bypass authentication, steal credentials, or make destructive changes.
        </p>
        <div className="form-grid">
          <label>
            Repository owner/name or GitHub URL
            <input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" />
          </label>
          <label>
            Client name, optional
            <input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" />
          </label>
          <label>
            Project name, optional
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" />
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
          I confirm I own this repository or have explicit permission to assess it.
        </label>
        <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || loading} onClick={runHostedAssessment}>
          {loading ? "Running assessment..." : "Run authorized hosted assessment"}
        </button>
        {assessmentError ? <p className="error-box">{assessmentError}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Assessment Result</p>
            <h2>{assessment?.maturity_signal?.level ? `${assessment.maturity_signal.level} maturity signal` : "Awaiting assessment"}</h2>
          </div>
          <span className={assessment?.maturity_signal?.level ? "status blue" : "status gray"}>{assessment?.status || "No report"}</span>
        </div>
        {assessment?.human_review_required ? <p className="warning-box">Human review is required before client-facing delivery. NICO provides evidence and draft conclusions; a consultant must validate context, recommendations, Q&A, and resourcing.</p> : null}
        {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
        <div className="results-grid">
          {assessment?.sections?.map((item) => (
            <article className="result-card" key={item.id}>
              <div className="result-head">
                <b>{item.label}</b>
                <span className={statusClass(item.status)}>{item.status} · {item.score}/100</span>
              </div>
              <p>{item.summary}</p>
              <h3>Evidence</h3>
              <ListBlock items={item.evidence} />
              {item.unavailable?.length ? <><h3>Unavailable data</h3><ListBlock items={item.unavailable} /></> : null}
            </article>
          ))}
        </div>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Findings</p><ListBlock items={assessment?.findings} /></div>
          <div className="mini-panel"><p className="eyebrow">Repairs</p><ListBlock items={assessment?.repairs} /></div>
        </div>
        <div className="report-actions">
          <button type="button" disabled={!assessment?.reports?.markdown} onClick={() => copyReport("markdown")}>Copy Markdown</button>
          <button type="button" disabled={!assessment?.reports?.html} onClick={() => copyReport("html")}>Copy HTML</button>
          <button type="button" disabled={!assessment?.reports?.pdf_base64} onClick={downloadPdf}>Download PDF</button>
          {copied ? <span className="muted">{copied}</span> : null}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Mid + Retainer Next</p>
            <h2>Next modules to reach the remaining targets</h2>
          </div>
          <span className="status gray">Planned</span>
        </div>
        <div className="scope-grid">
          {assessmentAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}
        </div>
        <p className="muted">Mid and Retainer coverage require QA intake, platform parity, stakeholder notes, roadmap generation, weekly/monthly reports, backlog health, and approval-gated task creation. NICO now shows these targets while Express is upgraded first.</p>
      </section>

      <section id="commands" className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">No-server fallback</p>
            <h2>Run NICO from your local CLI</h2>
          </div>
          <span className="status blue">CLI ready</span>
        </div>
        <p className="muted">Use these commands on your computer or Codespace when you want local folder/archive/passive URL assessment.</p>
        <div className="command-grid">
          <div className="command-card"><b>First test with NICO test lab</b><textarea readOnly defaultValue={quickStartCommands} /></div>
          <div className="command-card"><b>Assess authorized systems locally</b><textarea readOnly defaultValue={assessmentCommands} /></div>
        </div>
      </section>

      <section id="safety" className="section two-col">
        <div className="panel">
          <p className="eyebrow">Safety Boundary</p>
          <h2>Allowed use</h2>
          <ul className="tight-list">{safetyRules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </div>
        <div className="panel">
          <p className="eyebrow">Assessment Scope</p>
          <h2>Evidence-bound checks</h2>
          <ul className="tight-list">{assessmentAreas.map((area) => <li key={area}>{area}</li>)}</ul>
        </div>
      </section>
    </main>
  );
}
