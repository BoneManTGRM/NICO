"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./AssessmentRecoveryActions.module.css";
import {
  EXPRESS_RECOVERY_STATE_EVENT,
  EXPRESS_RECOVERY_STORAGE_KEY,
} from "./AssessmentExpressRecoveryGuard";

type RecoveryState = {
  status?: string;
  tier?: string;
  run_id?: string;
  scan_id?: string;
  current_stage?: string;
  progress_percent?: number;
  consecutive_failures?: number;
  http_status?: number;
  code?: string;
  message?: string;
  recovery_required?: boolean;
  recovery_path?: string;
  persistence_recorded?: boolean;
  persistence_durable?: boolean;
  persistence_adapter?: string;
};

function storedState(): RecoveryState | null {
  try {
    const value = window.sessionStorage.getItem(EXPRESS_RECOVERY_STORAGE_KEY);
    if (!value) return null;
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || parsed.status === "healthy") return null;
    return parsed as RecoveryState;
  } catch {
    return null;
  }
}

export default function AssessmentExpressRecoveryActions() {
  const [state, setState] = useState<RecoveryState | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setState(storedState());
    const update = (event: Event) => {
      const detail = (event as CustomEvent<RecoveryState>).detail || {};
      if (detail.status === "healthy") {
        setState(null);
        return;
      }
      setState(detail);
      setCopied(false);
    };
    window.addEventListener(EXPRESS_RECOVERY_STATE_EVENT, update);
    return () => window.removeEventListener(EXPRESS_RECOVERY_STATE_EVENT, update);
  }, []);

  const recoveryUrl = useMemo(() => {
    const path = state?.recovery_path || "/operations/recovery";
    const origin = typeof window === "undefined" ? "https://app.nicoaudit.com" : window.location.origin;
    const url = new URL(path, origin);
    if (state?.run_id) url.searchParams.set("run_id", state.run_id);
    if (state?.scan_id) url.searchParams.set("scan_id", state.scan_id);
    url.searchParams.set("tier", "express");
    return `${url.pathname}${url.search}`;
  }, [state]);

  if (!state || state.status === "healthy") return null;

  async function copyDiagnostics() {
    if (!state) return;
    await navigator.clipboard.writeText(JSON.stringify({express_run_recovery: state}, null, 2));
    setCopied(true);
  }

  return (
    <aside className={`${styles.card} ${styles.critical}`} role="alert" aria-live="assertive">
      <div className={styles.header}>
        <div>
          <span className={styles.eyebrow}>EXPRESS RUN CONTROL</span>
          <h2>Exact-run recovery required</h2>
        </div>
        <span className={styles.badge}>RECOVERY</span>
      </div>
      <p>{state.message || "The Express run can no longer be verified through its exact-run status route."}</p>
      <dl className={styles.details}>
        <div><dt>Run</dt><dd>{state.run_id || "Unknown"}</dd></div>
        <div><dt>Last stage</dt><dd>{state.current_stage || "Unknown"} · {Number.isFinite(Number(state.progress_percent)) ? `${Math.round(Number(state.progress_percent))}%` : "progress unavailable"}</dd></div>
        <div><dt>Status evidence</dt><dd>{state.code || "express_exact_run_recovery_required"}{state.http_status ? ` · HTTP ${state.http_status}` : ""}</dd></div>
        <div><dt>Durable record</dt><dd>{state.persistence_durable === true ? `Verified · ${state.persistence_adapter || "durable"}` : `Not durable · ${state.persistence_adapter || "unknown"}`}</dd></div>
        <div><dt>Bounded checks</dt><dd>{state.consecutive_failures ?? "Unknown"}</dd></div>
      </dl>
      <div className={styles.actions}>
        <a href={recoveryUrl}>Open exact-run Recovery</a>
        <a href="/operations">Open Operations</a>
        <button type="button" onClick={() => void copyDiagnostics()}>{copied ? "Diagnostics copied" : "Copy diagnostics"}</button>
      </div>
      <p className={styles.safety}><b>Do not start another Express assessment yet.</b> The original run identity remains preserved. Recovery must reconcile or explicitly close it before a replacement run is allowed.</p>
    </aside>
  );
}
