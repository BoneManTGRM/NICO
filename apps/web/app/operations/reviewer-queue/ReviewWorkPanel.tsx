"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import {savedRun, useReviewScope, reviewResponse, reviewError, ambiguousWrite, reconciliationMessage, type WorkspaceProps} from "./reviewWorkspaceState";
import {buildReviewActionPayload, type ReviewAction as Action} from "./reviewActionPayload";
import ReviewSessionNotice from "./ReviewSessionNotice";
import EvidenceRequests from "./EvidenceRequests";
import QualityControlRecords from "./QualityControlRecords";
import styles from "./review-work.module.css";

type Locale = "en" | "es-MX";
type JsonRecord = Record<string, unknown>;
type Projection = {
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  candidate_count?: number;
  dispositioned_candidate_count?: number;
  remaining_candidate_count?: number;
  quality_control_required_count?: number;
  quality_control_completed_count?: number;
  quality_control_blockers?: Record<string, string>;
  open_evidence_request_count?: number;
  unresolved_high_impact_candidate_ids?: string[];
  ready_for_final_approval?: boolean;
  empirical_measurement?: JsonRecord;
  ledger?: JsonRecord;
};

const COPY = {
  en: {
    title: "Phase 2 human review controls",
    lead: "Record authorized specialist decisions against the exact canonical candidate register. Every group action still writes one decision per underlying candidate. Nothing here approves client delivery.",
    language: "Español",
    run: "Exact run ID",
    reviewer: "Authorized reviewer",
    role: "Reviewer / specialist role",
    load: "Load review work",
    refresh: "Refresh",
    action: "Human action",
    target: "Candidate, cluster, or request ID",
    disposition: "Disposition",
    rationale: "Human rationale",
    residualRisk: "Residual risk",
    residualOwner: "Residual-risk owner",
    escalation: "High-impact escalation resolution",
    escalationOwner: "Escalation owner",
    assignee: "Assigned specialist",
    specialistRole: "Assigned specialist role",
    qcOutcome: "QC outcome",
    qcNote: "Independent QC note",
    requestText: "Evidence request",
    requestOwner: "Evidence request owner",
    resolution: "Evidence-resolution note",
    references: "Evidence references, one per line",
    stakeholderStatement: "Client / stakeholder evidence statement",
    sourceRole: "Source role",
    evidenceReference: "Evidence reference",
    submit: "Record authorized action",
    recording: "Recording…",
    noDelivery: "Human review required · client delivery remains blocked",
    ready: "Candidate review is ready for final approval",
    notReady: "Candidate review is not yet ready for final approval",
    empirical: "Empirical reviewer-time study",
    sessionStart: "Start measured specialist session",
    sessionStop: "Stop measured specialist session",
    completeStudy: "Complete empirical study",
    warning: "Reviewer identity, role, and explicit authorization are persisted with every action. Your signed-in specialist session protects each exact-run request.",
    status: "Status",
    combinedHours: "Combined specialist hours",
    fourHoursVerified: "≤ 4 hours verified",
    auditEvents: "Audit events",
    yes: "yes",
    no: "no",
  },
  "es-MX": {
    title: "Controles de revisión humana de Fase 2",
    lead: "Registra decisiones autorizadas de especialistas con base en el registro canónico exacto. Cada acción grupal conserva una decisión por candidato subyacente. Nada aquí autoriza la entrega al cliente.",
    language: "English",
    run: "ID de ejecución exacta",
    reviewer: "Revisor autorizado",
    role: "Función del revisor / especialista",
    load: "Cargar trabajo de revisión",
    refresh: "Actualizar",
    action: "Acción humana",
    target: "ID de candidato, grupo o solicitud",
    disposition: "Disposición",
    rationale: "Justificación humana",
    residualRisk: "Riesgo residual",
    residualOwner: "Responsable del riesgo residual",
    escalation: "Resolución de escalamiento de alto impacto",
    escalationOwner: "Responsable del escalamiento",
    assignee: "Especialista asignado",
    specialistRole: "Función del especialista asignado",
    qcOutcome: "Resultado de control de calidad",
    qcNote: "Nota de control independiente",
    requestText: "Solicitud de evidencia",
    requestOwner: "Responsable de evidencia",
    resolution: "Nota de resolución de evidencia",
    references: "Referencias de evidencia, una por línea",
    stakeholderStatement: "Declaración de evidencia del cliente / interesado",
    sourceRole: "Función de la fuente",
    evidenceReference: "Referencia de evidencia",
    submit: "Registrar acción autorizada",
    recording: "Registrando…",
    noDelivery: "Revisión humana requerida · la entrega al cliente sigue bloqueada",
    ready: "La revisión de candidatos está lista para aprobación final",
    notReady: "La revisión de candidatos aún no está lista para aprobación final",
    empirical: "Estudio empírico de tiempo de revisión",
    sessionStart: "Iniciar sesión medida de especialista",
    sessionStop: "Detener sesión medida de especialista",
    completeStudy: "Completar estudio empírico",
    warning: "La identidad, función y autorización explícita del revisor se conservan con cada acción. Su sesión de especialista protege cada solicitud de la ejecución exacta.",
    status: "Estado",
    combinedHours: "Horas combinadas de especialistas",
    fourHoursVerified: "≤ 4 horas verificadas",
    auditEvents: "Eventos de auditoría",
    yes: "sí",
    no: "no",
  },
} as const;

