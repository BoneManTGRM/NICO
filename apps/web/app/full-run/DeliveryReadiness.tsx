"use client";

import {useState} from "react";

type Check = {id?: string; passed?: boolean; message?: string; evidence?: unknown};
type Readiness = {
  status?: string;
  ready?: boolean;
  lifecycle?: string;
  run_id?: string;
  report_id?: string;
  approval_id?: string;
  checks?: Check[];
  blockers?: string[];
  summary?: {
    access_grant_count?: number;
    download_count?: number;
    verified_receipt_count?: number;
    verified_acknowledgment_count?: number;
    consumption_mismatch_count?: number;
  };
  repairable_orphaned_consumptions?: Array<Record<string, unknown>>;
  critical_over_receipting?: Array<Record<string, unknown>>;
  rule?: string;
};

type ReconcileResponse = {
  status?: string;
  repaired_count?: number;
  skipped_count?: number;
  grace_seconds?: number;
  repaired?: Array<Record<string, unknown>>;
  skipped?: Array<Record<string, unknown>>;
  readiness_after?: Readiness;
  detail?: {message?: string};
};

type Props = {
  apiUrl: string;
  runId: string;
  customerId: string;
  projectId: string;
  adminToken: string;
  actor: string;
  disabled?: boolean;
};

function statusClass(status?: string) {
  if (["ready", "approved", "shared", "delivered", "acknowledged", "reconciled", "no_change"].includes(status || "")) return "status green";
  if (["pending", "shared"].includes(status || "")) return "status yellow";
  if (["blocked", "failed"].includes(status || "")) return "status red";
  return "status gray";
}

export default function DeliveryReadiness({apiUrl, runId, customerId, projectId, adminToken, actor, disabled = false}: Props) {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [reconcileResult, setReconcileResult] = useState<ReconcileResponse | null>(null);
  const [graceSeconds, setGraceSeconds] = useState(300);
  const [loading, setLoading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [error, setError] = useState("");

  async function readJson(response: Response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data?.detail?.message || `Delivery readiness request failed with ${response.status}.`);
    return data;
  }

  async function refresh() {
    if (!apiUrl || !runId || !adminToken.trim() || disabled) return;
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({customer_id: customerId, project_id: projectId});
      const response = await fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/readiness?${params.toString()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      const data = await readJson(response) as Readiness;
      setReadiness(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delivery readiness could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function reconcile() {
    if (!apiUrl || !runId || !adminToken.trim() || disabled || reconciling) return;
    setError("");
    setReconciling(true);
    setReconcileResult(null);
    try {
      const params = new URLSearchParams({
        customer_id: customerId,
        project_id: projectId,
        actor: actor || "delivery_operator",
        grace_seconds: String(Math.max(0, Math.min(3600, graceSeconds || 0))),
      });
      const response = await fetch(`${apiUrl}/assessment/full-run/${encodeURIComponent(runId)}/approved-delivery/reconcile?${params.toString()}`, {
        method: "POST",
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      const data = await readJson(response) as ReconcileResponse;
      setReconcileResult(data);
      if (data.readiness_after) setReadiness(data.readiness_after);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delivery reconciliation failed.");
    } finally {
      setReconciling(false);
    }
  }

  const repairableCount = readiness?.repairable_orphaned_consumptions?.length || 0;
  const criticalCount = readiness?.critical_over_receipting?.length || 0;

  return <div className="mini-panel">
    <div className="section-head">
      <div><p className="eyebrow">Operational gate</p><h2>End-to-end delivery readiness</h2></div>
      <span className={statusClass(readiness?.ready ? readiness.lifecycle || "ready" : readiness?.status)}>{readiness?.ready ? readiness.lifecycle || "ready" : readiness?.status || "not checked"}</span>
    </div>
    <p className="muted">Verifies human approval, approved-artifact hashes, hosted storage, access grants, receipts, acknowledgments, scope bindings, and one verified receipt for every consumed download.</p>
    <div className="report-actions">
      <button type="button" className="primary-button" disabled={disabled || loading || !runId || !adminToken.trim()} onClick={refresh}>{loading ? "Checking..." : "Check delivery readiness"}</button>
    </div>
    {error ? <p className="error-box">{error}</p> : null}

    {readiness ? <>
      <div className="grid four target-grid">
        <article><b>Access grants</b><span>{readiness.summary?.access_grant_count ?? 0}</span></article>
        <article><b>Consumed downloads</b><span>{readiness.summary?.download_count ?? 0}</span></article>
        <article><b>Verified receipts</b><span>{readiness.summary?.verified_receipt_count ?? 0}</span></article>
        <article><b>Acknowledgments</b><span>{readiness.summary?.verified_acknowledgment_count ?? 0}</span></article>
      </div>
      <div className="results-grid">{(readiness.checks || []).map((item) => <article className="result-card" key={item.id || item.message}>
        <div className="result-head"><b>{String(item.id || "check").replaceAll("_", " ")}</b><span className={item.passed ? "status green" : "status red"}>{item.passed ? "passed" : "blocked"}</span></div>
        <p>{item.message || "No message returned."}</p>
        {item.evidence !== undefined ? <details className="help-details"><summary>Evidence</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}
      </article>)}</div>
      {readiness.blockers?.length ? <p className="error-box">{readiness.blockers.join(" ")}</p> : <p className="warning-box">All operational delivery checks passed for lifecycle state: {readiness.lifecycle}.</p>}

      <div className="mini-panel">
        <div className="section-head"><div><p className="eyebrow">Safe repair</p><h2>Orphaned download reconciliation</h2></div><span className={criticalCount ? "status red" : repairableCount ? "status yellow" : "status green"}>{criticalCount ? "manual review" : repairableCount ? `${repairableCount} repairable` : "balanced"}</span></div>
        <p className="muted">Only reduces consumed counts that have no verified receipt, are older than the concurrency grace window, and have not changed since inspection. Receipt over-counts and integrity failures are never auto-repaired.</p>
        <div className="form-grid"><label>Concurrency grace seconds<input type="number" min={0} max={3600} value={graceSeconds} onChange={(event) => setGraceSeconds(Number(event.target.value) || 0)} /></label></div>
        <div className="report-actions"><button type="button" disabled={!repairableCount || criticalCount > 0 || reconciling || !adminToken.trim()} onClick={reconcile}>{reconciling ? "Reconciling..." : "Reconcile orphaned counts"}</button></div>
        {readiness.repairable_orphaned_consumptions?.length ? <pre className="json-block">{JSON.stringify(readiness.repairable_orphaned_consumptions, null, 2)}</pre> : null}
        {reconcileResult ? <details className="help-details" open><summary>Reconciliation result</summary><pre className="json-block">{JSON.stringify(reconcileResult, null, 2)}</pre></details> : null}
      </div>
      {readiness.rule ? <p className="muted">{readiness.rule}</p> : null}
    </> : null}
  </div>;
}
