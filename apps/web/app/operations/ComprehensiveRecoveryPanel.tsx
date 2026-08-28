"use client";

import {useEffect, useMemo, useState} from "react";
import {copyFor} from "../assessment/assessmentCopy";
import styles from "./operations.module.css";

type RecoveryLocale = "en" | "es-MX";

type ComprehensiveProjection = {
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  status?: string;
  current_stage?: string;
  progress_percent?: number;
  terminal?: boolean;
  human_review_required?: boolean;
  client_delivery_allowed?: boolean;
  record?: {
    current_stage?: string;
    stage_results?: Record<string, Record<string, unknown>>;
  };
};

type Props = {
  apiUrl: string;
  locale?: RecoveryLocale;
  refreshKey: string;
  targetRunId: string;
  returnPath?: string;
};

function detailMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return fallback;
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const nested = detail as Record<string, unknown>;
    const message = String(nested.message || nested.code || "").trim();
    if (message) return message;
  }
  return String(record.message || record.error || fallback);
}

function runStage(run: ComprehensiveProjection | null): string {
  return String(run?.current_stage || run?.record?.current_stage || "unknown").trim();
}

function failureReason(run: ComprehensiveProjection | null, unavailable: string): string {
  if (!run?.record?.stage_results) return unavailable;
  const stage = runStage(run);
  const result = run.record.stage_results[stage];
  if (!result || typeof result !== "object") return unavailable;
  return String(
    result.technical_reason
      || result.reason
      || result.error
      || result.message
      || unavailable,
  );
}

function recoverable(run: ComprehensiveProjection | null): boolean {
  if (!run?.terminal) return false;
  return ["blocked", "failed", "error", "interrupted"].includes(
    String(run.status || "").trim().toLowerCase(),
  );
}

const SPANISH_STATUS_LABELS: Record<string, string> = {
  blocked: "Bloqueada",
  failed: "Fallida",
  error: "Error",
  interrupted: "Interrumpida",
  rejected: "Rechazada",
  complete: "Completa",
  completed: "Completada",
  verified: "Verificada",
  running: "En ejecución",
  queued: "En cola",
  pending: "Pendiente",
  starting: "Iniciando",
  review_required: "Revisión requerida",
};

function stageDisplayLabel(stageId: string, locale: RecoveryLocale): string {
  const canonical = String(stageId || "").trim();
  const labels = copyFor(locale).stageLabels as Record<string, string>;
  return labels[canonical] || canonical.replaceAll("_", " ");
}

function statusDisplayLabel(statusId: string, locale: RecoveryLocale, notLoaded: string): string {
  const canonical = String(statusId || "").trim();
  if (!canonical) return notLoaded;
  return locale === "es-MX"
    ? SPANISH_STATUS_LABELS[canonical.toLowerCase()] || canonical
    : canonical;
}

