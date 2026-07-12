"use client";

import {FormEvent, useState} from "react";
import ScannerRecoveryPanel from "../ScannerRecoveryPanel";
import styles from "../operations.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

export default function ScannerRecoveryPage() {
  const [adminToken, setAdminToken] = useState("");
  const [refreshKey, setRefreshKey] = useState("");

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
          <h1>Scanner Recovery</h1>
          <p className={styles.lead}>Review scanner work interrupted by a backend restart and resume the same durable scan ID without creating duplicate execution.</p>
        </div>
        <div className={styles.heroState}><a className={`${styles.pill} ${styles.neutral}`} href="/operations">Back to Operations</a></div>
      </section>

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

      <ScannerRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} />
    </main>
  );
}