const ACTIONS: {value: Action; en: string; es: string}[] = [
  {value: "assign", en: "Assign candidate / cluster", es: "Asignar candidato / grupo"},
  {value: "disposition_candidate", en: "Disposition one candidate", es: "Disponer un candidato"},
  {value: "disposition_group", en: "Disposition homogeneous group", es: "Disponer grupo homogéneo"},
  {value: "quality_control", en: "Independent quality control", es: "Control de calidad independiente"},
  {value: "request_evidence", en: "Request proof-gap evidence", es: "Solicitar evidencia faltante"},
  {value: "resolve_evidence_request", en: "Resolve evidence request", es: "Resolver solicitud de evidencia"},
  {value: "stakeholder_evidence", en: "Record client / stakeholder evidence", es: "Registrar evidencia del cliente / interesado"},
  {value: "start_session", en: "Start measured review session", es: "Iniciar sesión de revisión medida"},
  {value: "stop_session", en: "Stop measured review session", es: "Detener sesión de revisión medida"},
  {value: "complete_empirical_study", en: "Complete empirical reviewer-time study", es: "Completar estudio empírico de tiempo"},
];

const DISPOSITIONS = [
  {value: "confirmed", en: "confirmed", es: "Confirmado"},
  {value: "false_positive", en: "false positive", es: "Falso positivo"},
  {value: "not_applicable", en: "not applicable", es: "No aplica"},
  {value: "accepted_risk", en: "accepted risk", es: "Riesgo aceptado"},
  {value: "needs_more_evidence", en: "needs more evidence", es: "Requiere más evidencia"},
] as const;

const QC_OUTCOMES = [
  {value: "agree", en: "agree", es: "De acuerdo"},
  {value: "disagree", en: "disagree", es: "En desacuerdo"},
] as const;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function empiricalStatus(value: unknown, locale: Locale): string {
  const status = String(value || "not_yet_measured");
  if (locale === "en") return status;
  const labels: Record<string, string> = {
    not_yet_measured: "Aún no medido",
    verified_within_four_hours: "Verificado dentro de cuatro horas",
    measured_over_four_hours: "Medido en más de cuatro horas",
  };
  return Object.prototype.hasOwnProperty.call(labels, status)
    ? labels[status]
    : `Estado técnico: ${status}`;
}

type ProjectionSummaryProps = {projection: Projection; locale: Locale};

