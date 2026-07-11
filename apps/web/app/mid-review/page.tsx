"use client";

import {useState} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type ReviewItem = {
  item_id?: string;
  category?: string;
  section_id?: string;
  title?: string;
  reason?: string;
  severity?: string;
  evidence?: string[];
  blockers?: string[];
  score_change_material?: boolean;
  inference_based?: boolean;
};
type VerifiedSection = {section_id?: string; label?: string; truth_status?: string; summary?: string; evidence_count?: number; collapsed_by_default?: boolean};
type ReviewPacket = {
  status?: string;
  packet_version?: string;
  review_packet_id?: string;
  review_packet_sha256?: string;
  run_id?: string;
  repository?: string;
  snapshot_id?: string;
  snapshot_commit_sha?: string;
  exceptions?: ReviewItem[];
  verified_sections?: VerifiedSection[];
  summary?: {
    section_count?: number;
    sections_verified?: number;
    items_requiring_review?: number;
    unavailable_evidence_sources?: number;
    unsupported_claims_permitted?: number;
    critical_items?: number;
    high_items?: number;
    inference_items?: number;
    score_changing_items?: number;
    category_counts?: Record<string, number>;
  };
  human_approval_required?: boolean;
  approval_controls_available?: boolean;
  approval_controls_note?: string;
  rule?: string;
};

function statusClass(value?: string) {
  const normalized = String(value || "").toLowerCase();
  if (["verified", "ready_for_review", "low", "informational"].includes(normalized)) return "status green";
  if (["medium", "pending"].includes(normalized)) return "status yellow";
  if (["critical", "high", "failed", "blocked"].includes(normalized)) return "status red";
  return "status gray";
}

export default function MidReviewPage() {
  const [runId, setRunId] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [packet, setPacket] = useState<ReviewPacket | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadPacket() {
    if (!API_URL || !runId.trim() || !adminToken.trim() || loading) return;
    setError("");
    setPacket(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId.trim() || "default_customer", project_id: projectId.trim() || "default_project"});
      const response = await fetch(`${API_URL}/assessment/mid-run/${encodeURIComponent(runId.trim())}/review-exceptions?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      const data = await response.json() as ReviewPacket & {detail?: {message?: string}};
      if (!response.ok || data.status !== "ready_for_review") throw new Error(data.detail?.message || "Mid review packet could not be loaded.");
      setPacket(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Mid review packet could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Mid Assessment</p>
      <h1>Review by exception</h1>
      <p className="lead">Inspect only the findings, conflicts, limitations, missing evidence, failed tools, score-changing claims, and inference-based context that require a human decision.</p>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Reviewer access</p><h2>Load exact Mid run</h2></div><span className={packet ? "status green" : "status gray"}>{packet ? "packet loaded" : "not loaded"}</span></div>
      <p className="warning-box">Use the exact Mid run and customer/project scope. The admin token remains in browser state only and is not included in the review packet.</p>
      <div className="form-grid">
        <label>Mid run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="midrun_..." /></label>
        <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
        <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
        <label>NICO admin token<input type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
      </div>
      <button type="button" className="primary-button" disabled={!API_URL || !runId.trim() || !adminToken.trim() || loading} onClick={loadPacket}>{loading ? "Building reviewer packet..." : "Load review exceptions"}</button>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    {packet ? <>
      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Packet identity</p><h2>{packet.review_packet_id}</h2></div><span className={statusClass(packet.status)}>{packet.status}</span></div>
        <div className="grid four target-grid">
          <article><b>Verified sections</b><span>{packet.summary?.sections_verified ?? 0}</span></article>
          <article><b>Items requiring review</b><span>{packet.summary?.items_requiring_review ?? 0}</span></article>
          <article><b>Unavailable sources</b><span>{packet.summary?.unavailable_evidence_sources ?? 0}</span></article>
          <article><b>Unsupported claims permitted</b><span>{packet.summary?.unsupported_claims_permitted ?? 0}</span></article>
        </div>
        <div className="grid four target-grid">
          <article><b>Critical items</b><span>{packet.summary?.critical_items ?? 0}</span></article>
          <article><b>High items</b><span>{packet.summary?.high_items ?? 0}</span></article>
          <article><b>Score-changing items</b><span>{packet.summary?.score_changing_items ?? 0}</span></article>
          <article><b>Inference items</b><span>{packet.summary?.inference_items ?? 0}</span></article>
        </div>
        <details className="help-details"><summary>Immutable source identity</summary><pre className="json-block">{JSON.stringify({
          run_id: packet.run_id,
          repository: packet.repository,
          snapshot_id: packet.snapshot_id,
          snapshot_commit_sha: packet.snapshot_commit_sha,
          review_packet_sha256: packet.review_packet_sha256,
          packet_version: packet.packet_version,
        }, null, 2)}</pre></details>
        <p className="warning-box">{packet.approval_controls_note}</p>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Exceptions</p><h2>Human review queue</h2></div><span className={packet.exceptions?.length ? "status yellow" : "status green"}>{packet.exceptions?.length || 0} items</span></div>
        <div className="results-grid">{packet.exceptions?.map((item) => <details className="result-card" open key={item.item_id}>
          <summary><b>{item.title || item.category}</b> <span className={statusClass(item.severity)}>{item.severity || "medium"}</span></summary>
          <p>{item.reason}</p>
          <p className="muted">Category: {item.category}; section: {item.section_id}; score-changing={String(Boolean(item.score_change_material))}; inference-based={String(Boolean(item.inference_based))}</p>
          {item.evidence?.length ? <><h3>Evidence</h3><ul className="tight-list">{item.evidence.map((value, index) => <li key={`${item.item_id}-e-${index}`}>{value}</li>)}</ul></> : null}
          {item.blockers?.length ? <><h3>Blockers</h3><ul className="tight-list">{item.blockers.map((value, index) => <li key={`${item.item_id}-b-${index}`}>{value}</li>)}</ul></> : null}
        </details>)}</div>
      </section>

      <section className="section panel">
        <details className="help-details"><summary>Verified automatically — evidence available ({packet.verified_sections?.length || 0})</summary>
          <div className="results-grid">{packet.verified_sections?.map((section) => <article className="result-card" key={section.section_id}>
            <div className="result-head"><b>{section.label || section.section_id}</b><span className="status green">Verified</span></div>
            <p>{section.summary}</p><p className="muted">Direct evidence items: {section.evidence_count || 0}</p>
          </article>)}</div>
        </details>
        <p className="muted">{packet.rule}</p>
      </section>
    </> : null}
  </main>;
}
