"use client";

import {useEffect, useMemo, useState} from "react";

const DEFAULT_API_URL = process.env.NEXT_PUBLIC_NICO_API_URL || "http://localhost:8000";

type Health = {
  status?: string;
  system?: string;
  mode?: string;
  cors_origins?: string[];
};

type AssessmentSection = {
  id: string;
  label: string;
  score: number;
  status: string;
  summary: string;
  evidence: string[];
  unavailable: string[];
};

type AssessmentResult = {
  status?: string;
  repository?: string;
  generated_at?: string;
  executive_summary?: string;
  maturity_signal?: {level?: string; score?: number; summary?: string};
  maturity_semaphore?: Record<string, string>;
  sections?: AssessmentSection[];
  findings?: string[];
  repairs?: string[];
  quick_wins?: string[];
  medium_term_plan?: string[];
  resourcing_recommendation?: string[];
  risk_register?: string[];
  verification_checklist?: string[];
  reports?: {markdown?: string; html?: string};
  safety_boundary?: string;
};

function statusClass(status?: string) {
  if (status === "green") return "status green";
  if (status === "yellow") return "status yellow";
  if (status === "red") return "status red";
  return "status gray";
}

function ListBlock({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No evidence available yet.</p>;
  return (
    <ul className="tight-list">
      {items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
    </ul>
  );
}

export default function Page() {
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [health, setHealth] = useState<Health | null>(null);
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [clientName, setClientName] = useState("Bernardo Buendia");
  const [projectName, setProjectName] = useState("NICO Technical Assessment");
  const [timeframeDays, setTimeframeDays] = useState(180);
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  const [assessmentError, setAssessmentError] = useState("");
  const [copied, setCopied] = useState("");

  const frontendUrl = "https://app.nicoaudit.com";
  const backendReady = health?.status === "ok";

  const commandAreas = useMemo(() => [
    "Code Audit",
    "Dependency / Library Ecosystem",
    "CI/CD Analysis",
    "Architecture & Technical Debt",
    "Maturity Semaphore",
    "Velocity / Complexity",
    "Action Plan",
    "Resourcing Plan",
  ], []);

  async function refreshHealth() {
    setConnectionError("");
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/health`, {cache: "no-store"});
      if (!response.ok) throw new Error(`Health check returned ${response.status}`);
      setHealth(await response.json());
      try {
        const policyResponse = await fetch(`${apiUrl.replace(/\/$/, "")}/policy`, {cache: "no-store"});
        if (policyResponse.ok) setPolicy(await policyResponse.json());
      } catch {
        setPolicy(null);
      }
    } catch (error) {
      setHealth(null);
      setPolicy(null);
      setConnectionError(error instanceof Error ? error.message : "Backend connection failed");
    }
  }

  useEffect(() => {
    refreshHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runAssessment() {
    setAssessmentError("");
    setCopied("");
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/assessment/github`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          repository,
          authorized,
          client_name: clientName,
          project_name: projectName,
          assessment_mode: "express",
          timeframe_days: timeframeDays,
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
    const report = assessment?.reports?.[kind];
    if (!report) return;
    await navigator.clipboard?.writeText(report);
    setCopied(`${kind.toUpperCase()} report copied`);
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Hosted Command Center</p>
        <h1>Defensive Technical Assessment System</h1>
        <p className="lead">
          Hosted control surface for authorized repository assessments, evidence-bound reporting, repair planning, and verification.
        </p>
        <div className="hero-actions">
          <a href="#assessment" className="primary-link">Run assessment</a>
          <a href="#reports" className="secondary-link">View reports</a>
        </div>
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">System Status</p>
            <h2>Frontend / Backend connection</h2>
          </div>
          <span className={backendReady ? "status green" : "status red"}>{backendReady ? "API online" : "API not connected"}</span>
        </div>
        <div className="grid four">
          <article><b>Frontend</b><span>{frontendUrl}</span></article>
          <article><b>Backend</b><span>{apiUrl}</span></article>
          <article><b>Health</b><span>{health?.status || connectionError || "Not checked"}</span></article>
          <article><b>Autonomy</b><span>{String(policy?.autonomy_level ?? "Policy unavailable")}</span></article>
        </div>
        <div className="form-row single">
          <label>
            Backend API URL
            <input value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} placeholder="https://your-nico-api-host" />
          </label>
          <button type="button" onClick={refreshHealth}>Check backend</button>
        </div>
        {connectionError ? <p className="error">{connectionError}</p> : null}
      </section>

      <section id="assessment" className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Authorized Assessment Setup</p>
            <h2>Express Technical Health Assessment</h2>
          </div>
          <span className="status gray">Read-only</span>
        </div>
        <div className="form-grid">
          <label>
            Repository owner/name or URL
            <input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repo" />
          </label>
          <label>
            Client name
            <input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client" />
          </label>
          <label>
            Project name
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project" />
          </label>
          <label>
            Timeframe days
            <input type="number" min={30} max={365} value={timeframeDays} onChange={(event) => setTimeframeDays(Number(event.target.value))} />
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
          I confirm I own this repository or am explicitly authorized to assess it. NICO will perform defensive read-only assessment only.
        </label>
        <button type="button" className="primary-button" disabled={loading || !authorized} onClick={runAssessment}>
          {loading ? "Running assessment..." : "Run authorized assessment"}
        </button>
        {assessmentError ? <p className="error">{assessmentError}</p> : null}
      </section>

      <section className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Technical Health Assessment Dashboard</p>
            <h2>Scope areas</h2>
          </div>
          {assessment?.maturity_signal?.level ? <span className="status blue">{assessment.maturity_signal.level}</span> : <span className="status gray">Awaiting run</span>}
        </div>
        <div className="scope-grid">
          {commandAreas.map((area) => <div className="scope-card" key={area}>{area}</div>)}
        </div>
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
      </section>

      <section className="section two-col">
        <div className="panel">
          <p className="eyebrow">Findings</p>
          <h2>Evidence-bound findings</h2>
          <ListBlock items={assessment?.findings} />
        </div>
        <div className="panel">
          <p className="eyebrow">Repairs</p>
          <h2>Human-approved repair candidates</h2>
          <ListBlock items={assessment?.repairs} />
        </div>
      </section>

      <section className="section two-col">
        <div className="panel">
          <p className="eyebrow">Policy</p>
          <h2>Safety boundary</h2>
          <p className="muted">{assessment?.safety_boundary || "Defensive-only. Authorized repositories only. Production-impacting actions require human approval."}</p>
          <ListBlock items={assessment?.risk_register} />
        </div>
        <div className="panel">
          <p className="eyebrow">Audit Log</p>
          <h2>Verification checklist</h2>
          <ListBlock items={assessment?.verification_checklist} />
        </div>
      </section>

      <section id="reports" className="section panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">Reports</p>
            <h2>Markdown and HTML export</h2>
          </div>
          {assessment?.generated_at ? <span className="status green">Generated</span> : <span className="status gray">No report</span>}
        </div>
        <div className="report-actions">
          <button type="button" disabled={!assessment?.reports?.markdown} onClick={() => copyReport("markdown")}>Copy Markdown</button>
          <button type="button" disabled={!assessment?.reports?.html} onClick={() => copyReport("html")}>Copy HTML</button>
          {copied ? <span className="muted">{copied}</span> : null}
        </div>
        <textarea readOnly value={assessment?.reports?.markdown || "Run an authorized assessment to generate the Express Technical Health Assessment report."} />
      </section>
    </main>
  );
}
