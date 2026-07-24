"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type SourceState = {source_id?: string; status?: string; checked_at?: string; item_count?: number | null; note?: string; derived_from?: string};
type RetainerSection = {id?: string; label?: string; score?: number; score_calculated?: boolean; status?: string; summary?: string; evidence?: string[]; findings?: string[]; unavailable?: string[]};
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
    baseline?: {status?: string; baseline_type?: string; run_id?: string; snapshot_id?: string; snapshot_commit_sha?: string; scanner_id?: string};
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

function statusClass(status?: string): string {
  const value = String(status || "unverified").toLowerCase();
  if (["green", "clear", "verified", "complete", "ready_for_human_release_review", "ready_for_human_retainer_review"].includes(value)) return "status green";
  if (["yellow", "partial", "needs_more_retainer_evidence", "needs_release_evidence"].includes(value)) return "status yellow";
  if (["red", "blocked", "blocked_by_retainer_risk", "needs_escalation", "failed"].includes(value)) return "status red";
  return "status gray";
}

function List({items, empty = "No verified items returned."}: {items?: string[]; empty?: string}) {
  return items?.length
    ? <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    : <p className="muted">{empty}</p>;
}

function section(result: RetainerResult | null, id: string): RetainerSection | undefined {
  return result?.sections?.find((item) => item.id === id);
}

