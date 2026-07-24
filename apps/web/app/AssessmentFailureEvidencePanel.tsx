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
    };
  }, []);

  const failedStage = useMemo(
    () => failure?.progress.find((item) => TERMINAL_FAILURES.has(item.status.toLowerCase())) || null,
    [failure],
  );

  if (!failure) return null;

  const copy = spanish ? {
    eyebrow: "EVIDENCIA DE FALLO DE LA EVALUACIÓN",
    stopped: failure.run_id ? `La ejecución ${failure.run_id} se detuvo` : "La solicitud se detuvo antes de recibir un ID de ejecución",
    failedStage: "Etapa que falló",
    http: "Estado HTTP original",
    route: "Ruta canónica",
    type: "Tipo de evaluación",
    run: "Identidad de ejecución",
    missing: "no devuelto",
    noSteps: "El backend no devolvió evidencia acotada de la etapa que falló.",
    boundary: "Este panel conserva únicamente evidencia acotada del estado. No convierte una etapa fallida o no disponible en un resultado aprobado.",
    recovery: "Abrir esta misma ejecución en Recuperación antes de iniciar otra.",
  } : {
    eyebrow: "ASSESSMENT FAILURE EVIDENCE",
    stopped: failure.run_id ? `Run ${failure.run_id} stopped` : "Assessment request stopped before a run ID was returned",
    failedStage: "Actual failed stage",
    http: "Original HTTP status",
    route: "Canonical route",
    type: "Assessment type",
    run: "Run identity",
    missing: "not returned",
    noSteps: "The backend did not return bounded evidence for the actual failed stage.",
    boundary: "This panel preserves only bounded status evidence. It does not convert a failed or unavailable stage into a passing result.",
    recovery: "Open this same run in Recovery before starting another.",
  };
  const recoveryHref = failure.run_id
    ? `/operations/recovery?run_id=${encodeURIComponent(failure.run_id)}&assessment_type=${encodeURIComponent(failure.assessment_type || "express")}`
    : "/operations/recovery";

  return <>
    <style>{`body[data-nico-terminal-failure="true"] .report-actions { display: none !important; }`}</style>
    <section className="section panel" aria-live="assertive" lang={spanish ? "es-MX" : undefined}>
      <div className="section-head">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.stopped}</h2>
        </div>
        <span className="status red">{failure.code}</span>
      </div>
      <p className="error-box">{failure.message}</p>
      <div className="grid four target-grid">
        <article><b>{copy.failedStage}</b><span>{failedStage?.step.replaceAll("_", " ") || copy.missing}</span></article>
        <article><b>{copy.http}</b><span>{failure.http_status}</span></article>
        <article><b>{copy.type}</b><span>{failure.assessment_type || copy.missing}</span></article>
        <article><b>{copy.run}</b><span>{failure.run_id || copy.missing}</span></article>
      </div>
      <details className="help-details">
        <summary>{copy.route}</summary>
        <code>{failure.route}</code>
      </details>
      {failure.progress.length ? <div className="results-grid">
        {failure.progress.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
          <div className="result-head"><b>{item.step.replaceAll("_", " ")}</b><span className={`status ${tone(item.status)}`}>{item.status}</span></div>
          <p>{item.message}</p>
        </article>)}
      </div> : <p className="warning-box">{copy.noSteps}</p>}
      <p className="warning-box">
        {copy.boundary}
        {failure.run_id ? <> <a
          href="/operations/recovery"
          onClick={(event) => {
            event.preventDefault();
            window.location.assign(recoveryHref);
          }}
        >{copy.recovery}</a></> : null}
      </p>
    </section>
  </>;
}
