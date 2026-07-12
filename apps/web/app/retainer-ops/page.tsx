"use client";

import {FormEvent, useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type SourceState = {
  source_id?: string;
  status?: string;
  checked_at?: string;
  item_count?: number | null;
  note?: string;
  derived_from?: string;
};

type RetainerSection = {
  id?: string;
  label?: string;
  score?: number;
  score_calculated?: boolean;
  status?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
};

type RetainerResult = {
  status?: string;
  repository?: string;
  generated_at?: string;
  source_binding?: {
    status?: string;
    repository?: string;
    default_branch?: string;
    observed_commit_sha?: string;
    checked_at?: string;
    timeframe_days?: number;
    timeframe_start?: string;
    baseline?: {
      status?: string;
      baseline_type?: string;
      run_id?: string;
      snapshot_id?: string;
      snapshot_commit_sha?: string;
      scanner_id?: string;
    };
  };
  source_ledger?: Record<string, SourceState>;
  maturity_signal?: {level?: string; score?: number; calculated?: boolean; summary?: string};
  evidence_readiness?: {readiness_score?: number; calculated?: boolean; calculated_sections?: number; total_sections?: number};
  sections?: RetainerSection[];
  weekly_status_report?: string[];
  monthly_strategy_report?: string[];
  release_checklist?: string[];
  human_approval_queue?: string[];
  human_review_required?: boolean;
  client_delivery_allowed?: boolean;
};

function statusClass(status?: string) {
  const value = String(status || "unverified").toLowerCase();
  if (["green", "clear", "verified", "complete", "ready_for_human_release_review", "ready_for_human_retainer_review"].includes(value)) return "status green";
  if (["yellow", "partial", "needs_more_retainer_evidence", "needs_release_evidence"].includes(value)) return "status yellow";
  if (["red", "blocked", "blocked_by_retainer_risk", "needs_escalation", "failed"].includes(value)) return "status red";
  return "status gray";
}

function lines(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function List({items}: {items?: string[]}) {
  if (!items?.length) return <p className="muted">No items returned.</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export default function RetainerOpsPage() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [timeframeDays, setTimeframeDays] = useState("30");
  const [authorizedBy, setAuthorizedBy] = useState("frontend_reviewer");
  const [authorizationScope, setAuthorizationScope] = useState("repository assessment and retainer evidence review only");
  const [authorized, setAuthorized] = useState(false);
  const [roadmapNotes, setRoadmapNotes] = useState("");
  const [clientUpdate, setClientUpdate] = useState("");
  const [metrics, setMetrics] = useState("");
  const [budgetPriorities, setBudgetPriorities] = useState("");
  const [result, setResult] = useState<RetainerResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const sourceRows = useMemo(() => Object.values(result?.source_ledger || {}).sort((a, b) => String(a.source_id).localeCompare(String(b.source_id))), [result]);

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!API_URL) {
      setError("NEXT_PUBLIC_NICO_API_URL is not configured for this deployment.");
      return;
    }
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/retainer/ops`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          repository,
          authorized,
          authorized_by: authorizedBy,
          authorization_scope: authorizationScope,
          client_name: clientName,
          project_name: projectName,
          customer_id: customerId,
          project_id: projectId,
          baseline_run_id: baselineRunId,
          timeframe_days: Number(timeframeDays || 30),
          refresh_evidence: true,
          roadmap_notes: roadmapNotes,
          client_update: clientUpdate,
          retainer_metrics: metrics,
          success_metrics: "",
          budget_priorities: budgetPriorities,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Retainer request failed (${response.status}).`);
      setResult(payload as RetainerResult);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Retainer request failed.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">Retainer Operations</p>
      <h1>Verified weekly delivery, backlog, release, and blocker evidence</h1>
      <p className="lead">NICO collects technical evidence from the authorized GitHub repository. The operator supplies only business context GitHub cannot prove.</p>
      <div className="hero-actions"><a className="secondary-link" href="/">Command Center</a><a className="secondary-link" href="/operations">Operations</a></div>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Authorized source binding</p><h2>Repository and assessment baseline</h2></div><span className="status gray">No manual technical summaries</span></div>
      <p className="warning-box">An empty blocker field is not treated as clear. Blockers become clear only after GitHub issue and workflow sources are successfully checked.</p>
      <form onSubmit={run}>
        <div className="form-grid">
          <label>Repository owner/name<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repository" /></label>
          <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
          <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
          <label>Baseline run ID, optional<input value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)} placeholder="midrun_... or fullrun_..." /></label>
          <label>Evidence timeframe, days<input inputMode="numeric" value={timeframeDays} onChange={(event) => setTimeframeDays(event.target.value.replace(/[^0-9]/g, ""))} /></label>
          <label>Authorized by<input value={authorizedBy} onChange={(event) => setAuthorizedBy(event.target.value)} /></label>
          <label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} /></label>
          <label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} /></label>
        </div>
        <label className="wide-label">Authorization scope<textarea value={authorizationScope} onChange={(event) => setAuthorizationScope(event.target.value)} /></label>
        <div className="form-grid">
          <label>Roadmap decisions and priorities<textarea value={roadmapNotes} onChange={(event) => setRoadmapNotes(event.target.value)} placeholder="Only decisions and priorities GitHub cannot prove" /></label>
          <label>Client update context<textarea value={clientUpdate} onChange={(event) => setClientUpdate(event.target.value)} placeholder="Draft context for human review" /></label>
          <label>Business or retainer metrics<textarea value={metrics} onChange={(event) => setMetrics(event.target.value)} placeholder="Outcomes, service metrics, or client measures" /></label>
          <label>Budget and priority context<textarea value={budgetPriorities} onChange={(event) => setBudgetPriorities(event.target.value)} placeholder="Approved budget, priority, scope, or timeline context" /></label>
        </div>
        <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I confirm I own this repository or have explicit permission to assess it and review its Retainer evidence.</label>
        <button type="submit" className="primary-button" disabled={!API_URL || !authorized || !repository.trim() || loading}>{loading ? "Refreshing verified evidence..." : "Run Retainer Evidence Refresh"}</button>
      </form>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {result ? <>
      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Evidence identity</p><h2>{result.repository || "Repository unavailable"}</h2></div><span className={statusClass(result.status)}>{result.status || "unverified"}</span></div>
        <div className="grid four target-grid">
          <article><b>Observed commit</b><span>{result.source_binding?.observed_commit_sha?.slice(0, 12) || "Unavailable"}</span></article>
          <article><b>Baseline run</b><span>{result.source_binding?.baseline?.run_id || "Not available"}</span></article>
          <article><b>Snapshot</b><span>{result.source_binding?.baseline?.snapshot_commit_sha?.slice(0, 12) || "Not captured"}</span></article>
          <article><b>Scanner</b><span>{result.source_binding?.baseline?.scanner_id || "Not bound"}</span></article>
        </div>
        <p className="summary-box"><b>Checked:</b> {result.source_binding?.checked_at || result.generated_at || "Unavailable"} · timeframe={result.source_binding?.timeframe_days || "?"} days · branch={result.source_binding?.default_branch || "unknown"}</p>
        <p className="warning-box">Human review required: {String(Boolean(result.human_review_required))}. Client delivery allowed: {String(Boolean(result.client_delivery_allowed))}.</p>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Source ledger</p><h2>Exact evidence checks</h2></div><span className="status blue">{sourceRows.length} sources</span></div>
        <div className="results-grid">{sourceRows.map((source) => <article className="result-card" key={source.source_id}>
          <div className="result-head"><b>{source.source_id}</b><span className={statusClass(source.status)}>{source.status || "unavailable"}</span></div>
          <p><b>Items:</b> {source.item_count === null || source.item_count === undefined ? "Unavailable" : source.item_count}</p>
          <p><b>Checked:</b> {source.checked_at || "Unavailable"}</p>
          {source.derived_from ? <p><b>Derived from:</b> {source.derived_from}</p> : null}
          {source.note ? <p>{source.note}</p> : null}
        </article>)}</div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Reconciled result</p><h2>{result.maturity_signal?.calculated ? `${result.maturity_signal.level} · ${result.maturity_signal.score}/100` : "Maturity score unavailable"}</h2></div><span className={statusClass(result.status)}>{result.status || "unverified"}</span></div>
        <div className="results-grid">{result.sections?.map((section) => <article className="result-card" key={section.id}>
          <div className="result-head"><b>{section.label}</b><span className={statusClass(section.status)}>{section.status || "unverified"} · {section.score_calculated ? `${section.score}/100` : "score unavailable"}</span></div>
          <p>{section.summary}</p>
          <h3>Evidence</h3><List items={section.evidence} />
          {section.findings?.length ? <><h3>Findings</h3><List items={section.findings} /></> : null}
          {section.unavailable?.length ? <><h3>Unavailable</h3><List items={section.unavailable} /></> : null}
        </article>)}</div>
      </section>

      <section className="section panel">
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">Weekly status</p><List items={result.weekly_status_report} /></div>
          <div className="mini-panel"><p className="eyebrow">Monthly strategy</p><List items={result.monthly_strategy_report} /></div>
          <div className="mini-panel"><p className="eyebrow">Release checklist</p><List items={result.release_checklist} /></div>
          <div className="mini-panel"><p className="eyebrow">Human approval queue</p><List items={result.human_approval_queue} /></div>
        </div>
      </section>
    </> : null}
  </main>;
}
