"use client";

import {useEffect, useState} from "react";
import styles from "./operations.module.css";

type AssessmentRecoveryItem = {
  run_id?: string;
  workflow?: string;
  service_tier?: string;
  repository?: string;
  status?: string;
  scan_id?: string;
  snapshot_commit_sha?: string;
  report_id?: string;
  approval_id?: string;
  execution_checkpoint?: {
    current_step?: string;
    phase?: string;
    heartbeat_at?: string;
    completed_steps?: string[];
  };
  recovery?: {
    reason?: string;
    detected_at?: string;
    attempt?: number;
    resume_allowed?: boolean;
  };
};

type AssessmentRecoveryInventory = {
  status?: string;
  stale_seconds?: number;
  counts?: {
    recovery_required?: number;
    active?: number;
    express_recovery_required?: number;
    mid_recovery_required?: number;
    full_recovery_required?: number;
  };
  recovery_required?: AssessmentRecoveryItem[];
  operator_action?: string;
};

type Props = {
  apiUrl: string;
  adminToken: string;
  refreshKey: string;
  targetRunId?: string;
};

function tone(status?: string) {
  const value = String(status || "not_loaded").toLowerCase();
  if (value === "not_loaded") return styles.neutral;
  if (["clear", "complete", "running", "planned"].includes(value)) return styles.good;
  if (["attention_required", "recovery_required", "resuming", "degraded", "interrupted"].includes(value)) return styles.warn;
  return styles.bad;
}