function ReviewProgressSummary({projection, locale}: ProjectionSummaryProps) {
  const copy = COPY[locale];
  return <div className={styles.summary}>
    <article><b>{projection.dispositioned_candidate_count ?? 0}/{projection.candidate_count ?? 0}</b><span>{locale === "es-MX" ? "candidatos con disposición" : "candidates dispositioned"}</span></article>
    <article><b>{projection.quality_control_completed_count ?? 0}/{projection.quality_control_required_count ?? 0}</b><span>{locale === "es-MX" ? "muestras de control de calidad completadas" : "QC samples complete"}</span></article>
    <article><b>{projection.open_evidence_request_count ?? 0}</b><span>{locale === "es-MX" ? "solicitudes de evidencia abiertas" : "open evidence requests"}</span></article>
    <article><b>{Array.isArray(projection.unresolved_high_impact_candidate_ids) ? projection.unresolved_high_impact_candidate_ids.length : 0}</b><span>{locale === "es-MX" ? "escalamientos abiertos" : "open high-impact escalations"}</span></article>
    <article className={styles.wide}><b>{projection.ready_for_final_approval ? copy.ready : copy.notReady}</b><span>{locale === "es-MX" ? "La aprobación final sigue siendo una decisión humana separada." : "Final approval remains a separate human decision."}</span></article>
  </div>;
}

function EmpiricalStudySummary({projection, locale}: ProjectionSummaryProps) {
  const copy = COPY[locale];
  const empirical = asRecord(projection.empirical_measurement);
  const ledger = asRecord(projection.ledger);
  return <details className={styles.empirical}>
    <summary>{copy.empirical}</summary>
    <dl>
      <div><dt>{copy.status}</dt><dd>{empiricalStatus(empirical.status, locale)}</dd></div>
      <div><dt>{copy.combinedHours}</dt><dd>{String(empirical.combined_specialist_hours ?? 0)}</dd></div>
      <div><dt>{copy.fourHoursVerified}</dt><dd>{empirical.four_combined_specialist_hours_empirically_proven === true ? copy.yes : copy.no}</dd></div>
      <div><dt>{copy.auditEvents}</dt><dd>{String(projection.ledger ? (Array.isArray(ledger.audit_events) ? ledger.audit_events.length : 0) : 0)}</dd></div>
    </dl>
  </details>;
}

