"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import styles from "./assessment.module.css";

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 360;

type Locale = "en" | "es-MX";
type Service = "express" | "comprehensive";
type Phase = "idle" | "starting" | "running" | "review_required" | "complete" | "failed" | "timed_out";
type Evidence = Record<string, unknown> | string[];
type Report = {markdown?: string; html?: string; pdf_base64?: string; pdf_filename?: string; pdf_error?: string; report_id?: string; pdf_sha256?: string};
type Section = {id?: string; label?: string; score?: number | null; presented_score?: number | null; status?: string; presented_status?: string; summary?: string; evidence?: string[]; findings?: string[]; unavailable?: string[]};
type Assessment = {executive_summary?: string; evidence_coverage?: {calculated?: boolean; percent?: number; label?: string}; maturity_signal?: {level?: string; score?: number; presented_score?: number}; sections?: Section[]; unavailable_data_notes?: string[]; human_review_required?: boolean; client_ready?: boolean};
type Stage = {status?: string; message?: string; summary?: string; evidence?: Evidence; assessment?: Assessment; report_package?: Report; reports?: Report};
type Result = Assessment & {
  service_id?: string;
  status?: string;
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  evidence_ledger_id?: string;
  customer_id?: string;
  project_id?: string;
  current_stage?: string | null;
  progress_percent?: number;
  progress?: Array<{step?: string; status?: string; message?: string; evidence?: Record<string, unknown>}>;
  assessment?: Assessment;
  reports?: Report;
  record?: {status?: string; current_stage?: string | null; progress_percent?: number; stage_results?: Record<string, Stage>; revision?: number; integrity_sha256?: string};
  repository_snapshot?: {commit_sha?: string};
  scanner?: {status?: string};
  scanner_evidence?: {status?: string; scanner_status?: string};
  persistence?: {recorded?: boolean; durable?: boolean; adapter?: string};
  human_review_required?: boolean;
  client_ready?: boolean;
  client_delivery_allowed?: boolean;
};
type Scope = {customerId: string; projectId: string};
type Copy = {
  heroEyebrow: string;
  title: string;
  lead: string;
  coverage: string;
  warning: string;
  repo: string;
  repoPlaceholder: string;
  client: string;
  project: string;
  confirm: string;
  run: string;
  state: string;
  stage: string;
  progress: string;
  elapsed: string;
  checks: string;
  runId: string;
  commit: string;
  scanner: string;
  report: string;
  review: string;
  maturity: string;
  score: string;
  durable: string;
  yes: string;
  recorded: string;
  pending: string;
  awaitingStage: string;
  awaitingScanner: string;
  reviewAfterReport: string;
  maturityAfterScoring: string;
  notScoredYet: string;
  reviewLimitedNotScored: string;
  unavailableStatus: string;
  evidenceLimitations: string;
  baselineNotEstablished: string;
  inputNotProvided: string;
  notApplicable: string;
  runtimeAcceptanceNotProvided: string;
  awaitingCommercialInputs: string;
  copyValue: string;
  valueCopied: string;
  notScored: string;
  notVerified: string;
  copied: string;
  copy: string;
  download: string;
  select: string;
  unavailable: string;
  evidence: string;
  findings: string;
  stepEvidence: string;
  reviewNotice: string;
  backendError: string;
  authError: string;
  invalidJson: string;
  runIdMissing: string;
  expressComplete: string;
  comprehensiveReview: string;
  stopped: string;
  pdfMissing: string;
  services: Record<Service, {label: string; eyebrow: string; heading: string; summary: string; instructionsTitle: string; instructions: string[]}>;
  phases: Record<Phase, string>;
  stageLabels: Record<string, string>;
};

