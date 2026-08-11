"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./review-browser.module.css";

type JsonRecord = Record<string, unknown>;
type Projection = {
  candidates?: JsonRecord[];
  clusters?: JsonRecord[];
  queue_counts?: JsonRecord;
  workload_metrics?: JsonRecord;
  quality_control_sampling?: JsonRecord;
  ready_for_final_approval?: boolean;
};

type Queue = "all" | "critical_material" | "human_technical_review" | "new_automated_triage_complete" | "stable_carry_forward" | "quality_control_sample" | "human_disposition_completed";
type Sort = "risk" | "confidence_desc" | "confidence_asc" | "candidate_id";

const QUEUES: {value: Queue; label: string}[] = [
  {value: "all", label: "All canonical candidates"},
  {value: "critical_material", label: "Critical / material"},
  {value: "human_technical_review", label: "Human technical review"},
  {value: "new_automated_triage_complete", label: "New automated triage complete"},
  {value: "stable_carry_forward", label: "Stable carry-forward"},
  {value: "quality_control_sample", label: "Quality-control sample"},
  {value: "human_disposition_completed", label: "Human disposition completed"},
];

const SEVERITY_RANK: Record<string, number> = {critical: 5, material: 5, high: 4, medium: 3, moderate: 3, low: 2, informational: 1, info: 1};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function numberValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function boolValue(value: unknown): boolean {
  return value === true;
}

function responseError(payload: JsonRecord, status: number): string {
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return text(payload.error) || `HTTP ${status}`;
}

function searchHaystack(candidate: JsonRecord): string {
  const keys = [
    "candidate_id", "finding_id", "path", "file_path", "package", "package_name",
    "advisory", "advisory_id", "rule", "rule_id", "scanner", "category", "manifest",
    "cluster_id", "technical_triage_verdict", "severity",
  ];
  return keys.map((key) => text(candidate[key])).join(" ").toLocaleLowerCase();
}