export default function ComprehensiveRecoveryPanel({
  apiUrl,
  locale = "en",
  refreshKey,
  targetRunId,
  returnPath = "/assessment",
}: Props) {
  const [run, setRun] = useState<ComprehensiveProjection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const spanish = locale === "es-MX";
  const copy = spanish ? {
    unavailable: "No disponible",
    lookupFailed: "Falló la consulta de recuperación de NICO Comprehensive",
    lookupIdentityMismatch: "La consulta de recuperación devolvió el ID de otra ejecución de NICO Comprehensive.",
    recoveryFailed: "Falló la recuperación de NICO Comprehensive",
    recoveryIdentityMismatch: "La recuperación de NICO Comprehensive cambió el ID exacto de ejecución.",
    remainedBlockedPrefix: "La ejecución exacta permaneció bloqueada en",
    remainedBlockedSuffix: "La evidencia conservada no se convirtió en un resultado aprobado.",
    eyebrow: "Recuperación de NICO Comprehensive",
    heading: "Reanudar la ejecución exacta conservada de NICO Comprehensive",
    notLoaded: "Sin cargar",
    exactIdentity: "ID exacto de ejecución",
    exactIdentityDetail: "Este control nunca crea una ejecución de reemplazo. Vuelve a ingresar al mismo límite público de continuación de la ejecución exacta que usa el espacio de evaluación y conserva el registro duradero.",
    currentStage: "Etapa actual",
    stageAuthority: "La etapa que falló permanece como fuente autoritativa hasta que la recuperación tenga éxito.",
    progress: "Progreso",
    progressIntegrity: "La recuperación no fabrica trabajo completado.",
    repository: "Repositorio",
    exactCommit: "Commit exacto",
    exactCommitMissing: "Commit exacto sin cargar",
    clientDelivery: "Entrega al cliente",
    allowed: "Autorizada",
    blocked: "Bloqueada",
    humanReview: "La revisión humana sigue siendo obligatoria.",
    preservedReason: "Motivo técnico conservado",
    working: "Procesando…",
    reload: "Volver a cargar el estado de la ejecución exacta",
    resume: "Reanudar el mismo ID de ejecución de NICO Comprehensive",
    helper: "No se requiere un token de operador para esta recuperación acotada de NICO Comprehensive porque utiliza las rutas públicas existentes de estado y continuación de la ejecución exacta. La revisión humana y la entrega al cliente permanecen cerradas de forma segura. La primera continuación de recuperación está limitada a una etapa; un fallo terminal repetido permanece bloqueado y visible.",
  } : {
    unavailable: "Unavailable",
    lookupFailed: "Comprehensive recovery lookup failed",
    lookupIdentityMismatch: "The recovery lookup returned a different Comprehensive run identity.",
    recoveryFailed: "Comprehensive recovery failed",
    recoveryIdentityMismatch: "Comprehensive recovery changed the exact run identity.",
    remainedBlockedPrefix: "The exact run remained blocked at",
    remainedBlockedSuffix: "Preserved evidence was not converted into a passing result.",
    eyebrow: "Comprehensive recovery",
    heading: "Resume the preserved exact Comprehensive run",
    notLoaded: "not loaded",
    exactIdentity: "Exact run identity",
    exactIdentityDetail: "This control never creates a replacement run. It re-enters the same public exact-run continuation boundary used by the assessment workspace and preserves the durable record.",
    currentStage: "Current stage",
    stageAuthority: "The failed stage remains authoritative until recovery succeeds.",
    progress: "Progress",
    progressIntegrity: "Recovery does not fabricate completed work.",
    repository: "Repository",
    exactCommit: "Exact commit",
    exactCommitMissing: "Exact commit not loaded",
    clientDelivery: "Client delivery",
    allowed: "Allowed",
    blocked: "Blocked",
    humanReview: "Human review remains required.",
    preservedReason: "Preserved failure reason",
    working: "Working...",
    reload: "Reload exact run state",
    resume: "Resume same Comprehensive run ID",
    helper: "No operator token is required for this bounded Comprehensive recovery because it uses the existing public exact-run status and continuation routes. Human review and client delivery remain fail closed. The first recovery continuation is limited to one stage; a repeated terminal failure remains blocked and visible.",
  };
  const stage = useMemo(() => runStage(run), [run]);
  const reason = useMemo(() => failureReason(run, copy.unavailable), [run, copy.unavailable]);

  async function loadExactRun(): Promise<ComprehensiveProjection | null> {
    if (!apiUrl || !targetRunId) return null;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}`,
        {
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "Cache-Control": "no-store",
          },
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(detailMessage(payload, `${copy.lookupFailed} (${response.status}).`));
      }
      const exact = payload as ComprehensiveProjection;
      if (String(exact.run_id || "") !== targetRunId) {
        throw new Error(copy.lookupIdentityMismatch);
      }
      setRun(exact);
      return exact;
    } catch (requestError) {
      setRun(null);
      setError(requestError instanceof Error ? requestError.message : `${copy.lookupFailed}.`);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function resumeExactRun() {
    if (!apiUrl || !targetRunId || !recoverable(run)) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}/continue`,
        {
          method: "POST",
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
          },
          body: JSON.stringify({max_stages: 1}),
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(detailMessage(payload, `${copy.recoveryFailed} (${response.status}).`));
      }
      const recovered = payload as ComprehensiveProjection;
      if (String(recovered.run_id || "") !== targetRunId) {
        throw new Error(copy.recoveryIdentityMismatch);
      }
      setRun(recovered);
      if (
        recovered.terminal === true
        && ["blocked", "failed", "error", "interrupted"].includes(
          String(recovered.status || "").trim().toLowerCase(),
        )
      ) {
        throw new Error(
          `${copy.remainedBlockedPrefix} ${stageDisplayLabel(runStage(recovered), locale)}. ${copy.remainedBlockedSuffix}`,
        );
      }

      const target = new URL(returnPath, window.location.origin);
      target.searchParams.set("tier", "comprehensive");
      target.searchParams.set("run_id", targetRunId);
      window.location.assign(`${target.pathname}${target.search}${target.hash}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `${copy.recoveryFailed}.`);
      setLoading(false);
    }
  }

  useEffect(() => {
    if (refreshKey && targetRunId) void loadExactRun();
  }, [refreshKey]);

  return (
    <section className={styles.panel} data-comprehensive-recovery="true" data-recovery-locale={locale} lang={spanish ? "es-MX" : undefined}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>{copy.eyebrow}</p>
          <h2>{copy.heading}</h2>
        </div>
        <span
          className={`${styles.pill} ${recoverable(run) ? styles.warn : run ? styles.good : styles.neutral}`}
          data-status-id={run?.status || "not_loaded"}
          title={run?.status || "not_loaded"}
        >
          {statusDisplayLabel(run?.status || "", locale, copy.notLoaded)}
        </span>
      </div>

      <div className={styles.nextAction}>
        <b>{copy.exactIdentity}</b>
        <p><code title={targetRunId}>{targetRunId}</code>. {copy.exactIdentityDetail}</p>
      </div>

      <div className={styles.gridFour}>
        <article className={styles.detailCard}><span>{copy.currentStage}</span><b data-stage-id={run ? stage : "not_loaded"} title={run ? stage : "not_loaded"}>{run ? stageDisplayLabel(stage, locale) : copy.notLoaded}</b><small>{copy.stageAuthority}</small></article>
        <article className={styles.detailCard}><span>{copy.progress}</span><b>{run && Number.isFinite(Number(run.progress_percent)) ? `${Number(run.progress_percent).toFixed(2)}%` : copy.notLoaded}</b><small>{copy.progressIntegrity}</small></article>
        <article className={styles.detailCard}><span>{copy.repository}</span><b>{run?.repository || copy.notLoaded}</b><small>{run?.commit_sha ? `${copy.exactCommit} ${run.commit_sha.slice(0, 12)}` : copy.exactCommitMissing}</small></article>
        <article className={styles.detailCard}><span>{copy.clientDelivery}</span><b data-delivery-state={run?.client_delivery_allowed === true ? "allowed" : "blocked"}>{run?.client_delivery_allowed === true ? copy.allowed : copy.blocked}</b><small>{copy.humanReview}</small></article>
      </div>

      {run ? <div className={styles.nextAction}>
        <b>{copy.preservedReason}</b>
        <p>{reason}</p>
      </div> : null}

      {error ? <div className={styles.error}>{error}</div> : null}

      <div className={styles.filters}>
        <button type="button" onClick={() => void loadExactRun()} disabled={loading}>
          {loading ? copy.working : copy.reload}
        </button>
        <div />
        <button type="button" onClick={() => void resumeExactRun()} disabled={loading || !recoverable(run)}>
          {copy.resume}
        </button>
      </div>

      <p className={styles.helper}>{copy.helper}</p>
    </section>
  );
}
