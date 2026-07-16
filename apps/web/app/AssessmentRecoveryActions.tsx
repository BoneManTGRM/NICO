"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./AssessmentRecoveryActions.module.css";

const MID_RECOVERY_STATE_EVENT = "nico:mid-recovery-state";
const MID_FORCE_LIVE_RETRY_EVENT = "nico:mid-live-status-retry";

type RecoveryState = {
  status?: "healthy" | "temporarily_unreachable" | "recovery_required" | "deployment_mismatch";
  run_id?: string;
  scan_id?: string;
  scanner_status?: string;
  active_tool?: string;
  heartbeat_at?: string;
  current_stage?: string;
  progress_percent?: number;
  recovery_required?: boolean;
  recovery_path?: string;
  last_success_at?: string;
  next_retry_at?: string;
  consecutive_failures?: number;
  http_status?: number;
  code?: string;
  message?: string;
};

function storedState(): RecoveryState | null {
  try {
    const value = window.sessionStorage.getItem("nico.mid.recovery_state");
    if (!value) return null;
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || parsed.status === "healthy") return null;
    return parsed as RecoveryState;
  } catch {
    return null;
  }
}

function timeLabel(value?: string) {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

export default function AssessmentRecoveryActions() {
  const [state, setState] = useState<RecoveryState | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setState(storedState());
    const update = (event: Event) => {
      const detail = (event as CustomEvent<RecoveryState>).detail || {};
      if (detail.status === "healthy") {
        setState(null);
        try {
          window.sessionStorage.removeItem("nico.mid.recovery_state");
        } catch {
          // The event still clears the visible state.
        }
        return;
      }
      setState(detail);
      setCopied(false);
    };
    window.addEventListener(MID_RECOVERY_STATE_EVENT, update);
    return () => window.removeEventListener(MID_RECOVERY_STATE_EVENT, update);
  }, []);

  const recoveryUrl = useMemo(() => {
    const path = state?.recovery_path || "/operations/recovery";
    const url = new URL(path, typeof window === "undefined" ? "https://app.nicoaudit.com" : window.location.origin);
    if (state?.run_id) url.searchParams.set("run_id", state.run_id);
    if (state?.scan_id) url.searchParams.set("scan_id", state.scan_id);
    return `${url.pathname}${url.search}`;
  }, [state]);

  if (!state || state.status === "healthy") return null;

  const deploymentMismatch = state.status === "deployment_mismatch";
  const recoveryRequired = state.status === "recovery_required" || state.recovery_required;
  const title = recoveryRequired
    ? "Exact-run recovery required"
    : deploymentMismatch
      ? "Backend deployment contract mismatch"
      : "Mid live status needs attention";
  const summary = recoveryRequired
    ? "The scanner stopped updating. NICO preserved the run and requires an authenticated same-scan recovery action."
    : deploymentMismatch
      ? "The web app cannot reach the live-status endpoint expected from the Railway backend. Verify the backend deployment before starting another assessment."
      : "The exact run is preserved. NICO is applying bounded status backoff instead of flooding the backend or creating a duplicate scanner.";

  function retry() {
    if (!state?.run_id) return;
    window.dispatchEvent(new CustomEvent(MID_FORCE_LIVE_RETRY_EVENT, {detail: {run_id: state.run_id}}));
    setState((current) => current ? {...current, next_retry_at: new Date().toISOString()} : current);
  }

  async function copyDiagnostics() {
    if (!state) return;
    await navigator.clipboard.writeText(JSON.stringify(state, null, 2));
    setCopied(true);
  }

  return (
    <aside className={`${styles.card} ${recoveryRequired || deploymentMismatch ? styles.critical : styles.warning}`} role="alert" aria-live="assertive">
      <div className={styles.header}>
        <div>
          <span className={styles.eyebrow}>MID RUN CONTROL</span>
          <h2>{title}</h2>
        </div>
        <span className={styles.badge}>{recoveryRequired ? "RECOVERY" : deploymentMismatch ? "DEPLOYMENT" : "STATUS"}</span>
      </div>
      <p>{summary}</p>
      <dl className={styles.details}>
        <div><dt>Run</dt><dd>{state.run_id || "Unknown"}</dd></div>
        <div><dt>Scan</dt><dd>{state.scan_id || "Not yet returned"}</dd></div>
        <div><dt>Last stage</dt><dd>{state.current_stage || "Unknown"} · {Number.isFinite(Number(state.progress_percent)) ? `${Math.round(Number(state.progress_percent))}%` : "progress unavailable"}</dd></div>
        <div><dt>Scanner</dt><dd>{state.scanner_status || "Unknown"}{state.active_tool ? ` · ${state.active_tool}` : ""}</dd></div>
        <div><dt>Last heartbeat</dt><dd>{timeLabel(state.heartbeat_at)}</dd></div>
        <div><dt>Last successful status</dt><dd>{timeLabel(state.last_success_at)}</dd></div>
        <div><dt>Bounded code</dt><dd>{state.code || "transport_unavailable"}{state.http_status ? ` · HTTP ${state.http_status}` : ""}</dd></div>
      </dl>
      <div className={styles.actions}>
        {!recoveryRequired ? <button type="button" onClick={retry}>Retry live status now</button> : null}
        <a href={recoveryUrl}>{recoveryRequired ? "Recover exact scanner" : "Inspect Recovery Control"}</a>
        <a href="/operations">Open Operations</a>
        <button type="button" onClick={() => void copyDiagnostics()}>{copied ? "Diagnostics copied" : "Copy diagnostics"}</button>
      </div>
      <p className={styles.safety}><b>Do not start another Mid assessment.</b> Server-side duplicate prevention keeps the same repository and scope bound to the existing run until it completes, becomes terminal, or is recovered.</p>
    </aside>
  );
}
