"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import styles from "./review-work.module.css";

type Locale = "en" | "es-MX";
type JsonRecord = Record<string, unknown>;
type Action =
  | "assign"
  | "disposition_candidate"
  | "disposition_group"
  | "quality_control"
  | "request_evidence"
  | "resolve_evidence_request"
  | "stakeholder_evidence"
  | "start_session"
  | "stop_session"
  | "complete_empirical_study";

type Projection = {
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  candidate_count?: number;
  dispositioned_candidate_count?: number;
  remaining_candidate_count?: number;
  quality_control_required_count?: number;
  quality_control_completed_count?: number;
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
    token: "Operator admin token",
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
    warning: "Reviewer identity, role, and explicit authorization are persisted with every action. The admin token stays only in this open page.",
  },
  "es-MX": {
    title: "Controles de revisión humana de Fase 2",
    lead: "Registra decisiones autorizadas de especialistas contra el registro canónico exacto. Cada acción grupal conserva una decisión por candidato subyacente. Nada aquí autoriza la entrega al cliente.",
    language: "English",
    run: "ID de ejecución exacta",
    token: "Token de administrador",
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
    warning: "La identidad, función y autorización explícita del revisor se conservan con cada acción. El token administrativo permanece únicamente en esta página abierta.",
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

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function errorMessage(value: unknown): string {
  if (value instanceof Error) return value.message;
  return String(value || "Review work request failed.");
}

async function parseResponse(response: Response): Promise<Projection> {
  const payload = await response.json().catch(() => ({})) as Projection & {detail?: unknown; error?: unknown};
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object"
        ? String((detail as JsonRecord).message || (detail as JsonRecord).code || JSON.stringify(detail))
        : String(payload.error || `HTTP ${response.status}`);
    throw new Error(message);
  }
  return payload;
}

