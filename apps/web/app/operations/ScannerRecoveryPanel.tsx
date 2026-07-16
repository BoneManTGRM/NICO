"use client";

import {useEffect, useState} from "react";
import styles from "./operations.module.css";

type RecoveryItem = {
  scan_id?: string;
  run_id?: string;
  repository?: string;
  status?: string;
  updated_at?: string;
  tools_requested?: string[];
  recovery?: {
    reason?: string;
    detected_at?: string;
    attempt?: number;
    resume_allowed?: boolean;
  };
};

type RecoveryInventory = {
  status?: string;
  generated_at?: string;
  stale_seconds?: number;
  counts?: {
    recovery_required?: number;
    active?: number;
    total_scanner_records_examined?: number;
  };
  recovery_required?: RecoveryItem[];
  active?: RecoveryItem[];
  operator_action?: string;
};

type Props = {
  apiUrl: string;
  adminToken: string;
  refreshKey: string;
  targetScanId?: string;
};

function tone(status?: string) {
  const value = String(status || "not_loaded").toLowerCase();
  if (value === "not_loaded") return styles.neutral;
  if (["clear", "complete", "running", "queued"].includes(value)) return styles.good;
  if (["attention_required", "recovery_required", "degraded"].includes(value)) return styles.warn;
  return styles.bad;
}

export default function ScannerRecoveryPanel({apiUrl, adminToken, refreshKey, targetScanId = ""}: Props) {
  const [inventory, setInventory] = useState<RecoveryInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actor, setActor] = useState("operator");

  async function loadRecovery(refresh = false) {
    if (!apiUrl || !adminToken.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/operations/recovery?refresh=${refresh ? "true" : "false"}&limit=200`, {
        cache: "no-store",
        headers: {"X-NICO-Admin-Token": adminToken},
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Recovery request failed (${response.status}).`);
      setInventory(payload as RecoveryInventory);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Scanner recovery request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function resume(scanId: string) {
    if (!scanId || !apiUrl || !adminToken.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/operations/recovery/scanner/${encodeURIComponent(scanId)}/resume`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-NICO-Admin-Token": adminToken,
        },
        body: JSON.stringify({actor: actor.trim() || "operator"}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `Scanner resume failed (${response.status}).`);
      await loadRecovery(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Scanner resume failed.");
      setLoading(false);
    }
  }

  useEffect(() => {
    if (refreshKey && adminToken.trim()) void loadRecovery(false);
    // The token is deliberately page-memory state. Re-load only when the parent completes a control-center refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (!inventory || !targetScanId) return;
    window.setTimeout(() => document.getElementById(`scanner-recovery-${targetScanId}`)?.scrollIntoView({behavior: "smooth", block: "center"}), 0);
  }, [inventory, targetScanId]);

  const loaded = inventory !== null;
  const targetFound = Boolean(targetScanId && inventory?.recovery_required?.some((item) => item.scan_id === targetScanId));
  const targetActive = Boolean(targetScanId && inventory?.active?.some((item) => item.scan_id === targetScanId));

  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div><p className={styles.eyebrow}>Restart recovery</p><h2>Interrupted scanner runs</h2></div>
        <span className={`${styles.pill} ${tone(inventory?.status)}`}>{inventory?.status || "not loaded"}</span>
      </div>
      <div className={styles.gridThree}>
        <article className={styles.detailCard}><span>Recovery required</span><b>{loaded ? inventory?.counts?.recovery_required ?? "Unavailable" : "Not loaded"}</b><small>Operator review required before same-ID resume.</small></article>
        <article className={styles.detailCard}><span>Active scanners</span><b>{loaded ? inventory?.counts?.active ?? "Unavailable" : "Not loaded"}</b><small>Recently updated queued or running records are not interrupted.</small></article>
        <article className={styles.detailCard}><span>Stale threshold</span><b>{loaded ? inventory?.stale_seconds ? `${inventory.stale_seconds} sec` : "Unavailable" : "Not loaded"}</b><small>No automatic rerun is permitted.</small></article>
      </div>
      <div className={styles.filters}>
        <label>Resume actor<input value={actor} onChange={(event) => setActor(event.target.value)} maxLength={120} spellCheck={false} /></label>
        <div />
        <button type="button" onClick={() => void loadRecovery(true)} disabled={loading || !adminToken.trim()}>{loading ? "Working..." : "Refresh reconciliation"}</button>
      </div>
      {targetScanId && loaded && targetActive ? <div className={styles.nextAction}><b>Target scanner is still active</b><p>{targetScanId} is receiving current updates and is not eligible for recovery. Do not resume or replace it.</p></div> : null}
      {targetScanId && loaded && !targetFound && !targetActive ? <div className={styles.nextAction}><b>Target scanner not found</b><p>{targetScanId} is not in the current active or recovery inventory. Refresh reconciliation to reclassify stale durable records.</p></div> : null}
      {error ? <div className={styles.error}>{error}</div> : null}
      {inventory?.recovery_required?.length ? <div className={styles.alertList}>{inventory.recovery_required.map((item) => {
        const targeted = Boolean(targetScanId && item.scan_id === targetScanId);
        return <article
          className={styles.alertCard}
          id={item.scan_id ? `scanner-recovery-${item.scan_id}` : undefined}
          key={item.scan_id}
          aria-current={targeted ? "true" : undefined}
          style={targeted ? {borderColor: "#38bdf8", boxShadow: "0 0 0 2px rgba(56,189,248,.28)"} : undefined}
        >
          <div className={styles.cardHead}>
            <div><span>{item.repository || "repository unavailable"}</span><b>{item.scan_id || "unknown scan"}</b></div>
            <span className={`${styles.pill} ${tone(item.status)}`}>{item.status || "unknown"}</span>
          </div>
          <p>Run: <code>{item.run_id || "unbound"}</code></p>
          <div className={styles.statRow}><span>Reason</span><b>{item.recovery?.reason || "interrupted execution"}</b></div>
          <div className={styles.statRow}><span>Attempt</span><b>{item.recovery?.attempt ?? 0}</b></div>
          <div className={styles.statRow}><span>Detected</span><b>{item.recovery?.detected_at ? new Date(item.recovery.detected_at).toLocaleString() : "Unavailable"}</b></div>
          <button type="button" onClick={() => void resume(item.scan_id || "")} disabled={loading || !item.recovery?.resume_allowed}>Resume same scan ID</button>
        </article>;
      })}</div> : <div className={styles.emptyState}>{inventory ? "No interrupted scanner runs require recovery." : "Enter the admin token and load recovery to inspect scanner recovery state."}</div>}
      {inventory?.operator_action ? <div className={styles.nextAction}><b>Recovery policy</b><p>{inventory.operator_action}</p></div> : null}
    </section>
  );
}