const EN_STAGE_LABELS: Record<string, string> = {
  request_accepted: "Request accepted",
  repo_evidence: "Repository evidence",
  repository_evidence: "Repository evidence",
  scanner_worker: "Scanner suite",
  scanner_reconciliation: "Scanner reconciliation",
  evidence_attachment: "Evidence attachment",
  accuracy_review: "Accuracy review",
  scoring: "Technical scoring",
  score_reconciliation: "Score reconciliation",
  reports: "Report generation",
  report_generation: "Report generation",
  truth_and_review_gates: "Truth and review gates",
  authorization_and_scope: "Authorization and scope",
  immutable_repository_snapshot: "Immutable repository snapshot",
  repository_and_delivery_evidence: "Repository and delivery evidence",
  dependency_security_static_analysis: "Dependency, security, and static analysis",
  ci_cd_architecture_complexity_velocity: "CI/CD, architecture, complexity, and velocity",
  evidence_reconciliation_and_scoring: "Evidence reconciliation and scoring",
  decision_report_generation: "Core decision report",
  deep_scanner_triage: "Deep scanner triage",
  functional_qa: "Functional QA",
  platform_parity: "Platform parity",
  deployment_and_infrastructure: "Deployment and infrastructure",
  architecture_and_data_flow: "Architecture and data flow",
  developer_delivery_process: "Developer delivery process",
  stakeholder_and_business_alignment: "Stakeholder and business alignment",
  requirements_traceability: "Requirements traceability",
  historical_trends_and_change_failure: "Historical trends and change failure",
  six_month_roadmap: "Six-month roadmap",
  staffing_sequencing_and_cost: "Staffing, sequencing, and cost",
  risk_reduction_and_executive_briefing: "Risk reduction and executive briefing",
  final_comprehensive_report_generation: "Final Comprehensive report",
  cross_format_truth_verification: "Cross-format truth verification",
  human_review_request: "Human-review request",
  client_acceptance_pending: "Client acceptance pending",
};

const ES_STAGE_LABELS: Record<string, string> = {
  request_accepted: "Solicitud aceptada",
  repo_evidence: "Evidencia del repositorio",
  repository_evidence: "Evidencia del repositorio",
  scanner_worker: "Conjunto de analizadores",
  scanner_reconciliation: "Conciliación de analizadores",
  evidence_attachment: "Adjunto de evidencia",
  accuracy_review: "Revisión de exactitud",
  scoring: "Puntuación técnica",
  score_reconciliation: "Conciliación de puntuación",
  reports: "Generación del informe",
  report_generation: "Generación del informe",
  truth_and_review_gates: "Controles de veracidad y revisión",
  authorization_and_scope: "Autorización y alcance",
  immutable_repository_snapshot: "Instantánea inmutable del repositorio",
  repository_and_delivery_evidence: "Evidencia del repositorio y de entrega",
  dependency_security_static_analysis: "Dependencias, seguridad y análisis estático",
  ci_cd_architecture_complexity_velocity: "CI/CD, arquitectura, complejidad y velocidad",
  evidence_reconciliation_and_scoring: "Conciliación de evidencia y puntuación",
  decision_report_generation: "Informe principal de decisiones",
  deep_scanner_triage: "Triaje profundo de analizadores",
  functional_qa: "QA funcional",
  platform_parity: "Paridad de plataformas",
  deployment_and_infrastructure: "Despliegue e infraestructura",
  architecture_and_data_flow: "Arquitectura y flujo de datos",
  developer_delivery_process: "Proceso de entrega del equipo",
  stakeholder_and_business_alignment: "Alineación con negocio y partes interesadas",
  requirements_traceability: "Trazabilidad de requisitos",
  historical_trends_and_change_failure: "Tendencias históricas y fallos de cambio",
  six_month_roadmap: "Hoja de ruta de seis meses",
  staffing_sequencing_and_cost: "Personal, secuencia y costo",
  risk_reduction_and_executive_briefing: "Reducción de riesgo e informe ejecutivo",
  final_comprehensive_report_generation: "Informe Integral final",
  cross_format_truth_verification: "Verificación de veracidad entre formatos",
  human_review_request: "Solicitud de revisión humana",
  client_acceptance_pending: "Aceptación del cliente pendiente",
};