export default function RetainerWorkspace() {
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [timeframeDays, setTimeframeDays] = useState("30");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [roadmapNotes, setRoadmapNotes] = useState("");
  const [clientUpdate, setClientUpdate] = useState("");
  const [metrics, setMetrics] = useState("");
  const [budgetPriorities, setBudgetPriorities] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [result, setResult] = useState<RetainerResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setRepository(query.get("repository") || "BoneManTGRM/NICO");
    setBaselineRunId(query.get("baseline_run_id") || query.get("run_id") || "");
    setCustomerId(query.get("customer_id") || "default_customer");
    setProjectId(query.get("project_id") || "default_project");
  }, []);

  const sources = useMemo(
    () => Object.values(result?.source_ledger || {}).sort((a, b) => String(a.source_id).localeCompare(String(b.source_id))),
    [result],
  );
  const verifiedSources = sources.filter((item) => item.status === "verified").length;
  const blockers = section(result, "blockers");
  const release = section(result, "release_readiness");
  const weekly = section(result, "weekly_delivery");
  const baselineMatched = result?.source_binding?.baseline?.status === "matched";
  const healthScore = result?.maturity_signal?.calculated ? result.maturity_signal.score : undefined;

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!API_URL) {
      setError("The NICO API is not configured for this deployment.");
      return;
    }
    if (!baselineRunId.trim()) {
      setError("Choose the exact accepted Express or Comprehensive baseline run before refreshing ongoing evidence.");
      return;
    }
    if (!authorized) {
      setError("Confirm repository authorization before refreshing evidence.");
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
          authorized: true,
          authorized_by: "authorized_retainer_reviewer",
          authorization_scope: "repository assessment and ongoing evidence review only",
          client_name: clientName,
          project_name: projectName,
          customer_id: customerId,
          project_id: projectId,
          baseline_run_id: baselineRunId.trim(),
          timeframe_days: Number(timeframeDays || 30),
          refresh_evidence: true,
          roadmap_notes: roadmapNotes,
          client_update: clientUpdate,
          retainer_metrics: metrics,
          success_metrics: "",
          budget_priorities: budgetPriorities,
        }),
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Ongoing-evidence request failed (${response.status}).`);
      setResult(payload as RetainerResult);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ongoing evidence refresh failed.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell nico-retainer-workspace">
    <section className="hero">
      <p className="eyebrow">ONGOING ENGINEERING OVERSIGHT</p>
      <h1>See what changed after an accepted assessment.</h1>
      <p className="lead">Retainer Ops does not rerun the full assessment and does not deploy code. It compares current GitHub evidence with one exact accepted baseline, identifies blockers and release concerns, and prepares weekly and monthly material for human review.</p>
      <div className="hero-actions"><a className="primary-link" href="/assessment?tier=comprehensive#assessment">Create a baseline</a><a className="secondary-link" href="/operations/final-review">Approve a completed report</a></div>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">ONE CONTROL</p><h2>Refresh ongoing evidence</h2></div><span className="status blue">Read-only GitHub evidence</span></div>
      <p className="summary-box"><b>What it checks:</b> current commit, commits, pull requests, open issues, workflow results, CodeQL activity, releases, deployments, and verified blocker signals. It never treats an empty field as proof that risk is clear.</p>
      <form onSubmit={run}>
        <div className="form-grid">
          <label>Repository owner/name<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="owner/repository" /></label>
          <label>Accepted baseline run ID<input value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)} placeholder="express_run_… or comprun_…" /></label>
          <label>Evidence window<select value={timeframeDays} onChange={(event) => setTimeframeDays(event.target.value)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="180">Last 180 days</option></select></label>
        </div>

        <details className="retainer-advanced"><summary>Optional business context</summary><p className="retainer-context-note">These notes add decisions and business context that GitHub cannot prove. They cannot turn failed or unavailable technical evidence into a clean result.</p><div className="form-grid"><label>Roadmap decisions<textarea value={roadmapNotes} onChange={(event) => setRoadmapNotes(event.target.value)} placeholder="Approved priorities, dependencies, or sequencing" /></label><label>Client update context<textarea value={clientUpdate} onChange={(event) => setClientUpdate(event.target.value)} placeholder="Context for the next reviewed update" /></label><label>Success metrics<textarea value={metrics} onChange={(event) => setMetrics(event.target.value)} placeholder="Outcomes, service levels, or adoption measures" /></label><label>Budget and scope context<textarea value={budgetPriorities} onChange={(event) => setBudgetPriorities(event.target.value)} placeholder="Approved budget, scope, timeline, or priority constraints" /></label></div></details>

        <details className="retainer-advanced"><summary>Advanced project scope</summary><div className="form-grid"><label>Client name<input value={clientName} onChange={(event) => setClientName(event.target.value)} /></label><label>Project name<input value={projectName} onChange={(event) => setProjectName(event.target.value)} /></label><label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label><label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label></div></details>

        <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />I own this repository or have explicit permission to collect ongoing read-only engineering evidence.</label>
        <button type="submit" className="primary-button" disabled={!API_URL || !authorized || !repository.trim() || !baselineRunId.trim() || loading}>{loading ? "Checking current evidence…" : "Refresh ongoing evidence"}</button>
      </form>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {result ? <>
      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">CURRENT OVERVIEW</p><h2>{result.repository || repository}</h2></div><span className={statusClass(result.status)}>{String(result.status || "unverified").replaceAll("_", " ")}</span></div>
        <div className="grid four target-grid">
          <article><b>Baseline</b><span>{baselineMatched ? "Matched" : "Not matched"}</span><small>{result.source_binding?.baseline?.run_id || baselineRunId}</small></article>
          <article><b>Current commit</b><span>{result.source_binding?.observed_commit_sha?.slice(0, 12) || "Unavailable"}</span><small>{result.source_binding?.default_branch || "branch unavailable"}</small></article>
          <article><b>Verified sources</b><span>{verifiedSources}/{sources.length}</span><small>GitHub evidence checks</small></article>
          <article><b>Ongoing delivery health</b><span>{typeof healthScore === "number" ? `${healthScore}/100` : "Not calculated"}</span><small>This is not the assessment technical-maturity score.</small></article>
        </div>
        <p className="warning-box">Retainer results are advisory and require human review. Production actions, client communication, roadmap commitments, scope, budget, and timeline changes are never approved automatically.</p>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">WHAT NEEDS ATTENTION</p><h2>Changes, blockers, and release posture</h2></div></div>
        <div className="two-col inset-grid">
          <div className="mini-panel"><p className="eyebrow">What changed</p><p>{weekly?.summary || "Weekly delivery evidence was not calculated."}</p><List items={result.weekly_status_report} /></div>
          <div className="mini-panel"><p className="eyebrow">Current blockers</p><p>{blockers?.summary || "Blocker verification was not calculated."}</p><List items={blockers?.findings} empty="No verified blockers were returned. Review source completeness before treating this as clear." /></div>
          <div className="mini-panel"><p className="eyebrow">Release readiness</p><p>{release?.summary || "Release readiness was not calculated."}</p><List items={result.release_checklist} /></div>
          <div className="mini-panel"><p className="eyebrow">Next review actions</p><List items={result.human_approval_queue} empty="No approval items were returned." /></div>
        </div>
      </section>

      <section className="section panel">
        <details className="help-details"><summary>Detailed evidence and scoring</summary>
          <div className="section-head"><div><p className="eyebrow">SOURCE LEDGER</p><h2>Exact evidence checks</h2></div><span className="status blue">{sources.length} sources</span></div>
          <div className="results-grid">{sources.map((source) => <article className="result-card" key={source.source_id}><div className="result-head"><b>{source.source_id}</b><span className={statusClass(source.status)}>{source.status || "unavailable"}</span></div><p><b>Items:</b> {source.item_count === null || source.item_count === undefined ? "Unavailable" : source.item_count}</p><p><b>Checked:</b> {source.checked_at || "Unavailable"}</p>{source.derived_from ? <p><b>Derived from:</b> {source.derived_from}</p> : null}{source.note ? <p>{source.note}</p> : null}</article>)}</div>
          <div className="results-grid">{result.sections?.map((item) => <article className="result-card" key={item.id}><div className="result-head"><b>{item.label}</b><span className={statusClass(item.status)}>{item.status || "unverified"}</span></div><p>{item.summary}</p><p><b>Ongoing-health score:</b> {item.score_calculated ? `${item.score}/100` : "not calculated"}</p><h3>Evidence</h3><List items={item.evidence} />{item.findings?.length ? <><h3>Findings</h3><List items={item.findings} /></> : null}{item.unavailable?.length ? <><h3>Unavailable</h3><List items={item.unavailable} /></> : null}</article>)}</div>
          <div className="two-col inset-grid"><div className="mini-panel"><p className="eyebrow">Monthly strategy</p><List items={result.monthly_strategy_report} /></div><div className="mini-panel"><p className="eyebrow">Weekly status</p><List items={result.weekly_status_report} /></div></div>
        </details>
      </section>
    </> : null}
  </main>;
}
