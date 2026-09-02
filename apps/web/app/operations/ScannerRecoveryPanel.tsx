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
  locale?: "en" | "es-MX";
};

const CLOSE_REASONS = [
  ["superseded_by_terminal_assessment", "Superseded by terminal assessment", "Sustituido por una evaluación terminada"],
  ["authorization_expired", "Authorization expired", "La autorización venció"],
  ["duplicate_or_test_run", "Duplicate or test run", "Ejecución duplicada o de prueba"],
  ["no_longer_required", "No longer required", "Ya no es necesaria"],
] as const;

function tone(status?: string) {
  const value = String(status || "not_loaded").toLowerCase();
  if (value === "not_loaded") return styles.neutral;
  if (["clear", "complete", "running", "queued"].includes(value)) return styles.good;
  if (["attention_required", "recovery_required", "degraded"].includes(value)) return styles.warn;
  return styles.bad;
}

export default function ScannerRecoveryPanel({apiUrl, adminToken, refreshKey, targetScanId = "", locale = "en"}: Props) {
  const [inventory, setInventory] = useState<RecoveryInventory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actor, setActor] = useState("operator");
  const [closeReason, setCloseReason] = useState("superseded_by_terminal_assessment");
  const spanish = locale === "es-MX";
  const copy = spanish ? {
    requestFailed: "Falló la solicitud de recuperación",
    resumeFailed: "Falló la reanudación del analizador",
    closeFailed: "Falló el cierre de recuperación del analizador",
    eyebrow: "Recuperación después de reinicio",
    title: "Ejecuciones interrumpidas de analizadores",
    notLoaded: "sin cargar",
    required: "Recuperación necesaria",
    requiredNote: "Se requiere revisión del operador antes de reanudar o cerrar el mismo ID.",
    active: "Analizadores activos",
    activeNote: "Los registros recientes en cola o en ejecución no están interrumpidos.",
    threshold: "Umbral de inactividad",
    unavailable: "No disponible",
    thresholdNote: "No se permite una nueva ejecución automática.",
    actor: "Identidad del operador",
    closeReason: "Motivo de cierre",
    working: "Procesando…",
    refresh: "Actualizar conciliación",
    targetActive: "El analizador objetivo sigue activo",
    targetActiveDetail: "recibe actualizaciones actuales y no es elegible para recuperación. No lo reanudes, cierres ni reemplaces.",
    targetMissing: "No se encontró el analizador objetivo",
    targetMissingDetail: "no está en el inventario activo ni de recuperación actual. Actualiza la conciliación para reclasificar registros duraderos inactivos.",
    repositoryMissing: "repositorio no disponible",
    unknownScan: "analizador desconocido",
    unknown: "desconocido",
    run: "Ejecución",
    unbound: "sin vínculo",
    reason: "Motivo",
    interrupted: "ejecución interrumpida",
    attempt: "Intento",
    detected: "Detectado",
    resume: "Reanudar el mismo ID de analizador",
    close: "Cerrar conservando la evidencia",
    empty: "Ninguna ejecución interrumpida de analizador requiere recuperación.",
    emptyBeforeLoad: "Ingresa el token de administración y carga la recuperación para revisar su estado.",
    policy: "Política de recuperación",
    policyDetail: "Revisa cada registro interrumpido; reanuda únicamente el trabajo autorizado o cierra el trabajo obsoleto revisado conservando su evidencia.",
  } : {
    requestFailed: "Recovery request failed",
    resumeFailed: "Scanner resume failed",
    closeFailed: "Scanner recovery close failed",
    eyebrow: "Restart recovery",
    title: "Interrupted scanner runs",
    notLoaded: "not loaded",
    required: "Recovery required",
    requiredNote: "Operator review is required before same-ID resume or close.",
    active: "Active scanners",
    activeNote: "Recently updated queued or running records are not interrupted.",
    threshold: "Stale threshold",
    unavailable: "Unavailable",
    thresholdNote: "No automatic rerun is permitted.",
    actor: "Operator identity",
    closeReason: "Close reason",
    working: "Working...",
    refresh: "Refresh reconciliation",
    targetActive: "Target scanner is still active",
    targetActiveDetail: "is receiving current updates and is not eligible for recovery. Do not resume, close, or replace it.",
    targetMissing: "Target scanner not found",
    targetMissingDetail: "is not in the current active or recovery inventory. Refresh reconciliation to reclassify stale durable records.",
    repositoryMissing: "repository unavailable",
    unknownScan: "unknown scan",
    unknown: "unknown",
    run: "Run",
    unbound: "unbound",
    reason: "Reason",
    interrupted: "interrupted execution",
    attempt: "Attempt",
    detected: "Detected",
    resume: "Resume same scan ID",
    close: "Close and retain evidence",
    empty: "No interrupted scanner runs require recovery.",
    emptyBeforeLoad: "Enter the admin token and load recovery to inspect scanner recovery state.",
    policy: "Recovery policy",
    policyDetail: "Review each interrupted record; resume only authorized work or close reviewed stale work while retaining its evidence.",
  };

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
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `${copy.requestFailed} (${response.status}).`);
      setInventory(payload as RecoveryInventory);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `${copy.requestFailed}.`);
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
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `${copy.resumeFailed} (${response.status}).`);
      await loadRecovery(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `${copy.resumeFailed}.`);
      setLoading(false);
    }
  }

  async function closeRecovery(scanId: string) {
    if (!scanId || !apiUrl || !adminToken.trim() || !actor.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/operations/recovery/scanner/${encodeURIComponent(scanId)}/close`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "X-NICO-Admin-Token": adminToken,
        },
        body: JSON.stringify({actor: actor.trim(), reason_code: closeReason}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || `${copy.closeFailed} (${response.status}).`);
      await loadRecovery(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `${copy.closeFailed}.`);
      setLoading(false);
    }
  }

  useEffect(() => {
    if (refreshKey && adminToken.trim()) void loadRecovery(false);
    // The token is deliberately page-memory state. Re-load only when the parent completes a control-center refresh.
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
        <div><p className={styles.eyebrow}>{copy.eyebrow}</p><h2>{copy.title}</h2></div>
        <span className={`${styles.pill} ${tone(inventory?.status)}`}>{inventory?.status || copy.notLoaded}</span>
      </div>
      <div className={styles.gridThree}>
        <article className={styles.detailCard}><span>{copy.required}</span><b>{loaded ? inventory?.counts?.recovery_required ?? copy.unavailable : copy.notLoaded}</b><small>{copy.requiredNote}</small></article>
        <article className={styles.detailCard}><span>{copy.active}</span><b>{loaded ? inventory?.counts?.active ?? copy.unavailable : copy.notLoaded}</b><small>{copy.activeNote}</small></article>
        <article className={styles.detailCard}><span>{copy.threshold}</span><b>{loaded ? inventory?.stale_seconds ? `${inventory.stale_seconds} sec` : copy.unavailable : copy.notLoaded}</b><small>{copy.thresholdNote}</small></article>
      </div>
      <div className={styles.filters}>
        <label>{copy.actor}<input value={actor} onChange={(event) => setActor(event.target.value)} maxLength={120} spellCheck={false} /></label>
        <label>{copy.closeReason}<select value={closeReason} onChange={(event) => setCloseReason(event.target.value)}>{CLOSE_REASONS.map(([value, en, es]) => <option key={value} value={value}>{spanish ? es : en}</option>)}</select></label>
        <button type="button" onClick={() => void loadRecovery(true)} disabled={loading || !adminToken.trim()}>{loading ? copy.working : copy.refresh}</button>
      </div>
      {targetScanId && loaded && targetActive ? <div className={styles.nextAction}><b>{copy.targetActive}</b><p>{targetScanId} {copy.targetActiveDetail}</p></div> : null}
      {targetScanId && loaded && !targetFound && !targetActive ? <div className={styles.nextAction}><b>{copy.targetMissing}</b><p>{targetScanId} {copy.targetMissingDetail}</p></div> : null}
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
            <div><span>{item.repository || copy.repositoryMissing}</span><b>{item.scan_id || copy.unknownScan}</b></div>
            <span className={`${styles.pill} ${tone(item.status)}`}>{item.status || copy.unknown}</span>
          </div>
          <p>{copy.run}: <code>{item.run_id || copy.unbound}</code></p>
          <div className={styles.statRow}><span>{copy.reason}</span><b>{item.recovery?.reason || copy.interrupted}</b></div>
          <div className={styles.statRow}><span>{copy.attempt}</span><b>{item.recovery?.attempt ?? 0}</b></div>
          <div className={styles.statRow}><span>{copy.detected}</span><b>{item.recovery?.detected_at ? new Date(item.recovery.detected_at).toLocaleString(spanish ? "es-MX" : "en-US") : copy.unavailable}</b></div>
          <button type="button" onClick={() => void resume(item.scan_id || "")} disabled={loading || !item.recovery?.resume_allowed}>{copy.resume}</button>
          <button type="button" onClick={() => void closeRecovery(item.scan_id || "")} disabled={loading || !actor.trim()}>{copy.close}</button>
        </article>;
      })}</div> : <div className={styles.emptyState}>{inventory ? copy.empty : copy.emptyBeforeLoad}</div>}
      {inventory?.operator_action ? <div className={styles.nextAction}><b>{copy.policy}</b><p>{copy.policyDetail}</p></div> : null}
    </section>
  );
}
