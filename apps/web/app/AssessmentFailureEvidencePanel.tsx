"use client";

import {useEffect, useMemo, useState} from "react";
import {
  ASSESSMENT_FAILURE_EVENT,
  type AssessmentFailureEvidence,
} from "./AssessmentApiTransportBridge";
import {copyFor} from "./assessment/assessmentCopy";
import {UI_LOCALE_CHANGE_EVENT} from "./assessment/assessmentLocale";
import {localizeExactSpanishText} from "./assessment/AssessmentSpanishLocalization";

const TERMINAL_FAILURES = new Set(["failed", "blocked", "error", "interrupted", "rejected"]);

function isFailureEvidence(value: unknown): value is AssessmentFailureEvidence {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.http_status === "number"
    && typeof record.route === "string"
    && typeof record.code === "string"
    && typeof record.message === "string"
    && Array.isArray(record.progress);
}

function tone(status: string): string {
  const normalized = status.toLowerCase();
  if (TERMINAL_FAILURES.has(normalized)) return "red";
  if (["complete", "completed", "verified"].includes(normalized)) return "green";
  if (["running", "queued", "pending", "starting"].includes(normalized)) return "yellow";
  return "gray";
}

function normalizedLabel(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function spanishLocation(): boolean {
  const path = window.location.pathname.toLowerCase();
  const queryLocale = new URLSearchParams(window.location.search).get("lang")?.toLowerCase();
  return path === "/es"
    || path.startsWith("/es/")
    || path === "/es-mx"
    || path.startsWith("/es-mx/")
    || queryLocale === "es-mx"
    || queryLocale === "es"
    || document.documentElement.lang.toLowerCase().startsWith("es");
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
};

function stageDisplayLabel(stageId: string, spanish: boolean): string {
  const canonical = String(stageId || "").trim();
  if (!canonical) return spanish ? "no devuelta" : "not returned";
  const labels = copyFor(spanish ? "es-MX" : "en").stageLabels as Record<string, string>;
  return labels[canonical] || (spanish ? copyFor("es-MX").unknownStage : canonical.replaceAll("_", " "));
}

function statusDisplayLabel(statusId: string, spanish: boolean): string {
  const canonical = String(statusId || "").trim();
  if (!spanish) return canonical;
  return SPANISH_STATUS_LABELS[canonical.toLowerCase()] || copyFor("es-MX").unknownStatus;
}

function authoredFailureMessage(
  value: string,
  spanish: boolean,
  fallback: string,
): string {
  const source = String(value || "").replace(/\s+/g, " ").trim();
  if (!source) return fallback;
  if (!spanish) return source;
  // Canonical diagnostic prose stays in API evidence. The visible es-MX surface
  // renders only whole-message allowlisted phrases; unknown English, mixed-language
  // output or stack detail is replaced by safe Spanish copy while stable codes,
  // stages and routes stay shown.
  return localizeExactSpanishText(source) || fallback;
}

function reconcileFailureWorkspace(spanish: boolean) {
  const main = document.querySelector<HTMLElement>('main[data-workspace="assessment"]');
  if (!main) return;
  main.dataset.assessmentTerminalFailure = "true";

  const state = main.querySelector<HTMLElement>('section[data-assessment-run-state="true"]');
  if (!state) return;
  state.dataset.assessmentFailureReconciled = "true";

  const header = state.querySelector<HTMLElement>(".section-head");
  if (header) header.hidden = true;

  const reportActions = state.querySelector<HTMLElement>('[data-assessment-report-actions="true"]');
  if (reportActions) reportActions.hidden = true;

  const cardCopy = spanish ? {
    packageLabels: ["paquete de evaluación", "informe"],
    reviewLabels: ["revisión interna", "revisión humana", "revisión experta"],
    packageValue: "Bloqueado durante la generación del informe final",
    reviewValue: "No alcanzada",
  } : {
    packageLabels: ["assessment package", "report"],
    reviewLabels: ["internal review", "human review", "expert review"],
    packageValue: "Blocked during final report generation",
    reviewValue: "Not reached",
  };

  const articles = Array.from(state.querySelectorAll<HTMLElement>("article"));
  const updateCard = (labels: string[], value: string) => {
    const card = articles.find((article) => labels.includes(normalizedLabel(article.querySelector("b")?.textContent)));
    const target = card?.querySelector<HTMLElement>("span");
    if (target && target.textContent !== value) target.textContent = value;
  };
  updateCard(cardCopy.packageLabels, cardCopy.packageValue);
  updateCard(cardCopy.reviewLabels, cardCopy.reviewValue);
}

function clearFailureWorkspace() {
  const main = document.querySelector<HTMLElement>('main[data-workspace="assessment"]');
  if (!main) return;
  delete main.dataset.assessmentTerminalFailure;
  const state = main.querySelector<HTMLElement>('section[data-assessment-run-state="true"]');
  if (!state) return;
  delete state.dataset.assessmentFailureReconciled;
  const header = state.querySelector<HTMLElement>(".section-head");
  if (header) header.hidden = false;
  const reportActions = state.querySelector<HTMLElement>('[data-assessment-report-actions="true"]');
  if (reportActions) reportActions.hidden = false;
}

export default function AssessmentFailureEvidencePanel() {
  const [failure, setFailure] = useState<AssessmentFailureEvidence | null>(null);
  const [spanish, setSpanish] = useState(false);

  useEffect(() => {
    const assessmentRoute = window.location.pathname.startsWith("/assessment")
      || window.location.pathname.startsWith("/es/assessment")
      || window.location.pathname === "/es-mx"
      || window.location.pathname.startsWith("/es-mx/");
    if (!assessmentRoute) return;
    const synchronizeLocale = () => setSpanish(spanishLocation());
    synchronizeLocale();
    window.addEventListener("popstate", synchronizeLocale);
    window.addEventListener("pageshow", synchronizeLocale);
    window.addEventListener(UI_LOCALE_CHANGE_EVENT, synchronizeLocale);

    const handleFailure = (event: Event) => {
      const detail = (event as CustomEvent<AssessmentFailureEvidence | null>).detail;
      const next = isFailureEvidence(detail) ? detail : null;
      setFailure(next);
      if (next) document.body.dataset.nicoTerminalFailure = "true";
      else delete document.body.dataset.nicoTerminalFailure;
    };
    window.addEventListener(ASSESSMENT_FAILURE_EVENT, handleFailure);
    return () => {
      window.removeEventListener(ASSESSMENT_FAILURE_EVENT, handleFailure);
      window.removeEventListener("popstate", synchronizeLocale);
      window.removeEventListener("pageshow", synchronizeLocale);
      window.removeEventListener(UI_LOCALE_CHANGE_EVENT, synchronizeLocale);
      delete document.body.dataset.nicoTerminalFailure;
      clearFailureWorkspace();
    };
  }, []);

  useEffect(() => {
    if (!failure) {
      clearFailureWorkspace();
      return;
    }
    const apply = () => reconcileFailureWorkspace(spanish);
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    return () => {
      observer.disconnect();
      clearFailureWorkspace();
    };
  }, [failure, spanish]);

  const failedStage = useMemo(
    () => failure?.progress.find((item) => TERMINAL_FAILURES.has(item.status.toLowerCase())) || null,
    [failure],
  );
  const stageRows = useMemo(() => {
    if (!failure) return [];
    const seen = new Set<string>();
    return failure.progress.filter((item) => {
      const key = [
        normalizedLabel(item.step),
        normalizedLabel(item.status),
        normalizedLabel(item.message),
      ].join("|");
      if (seen.has(key)) return false;
      seen.add(key);
      const duplicatesPrimaryDiagnostic = TERMINAL_FAILURES.has(item.status.toLowerCase())
        && normalizedLabel(item.message) === normalizedLabel(failure.message)
        && (!failedStage || normalizedLabel(item.step) === normalizedLabel(failedStage.step));
      return !duplicatesPrimaryDiagnostic;
    });
  }, [failure, failedStage]);

  if (!failure) return null;

  const copy = spanish ? {
    eyebrow: "EVIDENCIA DEL FALLO",
    title: "La evaluación se detuvo",
    summary: "El análisis completado y la identidad exacta de la ejecución permanecen preservados, pero el paquete final no pudo publicarse.",
    blocked: "BLOQUEADA",
    failedStage: "Etapa que falló",
    http: "Estado HTTP original",
    route: "Ruta canónica",
    type: "Tipo de evaluación",
    run: "Identidad de ejecución",
    code: "Código diagnóstico",
    message: "Motivo técnico",
    workerModel: "Modelo del proceso",
    workerExit: "Código de salida del proceso",
    workerSignal: "Señal de salida",
    workerErrorType: "Tipo de error del proceso",
    workerFailureClass: "Clase de fallo",
    workerBootstrap: "Arranque del renderizador",
    missing: "no devuelto",
    details: "Ver detalles técnicos",
    stages: "Ver evidencia acotada de etapas",
    noSteps: "El backend no devolvió evidencia acotada de la etapa que falló.",
    boundary: "Esta ejecución sigue bloqueada y no está lista para el cliente. La evidencia preservada puede revisarse sin convertir el fallo en un resultado aprobado.",
    recovery: "Abrir esta ejecución en Recuperación",
    technicalReasonFallback: "No se recibió una explicación localizada. Consulta el código diagnóstico, la etapa y la ruta canónica conservados.",
    stageReasonFallback: "La etapa conservó un resultado técnico sin explicación localizada. Consulta sus identificadores y la evidencia acotada.",
  } : {
    eyebrow: "ASSESSMENT FAILURE",
    title: "The assessment stopped",
    summary: "Completed analysis and the exact run identity remain preserved, but the final assessment package could not be published.",
    blocked: "BLOCKED",
    failedStage: "Failed stage",
    http: "Original HTTP status",
    route: "Canonical route",
    type: "Assessment type",
    run: "Run identity",
    code: "Diagnostic code",
    message: "Technical reason",
    workerModel: "Worker model",
    workerExit: "Worker exit code",
    workerSignal: "Worker exit signal",
    workerErrorType: "Worker error type",
    workerFailureClass: "Worker failure class",
    workerBootstrap: "Renderer bootstrap",
    missing: "not returned",
    details: "View technical details",
    stages: "View bounded stage evidence",
    noSteps: "The backend did not return bounded evidence for the actual failed stage.",
    boundary: "This exact run remains blocked and is not client-ready. Preserved evidence can be reviewed without converting the failure into a passing result.",
    recovery: "Open this run in Recovery",
    technicalReasonFallback: "No bounded technical explanation was returned.",
    stageReasonFallback: "No bounded stage explanation was returned.",
  };
  const recoveryHref = failure.run_id
    ? `/operations/recovery?run_id=${encodeURIComponent(failure.run_id)}&assessment_type=${encodeURIComponent(failure.assessment_type || "comprehensive")}${spanish ? "&lang=es-MX" : ""}`
    : `/operations/recovery${spanish ? "?lang=es-MX" : ""}`;
  const failedStageId = failedStage?.step || "";
  const failedStageName = failedStageId ? stageDisplayLabel(failedStageId, spanish) : copy.missing;

  return <section
    className="section panel nico-failure-evidence"
    data-assessment-failure-evidence="true"
    data-assessment-failure-stage={failedStage?.step || "unknown_stage"}
    data-assessment-failure-code={failure.code}
    data-assessment-worker-failure-class={failure.worker?.failure_class || ""}
    aria-live="assertive"
    lang={spanish ? "es-MX" : undefined}
  >
    <div className="nico-failure-evidence__head">
      <div>
        <p className="eyebrow">{copy.eyebrow}</p>
        <h2>{copy.title}</h2>
        <p className="nico-failure-evidence__summary">{copy.summary}</p>
      </div>
      <span className="status red">{copy.blocked}</span>
    </div>

    <div className="nico-failure-evidence__primary">
      <article>
        <b>{copy.failedStage}</b>
        <span data-stage-id={failedStageId || "unknown_stage"} title={failedStageId || "unknown_stage"}>{failedStageName}</span>
      </article>
      <article>
        <b>{copy.run}</b>
        <code title={failure.run_id || copy.missing}>{failure.run_id || copy.missing}</code>
      </article>
    </div>

    <details className="help-details nico-failure-evidence__details">
      <summary>{copy.details}</summary>
      <dl>
        <div><dt>{copy.code}</dt><dd><code>{failure.code}</code></dd></div>
        <div><dt>{copy.message}</dt><dd>{authoredFailureMessage(failure.message, spanish, copy.technicalReasonFallback)}</dd></div>
        {failure.worker ? <>
          <div><dt>{copy.workerModel}</dt><dd><code>{failure.worker.model || copy.missing}</code></dd></div>
          <div><dt>{copy.workerExit}</dt><dd>{failure.worker.exit_code ?? copy.missing}</dd></div>
          <div><dt>{copy.workerSignal}</dt><dd><code>{failure.worker.exit_signal || copy.missing}</code></dd></div>
          <div><dt>{copy.workerErrorType}</dt><dd><code>{failure.worker.error_type || copy.missing}</code></dd></div>
          <div><dt>{copy.workerFailureClass}</dt><dd><code>{failure.worker.failure_class || copy.missing}</code></dd></div>
          <div><dt>{copy.workerBootstrap}</dt><dd><code>{failure.worker.bootstrap || copy.missing}</code></dd></div>
        </> : null}
        <div><dt>{copy.http}</dt><dd>{failure.http_status}</dd></div>
        <div><dt>{copy.type}</dt><dd><code>{failure.assessment_type || copy.missing}</code></dd></div>
        <div><dt>{copy.route}</dt><dd><code>{failure.route}</code></dd></div>
      </dl>
    </details>

    {stageRows.length ? <details className="help-details nico-failure-evidence__stages">
      <summary>{copy.stages}</summary>
      <div className="results-grid">
        {stageRows.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
          <div className="result-head">
            <b data-stage-id={item.step} title={item.step}>{stageDisplayLabel(item.step, spanish)}</b>
            <span
              className={`status ${tone(item.status)}`}
              data-status-id={item.status}
              title={item.status}
            >{statusDisplayLabel(item.status, spanish)}</span>
          </div>
          <p>{authoredFailureMessage(item.message, spanish, copy.stageReasonFallback)}</p>
        </article>)}
      </div>
    </details> : failure.progress.length ? null : <p className="warning-box">{copy.noSteps}</p>}

    <div className="nico-failure-evidence__boundary">
      <p>{copy.boundary}</p>
      {failure.run_id ? <a
        href={recoveryHref}
        onClick={(event) => {
          event.preventDefault();
          window.location.assign(recoveryHref);
        }}
      >{copy.recovery}</a> : null}
    </div>
  </section>;
}