const EN: Copy = {
  heroEyebrow: "NICO ASSESSMENTS",
  title: "One workspace. Two evidence-bound services.",
  lead: "Choose Express for a fast technical baseline or Comprehensive for the complete snapshot-bound assessment. Both use native backend identities and stop at required human review.",
  coverage: "Coverage calculated after run",
  warning: "Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.",
  repo: "Repository owner/name or GitHub URL",
  repoPlaceholder: "your-org/your-repo",
  client: "Client name, optional",
  project: "Project name, optional",
  confirm: "I confirm I own this target or have explicit permission to assess it.",
  run: "Run",
  state: "AUTOMATED RUN STATE",
  stage: "Current stage",
  progress: "Progress",
  elapsed: "Elapsed",
  checks: "Status checks",
  runId: "Run ID",
  commit: "Immutable commit",
  scanner: "Scanner",
  report: "Report",
  review: "Human review",
  maturity: "Maturity signal",
  score: "Technical score",
  durable: "Persistence",
  yes: "Durable",
  recorded: "Recorded",
  pending: "Pending",
  awaitingStage: "Awaiting stage",
  awaitingScanner: "Awaiting scanner completion",
  reviewAfterReport: "Begins after automated report",
  maturityAfterScoring: "Calculated after scoring",
  notScoredYet: "Not scored yet",
  reviewLimitedNotScored: "Review limited · Not scored",
  unavailableStatus: "Unavailable",
  evidenceLimitations: "Evidence limitations",
  baselineNotEstablished: "Baseline not established",
  inputNotProvided: "Input not provided",
  notApplicable: "Not applicable",
  runtimeAcceptanceNotProvided: "Runtime acceptance not provided",
  awaitingCommercialInputs: "Awaiting commercial inputs",
  copyValue: "Copy full value",
  valueCopied: "Copied",
  notScored: "Not scored",
  notVerified: "Not verified",
  copied: "Markdown copied",
  copy: "Copy Markdown",
  download: "Download final PDF",
  select: "Select a service and run an authorized repository.",
  unavailable: "Unavailable or limited evidence",
  evidence: "Evidence",
  findings: "Findings",
  stepEvidence: "Step evidence",
  reviewNotice: "The final report is complete. The team must review the exact evidence-bound package and approve it before client delivery; no separate report rewrite is required.",
  backendError: "The assessment backend could not be reached from this deployment.",
  authError: "Confirm that you own the target or have explicit permission to assess it.",
  invalidJson: "The assessment endpoint returned invalid JSON.",
  runIdMissing: "The assessment response did not include a run ID.",
  expressComplete: "Express completed its evidence, scoring, reporting, and truth-gate stages. Human review remains required before delivery.",
  comprehensiveReview: "Comprehensive completed every automated stage and stopped at the required human-review gate.",
  stopped: "The assessment stopped because a required stage failed or was blocked.",
  pdfMissing: "A PDF was not returned for this final report package.",
  services: {
    express: {
      label: "Express",
      eyebrow: "EXPRESS ASSESSMENT",
      heading: "Fast evidence-bound technical baseline",
      summary: "Repository evidence, calibrated scoring, repair intelligence, and a complete final report prepared for human approval.",
      instructionsTitle: "Express instructions",
      instructions: [
        "Publishes real backend stages and evidence status.",
        "Uses the exact run's reconciled evidence.",
        "Discloses missing or failed evidence and requires human review.",
      ],
    },
    comprehensive: {
      label: "Comprehensive",
      eyebrow: "COMPREHENSIVE ASSESSMENT",
      heading: "Complete snapshot-bound technical diligence",
      summary: "One immutable commit, modern scanners, functional and platform review, architecture and delivery analysis, six-month roadmap, staffing plan, executive briefing, and one review-gated report package.",
      instructionsTitle: "Comprehensive instructions",
      instructions: [
        "Captures one immutable commit before evidence collection.",
        "Continues the same native run through every core and deep stage.",
        "Discloses unavailable evidence rather than fabricating it.",
        "Blocks client delivery until an authorized human approves the exact package.",
      ],
    },
  },
  phases: {idle: "Not started", starting: "Starting", running: "Running automatically", review_required: "Human review required", complete: "Complete", failed: "Run failed or blocked", timed_out: "Continuation timed out"},
  stageLabels: EN_STAGE_LABELS,
};

