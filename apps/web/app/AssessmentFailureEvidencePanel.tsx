"use client";

import {useEffect, useMemo, useState} from "react";
import {
  ASSESSMENT_FAILURE_EVENT,
  type AssessmentFailureEvidence,
} from "./AssessmentApiTransportBridge";

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
      || window.location.pathname.startsWith("/es/assessment");
    if (!assessmentRoute) return;
    setSpanish(window.location.pathname.startsWith("/es/") || document.documentElement.lang.toLowerCase().startsWith("es"));

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
    missing: "no devuelto",
    details: "Ver detalles técnicos",
    stages: "Ver evidencia acotada de etapas",
    noSteps: "El backend no devolvió evidencia acotada de la etapa que falló.",
    boundary: "Esta ejecución sigue bloqueada y no está lista para el cliente. La evidencia preservada puede revisarse sin convertir el fallo en un resultado aprobado.",
    recovery: "Abrir esta ejecución en Recuperación",
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
    missing: "not returned",
    details: "View technical details",
    stages: "View bounded stage evidence",
    noSteps: "The backend did not return bounded evidence for the actual failed stage.",
    boundary: "This exact run remains blocked and is not client-ready. Preserved evidence can be reviewed without converting the failure into a passing result.",
    recovery: "Open this run in Recovery",
  };
  const recoveryHref = failure.run_id
    ? `/operations/recovery?run_id=${encodeURIComponent(failure.run_id)}&assessment_type=${encodeURIComponent(failure.assessment_type || "comprehensive")}`
    : "/operations/recovery";
  const failedStageName = failedStage?.step.replaceAll("_", " ") || copy.missing;

  return <section
    className="section panel nico-failure-evidence"
    data-assessment-failure-evidence="true"
    data-assessment-failure-stage={failedStage?.step || "unknown_stage"}
    data-assessment-failure-code={failure.code}
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
        <span>{failedStageName}</span>
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
        <div><dt>{copy.message}</dt><dd>{failure.message}</dd></div>
        <div><dt>{copy.http}</dt><dd>{failure.http_status}</dd></div>
        <div><dt>{copy.type}</dt><dd>{failure.assessment_type || copy.missing}</dd></div>
        <div><dt>{copy.route}</dt><dd><code>{failure.route}</code></dd></div>
      </dl>
    </details>

    {failure.progress.length ? <details className="help-details nico-failure-evidence__stages">
      <summary>{copy.stages}</summary>
      <div className="results-grid">
        {failure.progress.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
          <div className="result-head"><b>{item.step.replaceAll("_", " ")}</b><span className={`status ${tone(item.status)}`}>{item.status}</span></div>
          <p>{item.message}</p>
        </article>)}
      </div>
    </details> : <p className="warning-box">{copy.noSteps}</p>}

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