export default function ReviewWorkPanel() {
  const [locale, setLocale] = useState<Locale>("en");
  const copy = COPY[locale];
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
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
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    setRunId(params.get("run_id") || "");
    setLocale(params.get("lang") === "es-MX" ? "es-MX" : "en");
  }, []);

  const url = useMemo(
    () => `/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review-work`,
    [runId],
  );

  async function load(): Promise<void> {
    if (!runId.trim() || !adminToken.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url, {
        method: "GET",
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken},
      });
      setProjection(await parseResponse(response));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function actionPayload(): JsonRecord {
    const common: JsonRecord = {
      action,
      reviewer: reviewer.trim(),
      reviewer_role: reviewerRole.trim(),
      review_authorized: true,
      authorization_confirmed: true,
    };
    if (action === "assign") return {...common, target_id: targetId.trim(), assignee: assignee.trim(), specialist_role: specialistRole.trim()};
    if (action === "disposition_candidate" || action === "disposition_group") {
      return {
        ...common,
        ...(action === "disposition_candidate" ? {candidate_id: targetId.trim()} : {cluster_id: targetId.trim()}),
        disposition,
        rationale: rationale.trim(),
        residual_risk: residualRisk.trim(),
        residual_risk_owner: residualRiskOwner.trim(),
        escalation_resolution: escalationResolution.trim(),
        escalation_owner: escalationOwner.trim(),
      };
    }
    if (action === "quality_control") return {...common, candidate_id: targetId.trim(), qc_outcome: qcOutcome, qc_note: qcNote.trim()};
    if (action === "request_evidence") return {...common, candidate_id: targetId.trim(), request_text: requestText.trim(), owner: requestOwner.trim()};
    if (action === "resolve_evidence_request") return {...common, request_id: targetId.trim(), resolution_note: resolutionNote.trim(), evidence_references: evidenceReferences.split("\n").map((item) => item.trim()).filter(Boolean)};
    if (action === "stakeholder_evidence") return {...common, statement: stakeholderStatement.trim(), source_role: sourceRole.trim(), evidence_reference: evidenceReference.trim()};
    return common;
  }

  async function submit(event?: FormEvent): Promise<void> {
    event?.preventDefault();
    if (!runId.trim() || !adminToken.trim() || !reviewer.trim() || !reviewerRole.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url, {
        method: "POST",
        cache: "no-store",
        headers: {"Content-Type": "application/json", Accept: "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify(actionPayload()),
      });
      setProjection(await parseResponse(response));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const empirical = asRecord(projection?.empirical_measurement);
  const ledger = asRecord(projection?.ledger);
  const sessionActions = action === "start_session" || action === "stop_session" || action === "complete_empirical_study";

  return <section className={styles.panel} data-phase2-review-work="true" data-client-delivery-allowed="false">
    <div className={styles.header}>
      <div><p className={styles.eyebrow}>NICO COMPREHENSIVE · PHASE 2</p><h2>{copy.title}</h2></div>
      <button type="button" className={styles.language} onClick={() => setLocale(locale === "en" ? "es-MX" : "en")}>{copy.language}</button>
    </div>
    <p>{copy.lead}</p>
    <p className={styles.boundary}>{copy.noDelivery}</p>

    <div className={styles.identityGrid}>
      <label>{copy.run}<input value={runId} onChange={(event) => setRunId(event.target.value)} autoComplete="off" /></label>
      <label>{copy.token}<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" /></label>
      <label>{copy.reviewer}<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="off" /></label>
      <label>{copy.role}<input value={reviewerRole} onChange={(event) => setReviewerRole(event.target.value)} autoComplete="off" /></label>
    </div>
    <p className={styles.security}>{copy.warning}</p>
    <div className={styles.actions}><button type="button" onClick={load} disabled={busy || !runId.trim() || !adminToken.trim()}>{projection ? copy.refresh : copy.load}</button></div>

    {projection ? <div className={styles.summary}>
      <article><b>{projection.dispositioned_candidate_count ?? 0}/{projection.candidate_count ?? 0}</b><span>{locale === "es-MX" ? "candidatos dispuestos" : "candidates dispositioned"}</span></article>
      <article><b>{projection.quality_control_completed_count ?? 0}/{projection.quality_control_required_count ?? 0}</b><span>{locale === "es-MX" ? "muestras QC completas" : "QC samples complete"}</span></article>
      <article><b>{projection.open_evidence_request_count ?? 0}</b><span>{locale === "es-MX" ? "solicitudes de evidencia abiertas" : "open evidence requests"}</span></article>
      <article><b>{Array.isArray(projection.unresolved_high_impact_candidate_ids) ? projection.unresolved_high_impact_candidate_ids.length : 0}</b><span>{locale === "es-MX" ? "escalamientos abiertos" : "open high-impact escalations"}</span></article>
      <article className={styles.wide}><b>{projection.ready_for_final_approval ? copy.ready : copy.notReady}</b><span>{locale === "es-MX" ? "La aprobación final sigue siendo una decisión humana separada." : "Final approval remains a separate human decision."}</span></article>
    </div> : null}

    <form className={styles.form} onSubmit={submit}>
      <label>{copy.action}<select value={action} onChange={(event) => setAction(event.target.value as Action)}>{ACTIONS.map((item) => <option key={item.value} value={item.value}>{locale === "es-MX" ? item.es : item.en}</option>)}</select></label>

      {!sessionActions && action !== "stakeholder_evidence" ? <label>{copy.target}<input value={targetId} onChange={(event) => setTargetId(event.target.value)} autoComplete="off" /></label> : null}
      {action === "assign" ? <><label>{copy.assignee}<input value={assignee} onChange={(event) => setAssignee(event.target.value)} /></label><label>{copy.specialistRole}<input value={specialistRole} onChange={(event) => setSpecialistRole(event.target.value)} /></label></> : null}
      {action === "disposition_candidate" || action === "disposition_group" ? <>
        <label>{copy.disposition}<select value={disposition} onChange={(event) => setDisposition(event.target.value)}><option value="confirmed">confirmed</option><option value="false_positive">false positive</option><option value="not_applicable">not applicable</option><option value="accepted_risk">accepted risk</option><option value="needs_more_evidence">needs more evidence</option></select></label>
        <label className={styles.full}>{copy.rationale}<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
        <label>{copy.residualRisk}<input value={residualRisk} onChange={(event) => setResidualRisk(event.target.value)} /></label>
        <label>{copy.residualOwner}<input value={residualRiskOwner} onChange={(event) => setResidualRiskOwner(event.target.value)} /></label>
        <label className={styles.full}>{copy.escalation}<textarea value={escalationResolution} onChange={(event) => setEscalationResolution(event.target.value)} /></label>
        <label>{copy.escalationOwner}<input value={escalationOwner} onChange={(event) => setEscalationOwner(event.target.value)} /></label>
      </> : null}
      {action === "quality_control" ? <><label>{copy.qcOutcome}<select value={qcOutcome} onChange={(event) => setQcOutcome(event.target.value)}><option value="agree">agree</option><option value="disagree">disagree</option></select></label><label className={styles.full}>{copy.qcNote}<textarea value={qcNote} onChange={(event) => setQcNote(event.target.value)} /></label></> : null}
      {action === "request_evidence" ? <><label className={styles.full}>{copy.requestText}<textarea value={requestText} onChange={(event) => setRequestText(event.target.value)} /></label><label>{copy.requestOwner}<input value={requestOwner} onChange={(event) => setRequestOwner(event.target.value)} /></label></> : null}
      {action === "resolve_evidence_request" ? <><label className={styles.full}>{copy.resolution}<textarea value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} /></label><label className={styles.full}>{copy.references}<textarea value={evidenceReferences} onChange={(event) => setEvidenceReferences(event.target.value)} /></label></> : null}
      {action === "stakeholder_evidence" ? <><label className={styles.full}>{copy.stakeholderStatement}<textarea value={stakeholderStatement} onChange={(event) => setStakeholderStatement(event.target.value)} /></label><label>{copy.sourceRole}<input value={sourceRole} onChange={(event) => setSourceRole(event.target.value)} /></label><label>{copy.evidenceReference}<input value={evidenceReference} onChange={(event) => setEvidenceReference(event.target.value)} /></label></> : null}

      <div className={`${styles.actions} ${styles.full}`}><button type="submit" disabled={busy || !projection || !reviewer.trim() || !reviewerRole.trim()}>{busy ? copy.recording : action === "start_session" ? copy.sessionStart : action === "stop_session" ? copy.sessionStop : action === "complete_empirical_study" ? copy.completeStudy : copy.submit}</button></div>
    </form>

    {projection ? <details className={styles.empirical}><summary>{copy.empirical}</summary><dl><div><dt>Status</dt><dd>{String(empirical.status || "not_yet_measured")}</dd></div><div><dt>Combined specialist hours</dt><dd>{String(empirical.combined_specialist_hours ?? 0)}</dd></div><div><dt>≤ 4 hours verified</dt><dd>{empirical.four_combined_specialist_hours_empirically_proven === true ? "yes" : "no"}</dd></div><div><dt>Audit events</dt><dd>{String(projection.ledger ? (Array.isArray(ledger.audit_events) ? ledger.audit_events.length : 0) : 0)}</dd></div></dl></details> : null}
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
  </section>;
}