export default function ReviewWorkPanel({runId, refresh = 0, isCurrent, onChanged}: WorkspaceProps = savedRun()) {
  const scope = useReviewScope(isCurrent);
  const [locale, setLocale] = useState<Locale>("en");
  const copy = COPY[locale];
  const [reviewer, setReviewer] = useState("");
  const [reviewerRole, setReviewerRole] = useState("");
  const [action, setAction] = useState<Action>("disposition_candidate");
  const [targetId, setTargetId] = useState("");
  const [disposition, setDisposition] = useState("confirmed");
  const [rationale, setRationale] = useState("");
  const [residualRisk, setResidualRisk] = useState("");
  const [residualRiskOwner, setResidualRiskOwner] = useState("");
  const [escalationResolution, setEscalationResolution] = useState("");
  const [escalationOwner, setEscalationOwner] = useState("");
  const [assignee, setAssignee] = useState("");
  const [specialistRole, setSpecialistRole] = useState("");
  const [qcOutcome, setQcOutcome] = useState("agree");
  const [qcNote, setQcNote] = useState("");
  const [requestText, setRequestText] = useState("");
  const [requestOwner, setRequestOwner] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const [evidenceReferences, setEvidenceReferences] = useState("");
  const [stakeholderStatement, setStakeholderStatement] = useState("");
  const [sourceRole, setSourceRole] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [projection, setProjection] = useState<Projection | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    setLocale(params.get("lang") === "es-MX" ? "es-MX" : "en");
  }, []);

  function switchLocale(): void {
    const nextLocale: Locale = locale === "es-MX" ? "en" : "es-MX";
    const target = new URL(window.location.href);
    target.searchParams.set("lang", nextLocale);
    if (runId.trim()) target.searchParams.set("run_id", runId.trim());
    window.location.assign(`${target.pathname}${target.search}${target.hash}`);
  }

  const url = useMemo(
    () => `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review-work`,
    [runId],
  );

  useEffect(() => {if (refresh > 0) void load();}, [refresh]);

  async function readProjection() {
    const response = await fetch(url, {
      method: "GET", cache: "no-store", credentials: "same-origin", headers: {Accept: "application/json"},
    });
    return reviewResponse(response, runId, locale);
  }

  async function load(): Promise<void> {
    if (!runId.trim()) return;
    // A sibling refresh must never supersede an in-flight write or unlock its form.
    if (scope.mutation.current) {scope.refreshDeferred.current = true; return;}
    const token = scope.begin();
    setBusy(true); setError(""); setProjection(null);
    try {
      const next = await readProjection();
      if (scope.current(token)) setProjection(next);
    } catch (caught) {
      if (scope.current(token)) setError(reviewError(caught, locale));
    } finally {
      if (scope.current(token)) setBusy(false);
      scope.finish(token);
    }
  }

  async function submit(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    if (!runId.trim() || !projection || scope.pending.current || !reviewer.trim() || !reviewerRole.trim()) return;
    const token = scope.begin();
    scope.mutation.current = true;
    setBusy(true);
    setError("");
    setProjection(null);
    try {
      const response = await fetch(url, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", Accept: "application/json"},
        body: JSON.stringify(buildReviewActionPayload(action, {
          reviewer, reviewerRole, targetId, disposition,
          rationale, residualRisk, residualRiskOwner, escalationResolution,
          escalationOwner, assignee, specialistRole, qcOutcome,
          qcNote, requestText, requestOwner, resolutionNote,
          evidenceReferences, stakeholderStatement, sourceRole, evidenceReference,
        })),
      });
      const next = await reviewResponse(response, runId, locale);
      if (scope.current(token)) {setProjection(next); onChanged?.(runId);}
    } catch (caught) {
      if (scope.current(token)) {
        if (ambiguousWrite(caught)) {
          try {
            const next = await readProjection();
            if (scope.current(token)) {setProjection(next); onChanged?.(runId);}
          } catch { /* Keep actions blocked when reconciliation cannot verify saved state. */ }
          if (scope.current(token)) setNotice(reconciliationMessage(locale));
        } else setError(reviewError(caught, locale));
      }
    } finally {
      if (scope.current(token)) {
        setBusy(false);
        setTargetId(""); setRationale("");
      }
      scope.mutation.current = false;
      scope.finish(token);
      if (scope.current(token) && scope.refreshDeferred.current) {
        scope.refreshDeferred.current = false;
        void load();
      }
    }
  }

  const ledger = asRecord(projection?.ledger);
  const sessionActions = action === "start_session" || action === "stop_session" || action === "complete_empirical_study";

  return <section className={styles.panel} data-phase2-review-work="true" data-client-delivery-allowed="false">
    <div className={styles.header}>
      <div><p className={styles.eyebrow}>{locale === "es-MX" ? "NICO COMPREHENSIVE · FASE 2" : "NICO COMPREHENSIVE · PHASE 2"}</p><h2>{copy.title}</h2></div>
      <button type="button" className={styles.language} onClick={switchLocale}>{copy.language}</button>
    </div>
    <p>{copy.lead}</p>
    <p className={styles.boundary}>{copy.noDelivery}</p>

    {notice ? <p role="alert">{notice}</p> : null}
    <ReviewSessionNotice runId={runId} locale={locale} />
    <div className={styles.identityGrid}>
      <label>{copy.run}<input disabled={busy} value={runId} readOnly autoComplete="off" /></label>
      <label>{copy.reviewer}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="off" /></label>
      <label>{copy.role}<input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} autoComplete="off" /></label>
    </div>
    <p className={styles.security}>{copy.warning}</p>
    <div className={styles.actions}><button type="button" onClick={load} disabled={busy || !runId.trim()}>{projection ? copy.refresh : copy.load}</button></div>

    {projection ? <ReviewProgressSummary projection={projection} locale={locale} /> : null}

    {projection ? <QualityControlRecords records={ledger.quality_control} blockers={projection.quality_control_blockers} events={ledger.audit_events} locale={locale} busy={busy} onSelect={(candidateId) => {
      setAction("quality_control"); setTargetId(candidateId); setQcNote(""); setQcOutcome("agree");
    }} /> : null}
    {projection ? <EvidenceRequests requests={ledger.evidence_requests} locale={locale} busy={busy} onResolve={(requestId) => {
      setAction("resolve_evidence_request");
      setTargetId(requestId);
      setResolutionNote("");
      setEvidenceReferences("");
    }} /> : null}

    <form className={styles.form} onSubmit={submit}>
      <label>{copy.action}<select value={action} onChange={(event) => setAction(event.target.value as Action)}>{ACTIONS.map((item) => <option key={item.value} value={item.value}>{locale === "es-MX" ? item.es : item.en}</option>)}</select></label>

      {!sessionActions && action !== "stakeholder_evidence" ? <label>{copy.target}<input value={targetId} onChange={(event) => setTargetId(event.target.value)} autoComplete="off" /></label> : null}
      {action === "assign" ? <><label>{copy.assignee}<input value={assignee} onChange={(event) => setAssignee(event.target.value)} /></label><label>{copy.specialistRole}<input value={specialistRole} onChange={(event) => setSpecialistRole(event.target.value)} /></label></> : null}
      {action === "disposition_candidate" || action === "disposition_group" ? <>
        <label>{copy.disposition}<select value={disposition} onChange={(event) => setDisposition(event.target.value)}>{DISPOSITIONS.map((item) => <option key={item.value} value={item.value}>{locale === "es-MX" ? item.es : item.en}</option>)}</select></label>
        <label className={styles.full}>{copy.rationale}<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <label>{copy.residualRisk}<input value={residualRisk} onChange={(event) => setResidualRisk(event.target.value)} /></label>
        <label>{copy.residualOwner}<input value={residualRiskOwner} onChange={(event) => setResidualRiskOwner(event.target.value)} /></label>
        <label className={styles.full}>{copy.escalation}<textarea value={escalationResolution} onChange={(event) => setEscalationResolution(event.target.value)} /></label>
        <label>{copy.escalationOwner}<input value={escalationOwner} onChange={(event) => setEscalationOwner(event.target.value)} /></label>
      </> : null}
      {action === "quality_control" ? <><label>{copy.qcOutcome}<select value={qcOutcome} onChange={(event) => setQcOutcome(event.target.value)}>{QC_OUTCOMES.map((item) => <option key={item.value} value={item.value}>{locale === "es-MX" ? item.es : item.en}</option>)}</select></label><label className={styles.full}>{copy.qcNote}<textarea value={qcNote} onChange={(event) => setQcNote(event.target.value)} /></label></> : null}
      {action === "request_evidence" ? <><label className={styles.full}>{copy.requestText}<textarea value={requestText} onChange={(event) => setRequestText(event.target.value)} /></label><label>{copy.requestOwner}<input value={requestOwner} onChange={(event) => setRequestOwner(event.target.value)} /></label></> : null}
      {action === "resolve_evidence_request" ? <><label className={styles.full}>{copy.resolution}<textarea value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} /></label><label className={styles.full}>{copy.references}<textarea value={evidenceReferences} onChange={(event) => setEvidenceReferences(event.target.value)} /></label></> : null}
      {action === "stakeholder_evidence" ? <><label className={styles.full}>{copy.stakeholderStatement}<textarea value={stakeholderStatement} onChange={(event) => setStakeholderStatement(event.target.value)} /></label><label>{copy.sourceRole}<input value={sourceRole} onChange={(event) => setSourceRole(event.target.value)} /></label><label>{copy.evidenceReference}<input value={evidenceReference} onChange={(event) => setEvidenceReference(event.target.value)} /></label></> : null}

      <div className={`${styles.actions} ${styles.full}`}><button type="submit" disabled={busy || !projection || !reviewer.trim() || !reviewerRole.trim()}>{busy ? copy.recording : action === "start_session" ? copy.sessionStart : action === "stop_session" ? copy.sessionStop : action === "complete_empirical_study" ? copy.completeStudy : copy.submit}</button></div>
    </form>

    {projection ? <EmpiricalStudySummary projection={projection} locale={locale} /> : null}
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
  </section>;
}