const ES: Copy = {
  heroEyebrow: "EVALUACIONES NICO",
  title: "Un espacio de trabajo. Dos servicios vinculados a evidencia.",
  lead: "Elige Express para una línea base técnica rápida o Integral para la evaluación completa vinculada a una instantánea exacta. Ambos usan identidades nativas del backend y se detienen ante la revisión humana obligatoria.",
  coverage: "Cobertura calculada después de la ejecución",
  warning: "Evalúa únicamente repositorios que te pertenezcan o para los que tengas autorización explícita. NICO realiza evaluaciones defensivas de solo lectura y no efectúa cambios destructivos.",
  repo: "Propietario/nombre del repositorio o URL de GitHub",
  repoPlaceholder: "tu-organización/tu-repositorio",
  client: "Nombre del cliente, opcional",
  project: "Nombre del proyecto, opcional",
  confirm: "Confirmo que soy propietario de este objetivo o que tengo autorización explícita para evaluarlo.",
  run: "Ejecutar",
  state: "ESTADO DE EJECUCIÓN AUTOMATIZADA",
  stage: "Etapa actual",
  progress: "Progreso",
  elapsed: "Tiempo transcurrido",
  checks: "Comprobaciones de estado",
  runId: "ID de ejecución",
  commit: "Commit inmutable",
  scanner: "Analizadores",
  report: "Informe",
  review: "Revisión humana",
  maturity: "Señal de madurez",
  score: "Puntuación técnica",
  durable: "Persistencia",
  yes: "Durable",
  recorded: "Registrado",
  pending: "Pendiente",
  awaitingStage: "En espera de la etapa",
  awaitingScanner: "En espera de que finalicen los analizadores",
  reviewAfterReport: "Comienza después del informe automatizado",
  maturityAfterScoring: "Se calcula después de la puntuación",
  notScoredYet: "Aún sin puntuación",
  reviewLimitedNotScored: "Revisión limitada · Sin puntuación",
  unavailableStatus: "No disponible",
  evidenceLimitations: "Limitaciones de evidencia",
  baselineNotEstablished: "Línea base aún no establecida",
  inputNotProvided: "Información no proporcionada",
  notApplicable: "No aplica",
  runtimeAcceptanceNotProvided: "Aceptación en ejecución no proporcionada",
  awaitingCommercialInputs: "En espera de datos comerciales",
  copyValue: "Copiar valor completo",
  valueCopied: "Copiado",
  notScored: "Sin puntuación",
  notVerified: "No verificado",
  copied: "Markdown copiado",
  copy: "Copiar Markdown",
  download: "Descargar PDF final",
  select: "Selecciona un servicio y ejecuta un repositorio autorizado.",
  unavailable: "Evidencia no disponible o limitada",
  evidence: "Evidencia",
  findings: "Hallazgos",
  stepEvidence: "Evidencia de la etapa",
  reviewNotice: "El informe final está completo. El equipo debe revisar el paquete exacto vinculado a evidencia y aprobarlo antes de entregarlo al cliente; no es necesario rehacer el informe.",
  backendError: "No se pudo acceder al backend de evaluación desde este despliegue.",
  authError: "Confirma que eres propietario del objetivo o que tienes autorización explícita para evaluarlo.",
  invalidJson: "El endpoint de evaluación devolvió JSON no válido.",
  runIdMissing: "La respuesta de la evaluación no incluyó un ID de ejecución.",
  expressComplete: "Express completó las etapas de evidencia, puntuación, informe y control de veracidad. Aún se requiere revisión humana antes de la entrega.",
  comprehensiveReview: "Integral completó todas las etapas automatizadas y se detuvo ante la revisión humana obligatoria.",
  stopped: "La evaluación se detuvo porque una etapa obligatoria falló o quedó bloqueada.",
  pdfMissing: "No se devolvió un PDF para este paquete de informe final.",
  services: {
    express: {
      label: "Express",
      eyebrow: "EVALUACIÓN EXPRESS",
      heading: "Línea base técnica rápida vinculada a evidencia",
      summary: "Evidencia del repositorio, puntuación calibrada, inteligencia de reparación y un informe final completo preparado para aprobación humana.",
      instructionsTitle: "Instrucciones de Express",
      instructions: [
        "Publica etapas reales del backend y el estado de la evidencia.",
        "Usa la evidencia conciliada de la ejecución exacta.",
        "Declara la evidencia ausente o fallida y requiere revisión humana.",
      ],
    },
    comprehensive: {
      label: "Integral",
      eyebrow: "EVALUACIÓN INTEGRAL",
      heading: "Diligencia técnica completa vinculada a una instantánea",
      summary: "Un commit inmutable, analizadores modernos, revisión funcional y de plataformas, arquitectura y entrega, hoja de ruta de seis meses, plan de personal, informe ejecutivo y un paquete final sujeto a revisión.",
      instructionsTitle: "Instrucciones de la evaluación Integral",
      instructions: [
        "Captura un commit inmutable antes de recopilar evidencia.",
        "Continúa la misma ejecución nativa por todas las etapas principales y profundas.",
        "Declara la evidencia no disponible en lugar de inventarla.",
        "Bloquea la entrega hasta que una persona autorizada apruebe el paquete exacto.",
      ],
    },
  },
  phases: {idle: "No iniciada", starting: "Iniciando", running: "Ejecutándose automáticamente", review_required: "Se requiere revisión humana", complete: "Completa", failed: "La ejecución falló o está bloqueada", timed_out: "La continuación agotó el tiempo"},
  stageLabels: ES_STAGE_LABELS,
};

function normalizeService(value: string | null): Service {
  return ["comprehensive", "mid", "full", "deep"].includes(String(value || "")) ? "comprehensive" : "express";
}

