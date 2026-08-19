"use client";

import {FormEvent, useEffect, useState} from "react";
import AssessmentRecoveryPanel from "../AssessmentRecoveryPanel";
import ComprehensiveRecoveryPanel from "../ComprehensiveRecoveryPanel";
import ScannerRecoveryPanel from "../ScannerRecoveryPanel";
import styles from "../operations.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

export default function RecoveryPage() {
  const [adminToken, setAdminToken] = useState("");
  const [refreshKey, setRefreshKey] = useState("");
  const [targetRunId, setTargetRunId] = useState("");
  const [targetScanId, setTargetScanId] = useState("");
  const [returnPath, setReturnPath] = useState("/assessment");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runId = String(params.get("run_id") || "").trim();
    const scanId = String(params.get("scan_id") || "").trim();
    setTargetRunId(
      runId.startsWith("comprun_")
        || runId.startsWith("midrun_")
        || runId.startsWith("fullrun_")
        || runId.startsWith("express")
        ? runId
        : "",
    );
    setTargetScanId(scanId.startsWith("scan_") ? scanId : "");

    try {
      const referrer = document.referrer ? new URL(document.referrer) : null;
      if (
        referrer?.origin === window.location.origin
        && referrer.pathname.startsWith("/es/assessment")
      ) {
        setReturnPath("/es/assessment");
      }
    } catch {
      setReturnPath("/assessment");
    }
  }, []);

  const comprehensiveTarget = targetRunId.startsWith("comprun_");

  function load(event: FormEvent) {
    event.preventDefault();
    if (!API_URL || (!comprehensiveTarget && !adminToken.trim())) return;
    setRefreshKey(new Date().toISOString());
  }

  return (
    <main className={styles.shell}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>NICO Phase 3</p>
          <h1>Recovery Control</h1>
          <p className={styles.lead}>Review interrupted Express, Mid, Full, and scanner work. Comprehensive exact-run recovery is also available when a preserved <code>comprun_*</code> target is supplied. Assessment recovery retains durable run and artifact identities; scanner recovery retains the same durable scan ID. Recovery never starts automatically.</p>
        </div>
        <div className={styles.heroState}><a className={`${styles.pill} ${styles.neutral}`} href="/operations">Back to Operations</a></div>
      </section>

      {targetRunId || targetScanId ? <section className={styles.nextAction} role="status">
        <b>Exact recovery target</b>
        <p>{targetRunId ? `Run ${targetRunId}` : "Run identity not supplied"}{targetScanId ? ` · Scanner ${targetScanId}` : ""}. {comprehensiveTarget ? "Load the preserved Comprehensive run and explicitly resume the same exact run ID." : "Enter the operator token and load recovery."} NICO will preserve the retained identity and will not create a replacement run.</p>
      </section> : null}

      <section className={styles.securityPanel}>
        <div>
          <h2>{comprehensiveTarget ? "Recovery authorization boundary" : "Operator authentication"}</h2>
          <p>{comprehensiveTarget ? "Comprehensive recovery uses the existing public exact-run status and continuation boundary. It does not create approval or client-delivery authority, and it never starts automatically." : "The admin token remains only in this page&apos;s React memory. Recovery never starts automatically."}</p>
        </div>
        <form className={styles.authForm} onSubmit={load}>
          <label>
            Admin token {comprehensiveTarget ? "(not required for Comprehensive recovery)" : ""}
            <input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Enter NICO_ADMIN_TOKEN" disabled={comprehensiveTarget} />
          </label>
          <button type="submit" disabled={!API_URL || (!comprehensiveTarget && !adminToken.trim())}>Load recovery</button>
        </form>
        {!API_URL ? <div className={styles.error}>NEXT_PUBLIC_NICO_API_URL is not configured for this Vercel deployment.</div> : null}
      </section>

      {comprehensiveTarget ? <ComprehensiveRecoveryPanel
        apiUrl={API_URL}
        refreshKey={refreshKey}
        targetRunId={targetRunId}
        returnPath={returnPath}
      /> : <AssessmentRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetRunId={targetRunId} />}
      <ScannerRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetScanId={targetScanId} />
    </main>
  );
}