function unique(candidates: JsonRecord[], key: string): string[] {
  return [...new Set(candidates.map((candidate) => text(candidate[key])).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function renderDetail(candidate: JsonRecord): string {
  return JSON.stringify(candidate, null, 2);
}

export default function ReviewQueueBrowser() {
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [projection, setProjection] = useState<Projection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue>("all");
  const [severity, setSeverity] = useState("all");
  const [verdict, setVerdict] = useState("all");
  const [confidence, setConfidence] = useState("all");
  const [lineage, setLineage] = useState("all");
  const [scanner, setScanner] = useState("all");
  const [category, setCategory] = useState("all");
  const [disposition, setDisposition] = useState("all");
  const [attention, setAttention] = useState("all");
  const [sort, setSort] = useState<Sort>("risk");
  const [query, setQuery] = useState("");
  const [samplingStrategy, setSamplingStrategy] = useState("deterministic");
  const [sampleSize, setSampleSize] = useState("");

  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    setRunId(params.get("run_id") || "");
  }, []);

  const endpoint = useMemo(
    () => `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review-work`,
    [runId],
  );

  async function load(): Promise<void> {
    if (!runId.trim() || !adminToken.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(endpoint, {
        method: "GET",
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken},
      });
      const payload = await response.json().catch(() => ({})) as Projection & JsonRecord;
      if (!response.ok) throw new Error(responseError(payload, response.status));
      setProjection(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function configureSampling(): Promise<void> {
    if (!runId.trim() || !adminToken.trim() || !reviewer.trim() || !reviewerRole.trim()) return;
    setBusy(true);
    setError("");
    try {
      const payload: JsonRecord = {
        action: "configure_qc_sampling",
        reviewer: reviewer.trim(),
        reviewer_role: reviewerRole.trim(),
        review_authorized: true,
        authorization_confirmed: true,
        sampling_strategy: samplingStrategy,
      };
      if (sampleSize.trim()) payload.sample_size = Number.parseInt(sampleSize, 10);
      const response = await fetch(endpoint, {
        method: "POST",
        cache: "no-store",
        headers: {"Content-Type": "application/json", Accept: "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({})) as Projection & JsonRecord;
      if (!response.ok) throw new Error(responseError(result, response.status));
      setProjection(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  const candidates = useMemo(
    () => (projection?.candidates || []).filter((candidate): candidate is JsonRecord => Boolean(candidate && typeof candidate === "object")),
    [projection],
  );
  const severities = useMemo(() => unique(candidates, "severity"), [candidates]);
  const verdicts = useMemo(() => unique(candidates, "technical_triage_verdict"), [candidates]);
  const lineages = useMemo(() => unique(candidates, "evidence_change_state"), [candidates]);
  const scanners = useMemo(() => unique(candidates, "scanner"), [candidates]);
  const categories = useMemo(() => unique(candidates, "category"), [candidates]);

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const rows = candidates.filter((candidate) => {
      if (queue === "quality_control_sample" && !boolValue(candidate.quality_control_sample)) return false;
      if (queue !== "all" && queue !== "quality_control_sample" && text(candidate.primary_review_queue) !== queue) return false;
      if (severity !== "all" && text(candidate.severity) !== severity) return false;
      if (verdict !== "all" && text(candidate.technical_triage_verdict) !== verdict) return false;
      const candidateConfidence = numberValue(candidate.technical_triage_confidence);
      if (confidence === "low" && candidateConfidence >= 0.85) return false;
      if (confidence === "high" && candidateConfidence < 0.85) return false;
      if (lineage !== "all" && text(candidate.evidence_change_state) !== lineage) return false;
      if (scanner !== "all" && text(candidate.scanner) !== scanner) return false;
      if (category !== "all" && text(candidate.category) !== category) return false;
      if (disposition !== "all" && text(candidate.human_disposition_state) !== disposition) return false;
      if (attention === "individual" && !boolValue(candidate.individual_attention_required)) return false;
      if (attention === "grouped" && !boolValue(candidate.grouped_review_eligible)) return false;
      if (normalizedQuery && !searchHaystack(candidate).includes(normalizedQuery)) return false;
      return true;
    });
    return rows.sort((left, right) => {
      if (sort === "candidate_id") return text(left.candidate_id).localeCompare(text(right.candidate_id));
      if (sort === "confidence_desc") return numberValue(right.technical_triage_confidence) - numberValue(left.technical_triage_confidence);
      if (sort === "confidence_asc") return numberValue(left.technical_triage_confidence) - numberValue(right.technical_triage_confidence);
      const risk = (SEVERITY_RANK[text(right.severity).toLowerCase()] || 0) - (SEVERITY_RANK[text(left.severity).toLowerCase()] || 0);
      return risk || numberValue(left.technical_triage_confidence) - numberValue(right.technical_triage_confidence) || text(left.candidate_id).localeCompare(text(right.candidate_id));
    });
  }, [attention, candidates, category, confidence, disposition, lineage, query, queue, scanner, severity, sort, verdict]);

  const clusters = (projection?.clusters || []).filter((cluster): cluster is JsonRecord => Boolean(cluster && typeof cluster === "object"));
  const sampling = projection?.quality_control_sampling || {};
  const workload = projection?.workload_metrics || {};
  const queueCounts = projection?.queue_counts || {};

  return <section className={styles.panel} data-review-browser="phase2">
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NICO COMPREHENSIVE · REVIEW BY EXCEPTION</p>
        <h2>Canonical review queues, filtering, search, clusters, and QC sampling</h2>
        <p>NICO has already performed the repeatable technical analysis. Use these controls to isolate the evidence that needs professional attention. Full candidate evidence remains expandable.</p>
      </div>
      <span className={projection?.ready_for_final_approval ? styles.ready : styles.blocked}>{projection?.ready_for_final_approval ? "Review ready for separate final approval" : "Final approval blocked"}</span>
    </header>

    <div className={styles.credentials}>
      <label>Exact run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} autoComplete="off" /></label>
      <label>Operator admin token<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" /></label>
      <label>Authorized reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="off" /></label>
      <label>Reviewer role<input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} autoComplete="off" /></label>
      <button type="button" onClick={load} disabled={busy || !runId.trim() || !adminToken.trim()}>{busy ? "Working…" : projection ? "Refresh review truth" : "Load review truth"}</button>
    </div>
    <p className={styles.security}>The admin token remains only in page-local state and is sent only to the protected exact-run review endpoint.</p>
    {error ? <p className={styles.error}>{error}</p> : null}

    {projection ? <>
      <div className={styles.metrics}>
        <article><strong>{text(workload.individual_attention_count) || "0"}</strong><span>individual attention</span></article>
        <article><strong>{text(workload.grouped_review_eligible_count) || "0"}</strong><span>grouped-review eligible</span></article>
        <article><strong>{text(workload.quality_control_sample_size) || "0"}</strong><span>QC sample</span></article>
        <article><strong>{text(workload.human_dispositions_pending) || "0"}</strong><span>human dispositions pending</span></article>
        <article><strong>{text(workload.human_dispositions_completed) || "0"}</strong><span>human dispositions completed</span></article>
        <article><strong>{text(workload.clusters_remaining) || "0"}</strong><span>clusters remaining</span></article>
        <article><strong>{text(workload.measured_specialist_hours) || "0"} h</strong><span>measured specialist time</span></article>
      </div>

      <div className={styles.queueStrip}>
        {QUEUES.slice(1).map((item) => <button key={item.value} type="button" className={queue === item.value ? styles.activeQueue : ""} onClick={() => setQueue(item.value)}><span>{item.label}</span><b>{text(queueCounts[item.value]) || "0"}</b></button>)}
      </div>

      <div className={styles.filters}>
        <label>Queue<select value={queue} onChange={(event) => setQueue(event.target.value as Queue)}>{QUEUES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">All</option>{severities.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Technical verdict<select value={verdict} onChange={(event) => setVerdict(event.target.value)}><option value="all">All</option>{verdicts.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Confidence<select value={confidence} onChange={(event) => setConfidence(event.target.value)}><option value="all">All</option><option value="low">Below 0.85</option><option value="high">0.85 and above</option></select></label>
        <label>Evidence change<select value={lineage} onChange={(event) => setLineage(event.target.value)}><option value="all">All</option>{lineages.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Scanner<select value={scanner} onChange={(event) => setScanner(event.target.value)}><option value="all">All</option>{scanners.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">All</option>{categories.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Human disposition<select value={disposition} onChange={(event) => setDisposition(event.target.value)}><option value="all">All</option><option value="pending">Pending</option><option value="completed">Completed</option></select></label>
        <label>Review mode<select value={attention} onChange={(event) => setAttention(event.target.value)}><option value="all">All</option><option value="individual">Individual attention</option><option value="grouped">Grouped review eligible</option></select></label>
        <label>Sort<select value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="risk">Risk priority</option><option value="confidence_desc">Confidence high to low</option><option value="confidence_asc">Confidence low to high</option><option value="candidate_id">Candidate ID</option></select></label>
        <label className={styles.search}>Search candidate / finding / path / package / advisory / rule / scanner<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Exact ID or evidence term" /></label>
      </div>

      <section className={styles.sampling}>
        <div><h3>Quality-control sampling</h3><p>Sampling validates automation quality. It never approves unsampled candidates and never creates a human disposition.</p></div>
        <label>Strategy<select value={samplingStrategy} onChange={(event) => setSamplingStrategy(event.target.value)}><option value="deterministic">Deterministic</option><option value="risk_weighted">Risk-weighted</option></select></label>
        <label>Sample size<input type="number" min="0" value={sampleSize} onChange={(event) => setSampleSize(event.target.value)} placeholder={text(sampling.sample_size) || "auto"} /></label>
        <button type="button" onClick={configureSampling} disabled={busy || !reviewer.trim() || !reviewerRole.trim()}>Configure explicit QC sample</button>
        <code>{text(sampling.sampling_version)}</code>
      </section>

      <div className={styles.resultHeader}><h3>{filtered.length} candidate{filtered.length === 1 ? "" : "s"}</h3><button type="button" onClick={() => {setQueue("all"); setSeverity("all"); setVerdict("all"); setConfidence("all"); setLineage("all"); setScanner("all"); setCategory("all"); setDisposition("all"); setAttention("all"); setQuery("");}}>Clear filters</button></div>
      <div className={styles.candidates}>
        {filtered.map((candidate) => <details key={text(candidate.candidate_id)} className={styles.candidate}>
          <summary>
            <span><b>{text(candidate.candidate_id)}</b><small>{text(candidate.scanner) || text(candidate.category) || "canonical candidate"}</small></span>
            <span className={styles.badges}><i>{text(candidate.severity) || "unknown"}</i><i>{text(candidate.technical_triage_verdict) || "triage pending"}</i><i>{text(candidate.human_disposition_state)}</i>{boolValue(candidate.quality_control_sample) ? <i>QC</i> : null}</span>
          </summary>
          <div className={styles.detailGrid}>
            <p><b>Cluster</b>{text(candidate.cluster_id) || "—"}</p><p><b>Confidence</b>{numberValue(candidate.technical_triage_confidence).toFixed(3)}</p><p><b>Path</b>{text(candidate.path) || text(candidate.file_path) || "—"}</p><p><b>Package / advisory</b>{text(candidate.package) || text(candidate.package_name) || text(candidate.advisory) || "—"}</p><p><b>Rule</b>{text(candidate.rule) || text(candidate.rule_id) || "—"}</p><p><b>Evidence change</b>{text(candidate.evidence_change_state) || "—"}</p><p><b>Primary queue</b>{text(candidate.primary_review_queue)}</p><p><b>Review mode</b>{boolValue(candidate.individual_attention_required) ? "Individual" : boolValue(candidate.grouped_review_eligible) ? "Grouped eligible" : "Standard"}</p>
          </div>
          <pre>{renderDetail(candidate)}</pre>
        </details>)}
      </div>

      <section className={styles.clusters}>
        <h3>Clusters</h3>
        <p>Clusters summarize homogeneous review work. Expand any cluster to inspect its exact underlying candidate IDs and retained metadata.</p>
        {clusters.map((cluster) => <details key={text(cluster.cluster_id)}><summary><b>{text(cluster.cluster_id)}</b><span>{Array.isArray(cluster.candidate_ids) ? cluster.candidate_ids.length : 0} candidates</span></summary><pre>{JSON.stringify(cluster, null, 2)}</pre></details>)}
      </section>
    </> : null}
  </section>;
}
