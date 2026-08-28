"use client";

import {FormEvent, useEffect, useState} from "react";
import AssessmentRecoveryPanel from "../AssessmentRecoveryPanel";
import ComprehensiveRecoveryPanel from "../ComprehensiveRecoveryPanel";
import ScannerRecoveryPanel from "../ScannerRecoveryPanel";
import styles from "../operations.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
type RecoveryLocale = "en" | "es-MX";

export default function RecoveryPage() {
  const [adminToken, setAdminToken] = useState("");
  const [refreshKey, setRefreshKey] = useState("");
  const [targetRunId, setTargetRunId] = useState("");
  const [targetScanId, setTargetScanId] = useState("");
  const [locale, setLocale] = useState<RecoveryLocale>("en");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runId = String(params.get("run_id") || "").trim();
    const scanId = String(params.get("scan_id") || "").trim();
    setLocale(String(params.get("lang") || "").trim().toLowerCase() === "es-mx" ? "es-MX" : "en");
    setTargetRunId(
      runId.startsWith("comprun_")
        || runId.startsWith("midrun_")
        || runId.startsWith("fullrun_")
        || runId.startsWith("express")
        ? runId
        : "",
    );
    setTargetScanId(scanId.startsWith("scan_") ? scanId : "");
  }, []);

  const comprehensiveTarget = targetRunId.startsWith("comprun_");
  const spanish = locale === "es-MX";
  const returnPath = spanish ? "/es/assessment" : "/assessment";
  const operationsHref = spanish ? "/operations?lang=es-MX" : "/operations";
  const copy = spanish ? {
    eyebrow: "NICO Fase 3",
    title: "Control de recuperación",
    lead: "Revisa trabajo interrumpido de evaluaciones heredadas y analizadores. La recuperación de una ejecución exacta de NICO Comprehensive también está disponible cuando se proporciona un destino conservado con el formato comprun_*. La recuperación conserva los ID duraderos de ejecución y artefactos; la recuperación de analizadores conserva el mismo ID duradero de análisis. La recuperación nunca inicia automáticamente.",
    back: "Volver a Operaciones",
    exactTarget: "Destino exacto de recuperación",
    run: "Ejecución",
    runMissing: "No se proporcionó el ID de ejecución",
    scanner: "Analizador",
    comprehensiveTarget: "Carga la ejecución conservada de NICO Comprehensive y reanuda explícitamente el mismo ID exacto.",
    legacyTarget: "Ingresa el token del operador y carga la recuperación.",
    preserve: "NICO conservará la identidad retenida y no creará una ejecución de reemplazo.",
    boundary: comprehensiveTarget ? "Límite de autorización de recuperación" : "Autenticación del operador",
    boundaryDetail: comprehensiveTarget
      ? "La recuperación de NICO Comprehensive usa los límites públicos existentes de consulta de estado y continuación para la ejecución exacta. No otorga autoridad de aprobación ni de entrega al cliente, y nunca inicia automáticamente."
      : "El token de administración permanece únicamente en la memoria de React de esta página. La recuperación nunca inicia automáticamente.",
    token: "Token de administración",
    tokenOptional: "(no se requiere para la recuperación de NICO Comprehensive)",
    tokenPlaceholder: "Ingresa NICO_ADMIN_TOKEN",
    load: "Cargar recuperación",
    apiMissing: "NEXT_PUBLIC_NICO_API_URL no está configurada para este despliegue de Vercel.",
  } : {
    eyebrow: "NICO Phase 3",
    title: "Recovery Control",
    lead: "Review interrupted legacy assessment and scanner work. Comprehensive exact-run recovery is also available when a preserved comprun_* target is supplied. Assessment recovery retains durable run and artifact identities; scanner recovery retains the same durable scan ID. Recovery never starts automatically.",
    back: "Back to Operations",
    exactTarget: "Exact recovery target",
    run: "Run",
    runMissing: "Run identity not supplied",
    scanner: "Scanner",
    comprehensiveTarget: "Load the preserved Comprehensive run and explicitly resume the same exact run ID.",
    legacyTarget: "Enter the operator token and load recovery.",
    preserve: "NICO will preserve the retained identity and will not create a replacement run.",
    boundary: comprehensiveTarget ? "Recovery authorization boundary" : "Operator authentication",
    boundaryDetail: comprehensiveTarget
      ? "Comprehensive recovery uses the existing public exact-run status and continuation boundary. It does not create approval or client-delivery authority, and it never starts automatically."
      : "The admin token remains only in this page's React memory. Recovery never starts automatically.",
    token: "Admin token",
    tokenOptional: "(not required for Comprehensive recovery)",
    tokenPlaceholder: "Enter NICO_ADMIN_TOKEN",
    load: "Load recovery",
    apiMissing: "NEXT_PUBLIC_NICO_API_URL is not configured for this Vercel deployment.",
  };

  function load(event: FormEvent) {
    event.preventDefault();
    if (!API_URL || (!comprehensiveTarget && !adminToken.trim())) return;
    setRefreshKey(new Date().toISOString());
  }

  return (
    <main className={styles.shell} lang={spanish ? "es-MX" : undefined} data-recovery-locale={locale}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className={styles.lead}>{copy.lead}</p>
        </div>
        <div className={styles.heroState}><a className={`${styles.pill} ${styles.neutral}`} href={operationsHref}>{copy.back}</a></div>
      </section>

      {targetRunId || targetScanId ? <section className={styles.nextAction} role="status">
        <b>{copy.exactTarget}</b>
        <p>{targetRunId ? `${copy.run} ${targetRunId}` : copy.runMissing}{targetScanId ? ` · ${copy.scanner} ${targetScanId}` : ""}. {comprehensiveTarget ? copy.comprehensiveTarget : copy.legacyTarget} {copy.preserve}</p>
      </section> : null}

      <section className={styles.securityPanel}>
        <div>
          <h2>{copy.boundary}</h2>
          <p>{copy.boundaryDetail}</p>
        </div>
        <form className={styles.authForm} onSubmit={load}>
          <label>
            {copy.token} {comprehensiveTarget ? copy.tokenOptional : ""}
            <input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} placeholder={copy.tokenPlaceholder} disabled={comprehensiveTarget} />
          </label>
          <button type="submit" disabled={!API_URL || (!comprehensiveTarget && !adminToken.trim())}>{copy.load}</button>
        </form>
        {!API_URL ? <div className={styles.error}>{copy.apiMissing}</div> : null}
      </section>

      {comprehensiveTarget ? <ComprehensiveRecoveryPanel
        apiUrl={API_URL}
        locale={locale}
        refreshKey={refreshKey}
        targetRunId={targetRunId}
        returnPath={returnPath}
      /> : <AssessmentRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetRunId={targetRunId} />}
      {!comprehensiveTarget ? <ScannerRecoveryPanel apiUrl={API_URL} adminToken={adminToken} refreshKey={refreshKey} targetScanId={targetScanId} /> : null}
    </main>
  );
}