export default function AssessmentRecoveryPanel({apiUrl, adminToken, refreshKey, targetRunId = ""}: Props) {
  const [inventory, setInventory] = useState<AssessmentRecoveryInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actor, setActor] = useState("operator");

  async function loadRecovery(refresh = false) {
    if (!apiUrl || !adminToken.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/operations/recovery/assessments?refresh=${refresh ? "true" : "false"}&limit=200`, {
        cache: "no-store",
        headers: {"X-NICO-Admin-Token": adminToken},
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Assessment recovery request failed (${response.status}).`);
      setInventory(payload as AssessmentRecoveryInventory);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Assessment recovery request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function resume(runId: string) {
    if (!runId || !apiUrl || !adminToken.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/operations/recovery/assessment/${encodeURIComponent(runId)}/resume`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-NICO-Admin-Token": adminToken,
        },
        body: JSON.stringify({actor: actor.trim() || "operator"}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Assessment resume failed (${response.status}).`);
      await loadRecovery(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Assessment resume failed.");
      setLoading(false);
    }
  }

  useEffect(() => {
    if (refreshKey && adminToken.trim()) void loadRecovery(false);
    // Admin authentication remains parent page memory and is never persisted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (!inventory || !targetRunId) return;
    window.setTimeout(() => document.getElementById(`assessment-recovery-${targetRunId}`)?.scrollIntoView({behavior: "smooth", block: "center"}), 0);
  }, [inventory, targetRunId]);

  const loaded = inventory !== null;
  const targetFound = Boolean(targetRunId && inventory?.recovery_required?.some((item) => item.run_id === targetRunId));

  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div><p className={styles.eyebrow}>Assessment recovery</p><h2>Interrupted Express, Mid, and Full runs</h2></div>
        <span className={`${styles.pill} ${tone(inventory?.status)}`}>{inventory?.status || "not loaded"}</span>
      </div>
      <div className={styles.gridFour}>
        <article className={styles.detailCard}><span>Recovery required</span><b>{loaded ? inventory?.counts?.recovery_required ?? "Unavailable" : "Not loaded"}</b><small>All recovery evidence requires an authenticated operator review.</small></article>
        <article className={styles.detailCard}><span>Express runs</span><b>{loaded ? inventory?.counts?.express_recovery_required ?? "Unavailable" : "Not loaded"}</b><small>Interrupted Express runs are retained for manual review and cannot resume automatically.</small></article>
        <article className={styles.detailCard}><span>Mid runs</span><b>{loaded ? inventory?.counts?.mid_recovery_required ?? "Unavailable" : "Not loaded"}</b><small>Same run, snapshot, report, and approval identities are retained.</small></article>
        <article className={styles.detailCard}><span>Full runs</span><b>{loaded ? inventory?.counts?.full_recovery_required ?? "Unavailable" : "Not loaded"}</b><small>Existing deterministic artifacts are reused rather than duplicated.</small></article>
        <article className={styles.detailCard}><span>Stale threshold</span><b>{loaded ? inventory?.stale_seconds ? `${inventory.stale_seconds} sec` : "Unavailable" : "Not loaded"}</b><small>No automatic continuation is permitted.</small></article>
      </div>
      <div className={styles.filters}>
        <label>Resume actor<input value={actor} onChange={(event) => setActor(event.target.value)} maxLength={120} spellCheck={false} /></label>
        <div />
        <button type="button" onClick={() => void loadRecovery(true)} disabled={loading || !adminToken.trim()}>{loading ? "Working..." : "Refresh assessment reconciliation"}</button>
      </div>
      <p className={styles.helper}>All resumes require an authenticated operator claim. Interrupted Express runs remain manual-review-only and cannot silently start a replacement.</p>
      {targetRunId && loaded && !targetFound ? <div className={styles.nextAction}><b>Target not in assessment recovery inventory</b><p>{targetRunId} may still be active, may be listed under scanner recovery, or may require a fresh reconciliation. Use Refresh assessment reconciliation and inspect the scanner panel below.</p></div> : null}
      {error ? <div className={styles.error}>{error}</div> : null}
      {inventory?.recovery_required?.length ? <div className={styles.alertList}>{inventory.recovery_required.map((item) => {
        const targeted = Boolean(targetRunId && item.run_id === targetRunId);
        return <article
          className={styles.alertCard}
          id={item.run_id ? `assessment-recovery-${item.run_id}` : undefined}
          key={item.run_id}
          aria-current={targeted ? "true" : undefined}
          style={targeted ? {borderColor: "#38bdf8", boxShadow: "0 0 0 2px rgba(56,189,248,.28)"} : undefined}
        >
          <div className={styles.cardHead}>
            <div><span>{item.workflow || item.service_tier || "assessment"}</span><b>{item.run_id || "unknown run"}</b></div>
            <span className={`${styles.pill} ${tone(item.status)}`}>{item.status || "unknown"}</span>
          </div>
          <p>{item.repository || "Repository unavailable"}</p>
          <div className={styles.statRow}><span>Checkpoint</span><b>{item.execution_checkpoint?.current_step || "Unavailable"} · {item.execution_checkpoint?.phase || "unknown"}</b></div>
          <div className={styles.statRow}><span>Scanner</span><b>{item.scan_id || "not bound"}</b></div>
          <div className={styles.statRow}><span>Snapshot</span><b>{item.snapshot_commit_sha ? item.snapshot_commit_sha.slice(0, 12) : "not captured"}</b></div>
          <div className={styles.statRow}><span>Artifacts</span><b>{item.report_id || "no report"} · {item.approval_id || "no approval"}</b></div>
          <div className={styles.statRow}><span>Attempt</span><b>{item.recovery?.attempt ?? 0}</b></div>
          <button type="button" onClick={() => void resume(item.run_id || "")} disabled={loading || !item.recovery?.resume_allowed}>{item.recovery?.resume_allowed ? "Resume same run ID" : "Manual review required"}</button>
        </article>;
      })}</div> : <div className={styles.emptyState}>{inventory ? "No interrupted Express, Mid, or Full runs require recovery." : "Enter the admin token and load recovery to inspect Express, Mid, and Full run state."}</div>}
      {inventory?.operator_action ? <div className={styles.nextAction}><b>Assessment recovery policy</b><p>{inventory.operator_action}</p></div> : null}
    </section>
  );
}