function scopeId(prefix: string, value: string, fallback: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

function statusClass(status?: string): string {
  const value = String(status || "").toLowerCase();
  if (["green", "complete", "completed", "attached", "verified", "review_required"].includes(value)) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "ready", "starting", "skipped"].includes(value)) return "status yellow";
  if (["red", "failed", "blocked", "error", "unavailable", "timed_out", "interrupted", "rejected"].includes(value)) return "status red";
  return "status gray";
}

function compactIdentifier(value: string, lead = 12, tail = 8): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}…${normalized.slice(-tail)}`;
}

function formatStatus(status: unknown, copy: Copy): string {
  const raw = String(status || "").trim();
  const value = raw.toLowerCase().replace(/[\s-]+/g, "_");
  if (!value) return copy.notVerified;
  if (value.includes("review_limited") && value.includes("not_scored")) return copy.reviewLimitedNotScored;
  if (["complete", "completed", "attached", "verified", "green"].includes(value)) return copy.phases.complete;
  if (["review_required", "human_review_required"].includes(value)) return copy.phases.review_required;
  if (["running", "starting", "in_progress"].includes(value)) return copy.phases.running;
  if (["pending", "queued", "planned", "ready", "not_started"].includes(value)) return copy.awaitingStage;
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return copy.phases.failed;
  if (["timed_out", "timeout"].includes(value)) return copy.phases.timed_out;
  if (value.includes("unavailable") || value === "not_available") return copy.unavailableStatus;
  if (value === "not_applicable") return copy.notApplicable;
  return value.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function IdentifierValue({value, fallback, copy}: {value?: string; fallback: string; copy: Copy}) {
  const [didCopy, setDidCopy] = useState(false);
  const fullValue = String(value || "").trim();

  async function copyFullValue(): Promise<void> {
    if (!fullValue) return;
    try {
      await navigator.clipboard.writeText(fullValue);
      setDidCopy(true);
      window.setTimeout(() => setDidCopy(false), 1800);
    } catch {
      setDidCopy(false);
    }
  }

  return <span className="nico-identifier-value">
    <code title={fullValue || fallback}>{fullValue ? compactIdentifier(fullValue) : fallback}</code>
    {fullValue ? <button type="button" onClick={copyFullValue} aria-label={`${copy.copyValue}: ${fullValue}`}>{didCopy ? copy.valueCopied : copy.copyValue}</button> : null}
  </span>;
}

function api(path: string): string {
  return new URL(`/api/nico${path}`, window.location.origin).href;
}

function stage(result: Result | null, id: string): Stage | null {
  const value = result?.record?.stage_results?.[id];
  return value && typeof value === "object" ? value : null;
}

function evidenceRecord(value: Evidence | undefined): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function assessmentFor(service: Service, result: Result | null): Assessment | null {
  if (!result) return null;
  if (service === "express") return result;
  return stage(result, "final_comprehensive_report_generation")?.assessment
    || stage(result, "evidence_reconciliation_and_scoring")?.assessment
    || result.assessment
    || null;
}

function reportFor(service: Service, result: Result | null): Report | null {
  if (!result) return null;
  if (service === "express") return result.reports || null;
  for (const id of ["final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation"]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    if (report) return report;
  }
  return result.reports || null;
}

function terminal(service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return "failed";
  if (service === "express" && ["complete", "completed"].includes(value)) return "complete";
  if (service === "comprehensive" && (value === "review_required" || (["complete", "completed"].includes(value) && result.human_review_required !== false))) return "review_required";
  return null;
}

async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function json(response: Response, copy: Copy): Promise<Result> {
  let data: Result & {detail?: string | {message?: string; code?: string}; error?: string};
  try {
    data = await response.json() as Result & {detail?: string | {message?: string; code?: string}; error?: string};
  } catch {
    throw new Error(copy.invalidJson);
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.message || data.detail?.code;
    throw new Error(detail || data.error || `${copy.backendError} (${response.status})`);
  }
  return data;
}

function savePdf(encoded: string, filename: string): void {
  const binary = window.atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const blob = new Blob([bytes.buffer], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function List({items, empty}: {items?: string[]; empty: string}) {
  return items?.length
    ? <ul className="tight-list">{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
    : <p className="muted">{empty}</p>;
}

export default function AssessmentWorkspace({locale = "en"}: {locale?: Locale}) {
  const copy = locale === "es-MX" ? ES : EN;
  const [service, setService] = useState<Service>("express");
  const [repository, setRepository] = useState("");
  const [client, setClient] = useState("");
  const [project, setProject] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const sequence = useRef(0);

  useEffect(() => {
    document.documentElement.lang = locale;
    const url = new URL(window.location.href);
    const next = normalizeService(url.searchParams.get("tier"));
    setService(next);
    if (url.searchParams.get("tier") !== next) {
      url.searchParams.set("tier", next);
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
    return () => { sequence.current += 1; };
  }, [locale]);

  useEffect(() => {
    if (!started || !["starting", "running"].includes(phase)) return;
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [started, phase]);

  const serviceCopy = copy.services[service];
  const assessment = useMemo(() => assessmentFor(service, result), [service, result]);
  const report = useMemo(() => reportFor(service, result), [service, result]);
  const running = phase === "starting" || phase === "running";
  const progressItems = service === "express"
    ? result?.progress || []
    : Object.entries(result?.record?.stage_results || {}).map(([stepId, value]) => ({
        step: stepId,
        status: value.status,
        message: value.message || value.summary,
        evidence: value.evidence && !Array.isArray(value.evidence) ? value.evidence : undefined,
      }));
  const activeProgress = progressItems.find((item) => ["queued", "running", "pending", "planned", "starting"].includes(String(item.status || "").toLowerCase()));
  const stageId = String(result?.current_stage || result?.record?.current_stage || activeProgress?.step || "");
  const percentValue = Number(result?.progress_percent ?? result?.record?.progress_percent);
  const percent = phase === "complete" || phase === "review_required"
    ? 100
    : Number.isFinite(percentValue)
      ? Math.max(0, Math.min(100, percentValue))
      : running ? 5 : 0;
  const coverage = assessment?.evidence_coverage;
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent))
    ? `${coverage.label || copy.evidence}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
    : copy.coverage;
  const scoreValue = assessment?.maturity_signal?.presented_score ?? assessment?.maturity_signal?.score;
  const scoreLabel = typeof scoreValue === "number" && Number.isFinite(scoreValue) ? `${scoreValue}/100` : running ? copy.notScoredYet : copy.notScored;
  const snapshotEvidence = evidenceRecord(stage(result, "immutable_repository_snapshot")?.evidence);
  const repositoryEvidence = evidenceRecord(stage(result, "repository_and_delivery_evidence")?.evidence);
  const immutableCommit = result?.commit_sha
    || result?.repository_snapshot?.commit_sha
    || String(snapshotEvidence.commit_sha || snapshotEvidence.snapshot_commit_sha || repositoryEvidence.snapshot_commit_sha || "—");
  const scannerRawStatus = service === "express"
    ? result?.scanner_evidence?.scanner_status || result?.scanner?.status || result?.scanner_evidence?.status || (running ? "running" : "pending")
    : stage(result, "dependency_security_static_analysis")?.status || stage(result, "deep_scanner_triage")?.status || (running ? "running" : "pending");
  const scannerUnavailable = String(scannerRawStatus || "").toLowerCase().includes("unavailable");
  const scannerStatus = running && scannerUnavailable ? copy.awaitingScanner : formatStatus(scannerRawStatus, copy);
  const reportStatus = report?.markdown || report?.html || report?.pdf_base64
    ? copy.phases.complete
    : running ? copy.awaitingScanner : copy.awaitingStage;
  const reviewStatus = phase === "review_required"
    ? copy.phases.review_required
    : running ? copy.reviewAfterReport : copy.awaitingStage;
  const maturityRawStatus = assessment?.maturity_signal?.level;
  const maturityUnavailable = String(maturityRawStatus || "").toLowerCase().includes("unavailable");
  const maturityStatus = running && (!maturityRawStatus || maturityUnavailable)
    ? copy.maturityAfterScoring
    : formatStatus(maturityRawStatus || (running ? "pending" : "not_started"), copy);

  function choose(next: Service): void {
    if (running) return;
    setService(next);
    setResult(null);
    setPhase("idle");
    setMessage("");
    setError("");
    setAttempt(0);
    setStarted(null);
    setElapsed(0);
    setCopied(false);
    const url = new URL(window.location.href);
    url.searchParams.set("tier", next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new CustomEvent("nico:assessment-tier-selected", {detail: {tier: next}}));
  }

  async function continueRun(selected: Service, initial: Result, scope: Scope, token: number): Promise<void> {
    let current = initial;
    for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1) {
      if (token !== sequence.current) return;
      setResult(current);
      const stable = terminal(selected, current);
      if (stable) {
        setPhase(stable);
        setAttempt(count);
        setMessage(stable === "review_required" ? copy.comprehensiveReview : stable === "complete" ? copy.expressComplete : copy.stopped);
        return;
      }

      setPhase("running");
      setAttempt(count);
      const currentStageId = String(current.current_stage || current.record?.current_stage || "");
      setMessage(`${copy.services[selected].label}: ${copy.stageLabels[currentStageId] || currentStageId.replaceAll("_", " ") || copy.phases.running}.`);
      const runId = String(current.run_id || "");
      if (!runId) throw new Error(copy.runIdMissing);

      if (selected === "comprehensive") {
        current = await json(await fetch(api(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({max_stages: 1}),
          cache: "no-store",
        }), copy);
      } else {
        await wait(POLL_INTERVAL_MS);
        current = await json(await fetch(api(`/assessment/express-run/${encodeURIComponent(runId)}/status`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({customer_id: current.customer_id || scope.customerId, project_id: current.project_id || scope.projectId}),
          cache: "no-store",
        }), copy);
      }
      await wait(POLL_INTERVAL_MS);
    }
    setResult(current);
    setPhase("timed_out");
    setMessage(copy.phases.timed_out);
  }

  async function run(): Promise<void> {
    if (!authorized) {
      setError(copy.authError);
      return;
    }
    const token = sequence.current + 1;
    sequence.current = token;
    const scope = {
      customerId: scopeId("customer", client, "default_customer"),
      projectId: scopeId("project", project, "default_project"),
    };
    setPhase("starting");
    setResult(null);
    setError("");
    setMessage(`${copy.phases.starting}: ${serviceCopy.label}`);
    setAttempt(0);
    setStarted(Date.now());
    setElapsed(0);
    setCopied(false);

    const body = {
      repository,
      customer_id: scope.customerId,
      project_id: scope.projectId,
      client_name: client,
      project_name: project,
      authorized_by: "public_assessment_requester",
      authorization_scope: "authorized defensive repository assessment",
      authorization_confirmed: true,
      authorized: true,
      timeframe_days: 180,
    };

    try {
      const path = service === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake";
      const payload = service === "express" ? {...body, assessment_mode: "express"} : body;
      const data = await json(await fetch(api(path), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
        cache: "no-store",
      }), copy);
      if (token !== sequence.current) return;
      setResult(data);
      await continueRun(service, data, scope, token);
    } catch (caught) {
      if (token !== sequence.current) return;
      setPhase("failed");
      setError(caught instanceof Error ? caught.message : copy.backendError);
      setMessage(copy.backendError);
    }
  }

  async function copyMarkdown(): Promise<void> {
    if (!report?.markdown) return;
    await navigator.clipboard.writeText(report.markdown);
    setCopied(true);
  }

  function downloadPdf(): void {
    if (!report?.pdf_base64) {
      setError(report?.pdf_error || copy.pdfMissing);
      return;
    }
    savePdf(report.pdf_base64, report.pdf_filename || `nico-${service}-assessment.pdf`);
  }

  return <main className="shell" data-assessment-service-count="2" data-assessment-locale={locale}>
    <section className="hero"><p className="eyebrow">{copy.heroEyebrow}</p><h1>{copy.title}</h1><p className="lead">{copy.lead}</p></section>
    <section id="assessment" className="section panel">
      <div className="section-head"><div><p className="eyebrow">{serviceCopy.eyebrow}</p><h2>{serviceCopy.heading}</h2></div><span className="status gray">{coverageLabel}</span></div>
      <p className="summary-box">{serviceCopy.summary}</p>
      <div className={styles.tierGrid} aria-label="Assessment type">{(["express", "comprehensive"] as Service[]).map((value) => <button type="button" key={value} className={service === value ? "primary-button" : ""} aria-pressed={service === value} disabled={running} onClick={() => choose(value)}>{copy.services[value].label}</button>)}</div>
      <details className="help-details"><summary>{serviceCopy.instructionsTitle}</summary><ul>{serviceCopy.instructions.map((item) => <li key={item}>{item}</li>)}</ul></details>
      <p className="warning-box">{copy.warning}</p>
      <div className="form-grid"><label>{copy.repo}<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={copy.repoPlaceholder} disabled={running} /></label><label>{copy.client}<input value={client} onChange={(event) => setClient(event.target.value)} disabled={running} /></label><label>{copy.project}<input value={project} onChange={(event) => setProject(event.target.value)} disabled={running} /></label></div>
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} disabled={running} />{copy.confirm}</label>
      <button type="button" className="primary-button" disabled={!authorized || !repository.trim() || running} onClick={run}>{running ? `${copy.phases.running}: ${serviceCopy.label}` : `${copy.run} ${serviceCopy.label}`}</button>
      {error ? <p className="error-box">{error}</p> : null}
    </section>
    <section className="section panel" aria-live="polite">
      <div className="section-head"><div><p className="eyebrow">{copy.state}</p><h2 title={result?.run_id}>{result?.run_id ? compactIdentifier(result.run_id, 18, 8) : copy.phases[phase]}</h2></div><span className={statusClass(phase)}>{copy.phases[phase]}</span></div>
      <p className={phase === "failed" ? "error-box" : phase === "review_required" ? "warning-box" : "summary-box"}>{message || copy.select}</p>
      {running ? <><div className={styles.progressMeta}><span><b>{copy.stage}</b>{copy.stageLabels[stageId] || stageId.replaceAll("_", " ") || copy.phases[phase]}</span><span><b>{copy.progress}</b>{Math.round(percent)}%</span><span><b>{copy.elapsed}</b>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span><span><b>{copy.checks}</b>{attempt}</span></div><div className={styles.progressBar} role="progressbar" aria-label={`${copy.stageLabels[stageId] || stageId || copy.phases[phase]} ${copy.progress}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{width: `${Math.max(2, Math.min(100, percent))}%`}} /></div></> : null}
      {result ? <>
        <div className="grid four target-grid">
          <article><b>{copy.runId}</b><IdentifierValue value={result.run_id} fallback={copy.notVerified} copy={copy} /></article>
          <article><b>{copy.commit}</b><IdentifierValue value={immutableCommit === "—" ? "" : immutableCommit} fallback={copy.notVerified} copy={copy} /></article>
          <article><b>{copy.scanner}</b><span>{scannerStatus}</span></article>
          <article><b>{copy.report}</b><span>{reportStatus}</span></article>
        </div>
        <div className="grid four target-grid">
          <article><b>{copy.review}</b><span>{reviewStatus}</span></article>
          <article><b>{copy.maturity}</b><span>{maturityStatus}</span></article>
          <article><b>{copy.score}</b><span>{scoreLabel}</span></article>
          <article><b>{copy.durable}</b><span>{result.persistence?.durable ? copy.yes : result.persistence?.recorded ? copy.recorded : copy.notVerified}</span></article>
        </div>
        {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
        {progressItems.length ? <div className={styles.timeline}>{progressItems.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}><div className="result-head"><b>{copy.stageLabels[String(item.step || "")] || String(item.step || copy.stage).replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{formatStatus(item.status, copy)}</span></div><p>{item.message || copy.notVerified}</p>{item.evidence ? <details className="help-details"><summary>{copy.stepEvidence}</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}</article>)}</div> : null}
        {assessment?.sections?.length ? <div className="results-grid">{assessment.sections.map((section, index) => {
          const value = section.presented_score ?? section.score;
          const score = typeof value === "number" ? `${value}/100` : copy.notScored;
          const rawState = section.presented_status || section.status || "unknown";
          const displayState = formatStatus(rawState, copy);
          const badge = typeof value === "number" ? `${displayState} · ${score}` : displayState === copy.reviewLimitedNotScored ? displayState : `${displayState} · ${score}`;
          return <article className="result-card" key={section.id || index}><div className="result-head"><b>{section.label || String(section.id || "").replaceAll("_", " ")}</b><span className={statusClass(rawState)}>{badge}</span></div><p>{section.summary}</p><details className="help-details"><summary>{copy.evidence} ({section.evidence?.length || 0})</summary><List items={section.evidence} empty={copy.notVerified} /></details>{section.findings?.length ? <details className="help-details"><summary>{copy.findings} ({section.findings.length})</summary><List items={section.findings} empty={copy.notVerified} /></details> : null}{section.unavailable?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({section.unavailable.length})</summary><List items={section.unavailable} empty={copy.notVerified} /></details> : null}</article>;
        })}</div> : null}
        <div className="report-actions"><button type="button" disabled={!report?.markdown} onClick={copyMarkdown}>{copy.copy}</button><button type="button" disabled={!report?.pdf_base64} onClick={downloadPdf}>{copy.download}</button>{copied ? <span className="muted">{copy.copied}</span> : null}</div>
        {phase === "review_required" ? <p className="warning-box">{copy.reviewNotice}</p> : null}
        {assessment?.unavailable_data_notes?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({assessment.unavailable_data_notes.length})</summary><List items={assessment.unavailable_data_notes} empty={copy.notVerified} /></details> : null}
      </> : null}
    </section>
  </main>;
}
