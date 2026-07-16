"use client";

import {FormEvent, useEffect, useState} from "react";
import AssessmentRecoveryPanel from "../AssessmentRecoveryPanel";
import ScannerRecoveryPanel from "../ScannerRecoveryPanel";
import styles from "../operations.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

export default function RecoveryPage() {
  const [adminToken, setAdminToken] = useState("");
  const [refreshKey, setRefreshKey] = useState("");
  const [targetRunId, setTargetRunId] = useState("");
  const [targetScanId, setTargetScanId] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runId = String(params.get("run_id") || "").trim();
    const scanId = String(params.get("scan_id") || "").trim();
    setTargetRunId(runId.startsWith("midrun_") || runId.startsWith("fullrun_") || runId.startsWith("express") ? runId : "");
    setTargetScanId(scanId.startsWith("scan_") ? scanId : "");
  }, []);

  function load(event: FormEvent) {
    event.preventDefault();
    if (!adminToken.trim() || !API_URL) return;
    setRefreshKey(new Date().toISOString());
  }

  return (
    <main className={styles.shell}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>NICO Phase 3</p>
          <h1>Recovery Control</h1>
          <p className={styles.lead}>Review interrupted Express, Mid, Full, and scanner work. Assessment recovery retains durable run and artifact identities; scanner recovery retains the same durable scan ID. Recovery never starts automatically.</p>
        </div>
        <div className={styles.heroState}><a className={`${styles.pill} ${styles.neutral}`} href="/operations">Back to Operations</a></div>
      </section>

      {targetRunId || targetScanId ? <section className={styles.nextAction} role="status">
        <b>Exact recovery target</b>
        <p>{targetRunId ? `Run ${targetRunId}` : "Run identity not supplied"}{targetScanId ? ` · Scanner ${targetScanId}` : ""}. Enter the operator token and load recovery. NICO will highlight the retained identity and will not create a replacement run.</p>
      </section> : null}

      <section className={styles.securityPanel}>
        <div>
          <h2>Operator authentication</h2>
          <p>The admin token remains only in this page&apos;s React memory. Recovery never starts automatically.</p>
        </div>
        <form className={styles.authForm} onSubmit={load}>
          <label>
            Admin token
            <input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Enter NICO_ADMIN_TOKEN" />
          </label>
          <button type="submit" disabled={!API_URL || !adminToken.trim()}>Load recovery</button>
        </form>
        {!API_URL ? <div className={styles.error}>NEXT_PUBLIC_NICO_API_URL is not configured for this Vercel deployment.</div> : null}
      </section>

      <AssessmentRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetRunId={targetRunId} />
      <ScannerRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetScanId={targetScanId} />
    </main>
  );
}
