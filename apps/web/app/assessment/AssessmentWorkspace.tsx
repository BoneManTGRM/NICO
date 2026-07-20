"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import styles from "./assessment.module.css";

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 360;

type Locale = "en" | "es-MX";
type AssessmentTier = "express" | "comprehensive";
type RunPhase = "idle" | "starting" | "running" | "review_required" | "complete" | "failed" | "timed_out";
type EvidenceCoverage = {percent?: number; calculated?: boolean; label?: string; numerator?: number; denominator?: number};
type Section = {
  id?: string;
  label?: string;
  score?: number | null;
  presented_score?: number | null;
  status?: string;
  presented_status?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
  confidence?: string;
};
type ProgressItem = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
type ReportPackage = {
  markdown?: string;
  html?: string;
  pdf_base64?: string;
  pdf_filename?: string;
  pdf_error?: string;
  report_id?: string;
  pdf_sha256?: string;
};
type AssessmentDocument = {
  status?: string;
  executive_summary?: string;
  maturity_signal?: {level?: string; score?: number; presented_score?: number; summary?: string; evidence_readiness_score?: number};
  evidence_coverage?: EvidenceCoverage;
  sections?: Section[];
  findings?: string[];
  repairs?: string[];
  unavailable_data_notes?: string[];
  human_review_required?: boolean;
  client_ready?: boolean;
};
type StageResult = {
  stage_id?: string;
  status?: string;
  message?: string;
  summary?: string;
  evidence?: Record<string, unknown> | string[];
  unavailable_data_notes?: string[];
  report_package?: ReportPackage;
  reports?: ReportPackage;
  assessment?: AssessmentDocument;
  [key: string]: unknown;
};
type ComprehensiveRecord = {
  service_id?: string;
  status?: string;
  current_stage?: string | null;
  completed_stages?: string[];
  stage_results?: Record<string, StageResult>;
  progress_percent?: number;
  revision?: number;
  terminal?: boolean;
  integrity_sha256?: string;
};
type AssessmentResult = AssessmentDocument & {
  service_id?: string;
  status?: string;
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  evidence_ledger_id?: string;
  customer_id?: string;
  project_id?: string;
  generated_at?: string;
  updated_at?: string;
  current_stage?: string | null;
  progress_percent?: number;
  progress?: ProgressItem[];
  assessment?: AssessmentDocument;
  record?: ComprehensiveRecord;
  repository_snapshot?: {snapshot_id?: string; commit_sha?: string};
  repository_evidence?: {status?: string; evidence_id?: string; snapshot_commit_sha?: string; unavailable_data_notes?: string[]};
  scanner?: {scan_id?: string; status?: string};
  scanner_evidence?: {status?: string; scan_id?: string; scanner_status?: string; unavailable_data_notes?: string[]};
  reports?: ReportPackage;
  persistence?: {recorded?: boolean; durable?: boolean; adapter?: string; note?: string};
  human_review_required?: boolean;
  client_ready?: boolean;
  client_delivery_allowed?: boolean;
  revision?: number;
  integrity_sha256?: string;
};
type RunScope = {customerId: string; projectId: string};

type Copy = {
  heroEyebrow: string;
  heroTitle: string;
  heroLead: string;
  coveragePending: string;
  authorizationWarning: string;
  repositoryLabel: string;
  repositoryPlaceholder: string;
  clientLabel: string;
  clientPlaceholder: string;
  projectLabel: string;
  projectPlaceholder: string;
  authorizationConfirm: string;
  backendUnavailable: string;
  runStateEyebrow: string;
  currentStage: string;
  progress: string;
  elapsed: string;
  checks: string;
  runId: string;
  immutableCommit: string;
  scanner: string;
  report: string;
  humanReview: string;
  maturity: string;
  technicalScore: string;
  evidenceReadiness: string;
  durableRecord: string;
  notScored: string;
  pending: string;
  complete: string;
  recordedNotDurable: string;
  notVerified: string;
  copyMarkdown: string;
  downloadPdf: string;
  stepEvidence: string;
  evidence: string;
  findings: string;
  unavailable: string;
  reviewNotice: string;
  startError: string;
  authorizationError: string;
  timeoutNotice: string;
  noItems: string;
  tiers: Record<AssessmentTier, {label: string; eyebrow: string; title: string; summary: string; instructionsTitle: string; instructions: string[]}>;
  phase: Record<RunPhase, string>;
  stageLabels: Record<string, string>;
};

const EN: Copy = {
  heroEyebrow: "NICO ASSESSMENTS",
  heroTitle: "One workspace. Two evidence-bound services.",
  heroLead: "Choose Express for a fast technical baseline or Comprehensive for the complete snapshot-bound assessment. Both use real backend identities and stop at required human review.",
  coveragePending: "Coverage calculated after run",
  authorizationWarning: "Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.",
  repositoryLabel: "Repository owner/name or GitHub URL",
  repositoryPlaceholder: "your-org/your-repo",
  clientLabel: "Client name, optional",
  clientPlaceholder: "Client name",
  projectLabel: "Project name, optional",
  projectPlaceholder: "Project name",
  authorizationConfirm: "I confirm I own this target or have explicit permission to assess it.",
  backendUnavailable: "The assessment backend could not be reached from this deployment.",
  runStateEyebrow: "AUTOMATED RUN STATE",
  currentStage: "Current stage",
  progress: "Progress",
  elapsed: "Elapsed",
  checks: "Status checks",
  runId: "Run ID",
  immutableCommit: "Immutable commit",
  scanner: "Scanner",
  report: "Report",
  humanReview: "Human review",
  maturity: "Maturity signal",
  technicalScore: "Technical score",
  evidenceReadiness: "Evidence readiness",
  durableRecord: "Durable record",
  notScored: "Not scored",
  pending: "Pending",
  complete: "Complete",
  recordedNotDurable: "Recorded, not durable",
  notVerified: "Not verified",
  copyMarkdown: "Copy Markdown",
  downloadPdf: "Download draft PDF",
  stepEvidence: "Step evidence",
  evidence: "Evidence",
  findings: "Findings",
  unavailable: "Unavailable or limited evidence",
  reviewNotice: "Automated assessment work is complete. NICO did not approve findings, create a delivery link, or deliver the report. A human must review the exact evidence-bound artifact.",
  startError: "Assessment failed.",
  authorizationError: "Confirm that you own the target or have explicit permission to assess it.",
  timeoutNotice: "Automatic continuation reached its bounded limit. The exact run identity is preserved; do not start a duplicate run unless the saved run is terminal.",
  noItems: "No items returned.",
  tiers: {
    express: {
      label: "Express",
      eyebrow: "EXPRESS ASSESSMENT",
      title: "Fast evidence-bound technical baseline",
      summary: "Repository evidence, calibrated scoring, decision-ready repair intelligence, and a downloadable draft report.",
      instructionsTitle: "Express instructions",
      instructions: [
        "Express publishes real backend stages and evidence status.",
        "The report is generated from the exact run's reconciled evidence.",
        "Missing or failed evidence remains disclosed and human review is required.",
      ],
    },
    comprehensive: {
      label: "Comprehensive",
      eyebrow: "COMPREHENSIVE ASSESSMENT",
      title: "Complete snapshot-bound technical diligence",
      summary: "One immutable commit, modern scanners, functional and platform review, architecture and delivery analysis, six-month roadmap, staffing plan, executive briefing, and one review-gated report package.",
      instructionsTitle: "Comprehensive instructions",
      instructions: [
        "Comprehensive captures one immutable commit before collecting or scanning evidence.",
        "The same run identity continues through every core and deep assessment stage.",
        "Unavailable stakeholder or runtime evidence is disclosed rather than fabricated.",
        "Client delivery remains blocked until an authorized human approves the exact report package.",
      ],
    },
  },
  phase: {
    idle: "Not started",
    starting: "Starting",
    running: "Running automatically",
    review_required: "Human review required",
    complete: "Complete",
    failed: "Run failed or blocked",
    timed_out: "Continuation timed out",
  },
  stageLabels: {
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
    approval_request: "Human-review request",
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
  },
};

const ES: Copy = {
  ...EN,
  heroEyebrow: "EVALUACIONES NICO",
  heroTitle: "Un espacio de trabajo. Dos servicios vinculados a evidencia.",
  heroLead: "Elige Express para una línea base técnica rápida o Integral para la evaluación completa vinculada a una instantánea exacta. Ambos servicios usan identidades reales del backend y se detienen ante la revisión humana obligatoria.",
  coveragePending: "Cobertura calculada después de la ejecución",
  authorizationWarning: "Evalúa únicamente repositorios que te pertenezcan o para los que tengas autorización explícita. NICO realiza evaluaciones defensivas de solo lectura y no efectúa cambios destructivos.",
  repositoryLabel: "Propietario/nombre del repositorio o URL de GitHub",
  repositoryPlaceholder: "tu-organización/tu-repositorio",
  clientLabel: "Nombre del cliente, opcional",
  clientPlaceholder: "Nombre del cliente",
  projectLabel: "Nombre del proyecto, opcional",
  projectPlaceholder: "Nombre del proyecto",
  authorizationConfirm: "Confirmo que soy propietario de este objetivo o que tengo autorización explícita para evaluarlo.",
  backendUnavailable: "No se pudo acceder al backend de evaluación desde este despliegue.",
  runStateEyebrow: "ESTADO DE EJECUCIÓN AUTOMATIZADA",
  currentStage: "Etapa actual",
  progress: "Progreso",
  elapsed: "Tiempo transcurrido",
  checks: "Comprobaciones de estado",
  runId: "ID de ejecución",
  immutableCommit: "Commit inmutable",
  scanner: "Analizadores",
  report: "Informe",
  humanReview: "Revisión humana",
  maturity: "Señal de madurez",
  technicalScore: "Puntuación técnica",
  evidenceReadiness: "Preparación de evidencia",
  durableRecord: "Registro durable",
  notScored: "Sin puntuación",
  pending: "Pendiente",
  complete: "Completa",
  recordedNotDurable: "Registrado, no durable",
  notVerified: "No verificado",
  copyMarkdown: "Copiar Markdown",
  downloadPdf: "Descargar PDF preliminar",
  stepEvidence: "Evidencia de la etapa",
  evidence: "Evidencia",
  findings: "Hallazgos",
  unavailable: "Evidencia no disponible o limitada",
  reviewNotice: "El trabajo automatizado terminó. NICO no aprobó los hallazgos, no creó un enlace de entrega y no entregó el informe. Una persona autorizada debe revisar el artefacto exacto vinculado a evidencia.",
  startError: "La evaluación falló.",
  authorizationError: "Confirma que eres propietario del objetivo o que tienes autorización explícita para evaluarlo.",
  timeoutNotice: "La continuación automática alcanzó su límite. La identidad exacta de la ejecución se conserva; no inicies una ejecución duplicada salvo que la guardada sea terminal.",
  noItems: "No se devolvieron elementos.",
  tiers: {
    express: {
      label: "Express",
      eyebrow: "EVALUACIÓN EXPRESS",
      title: "Línea base técnica rápida vinculada a evidencia",
      summary: "Evidencia del repositorio, puntuación calibrada, inteligencia de reparación lista para decisiones y un informe preliminar descargable.",
      instructionsTitle: "Instrucciones de Express",
      instructions: [
        "Express publica etapas reales del backend y el estado de la evidencia.",
        "El informe se genera a partir de la evidencia conciliada de la ejecución exacta.",
        "La evidencia ausente o fallida permanece visible y se requiere revisión humana.",
      ],
    },
    comprehensive: {
      label: "Integral",
      eyebrow: "EVALUACIÓN INTEGRAL",
      title: "Diligencia técnica completa vinculada a una instantánea",
      summary: "Un commit inmutable, analizadores modernos, revisión funcional y de plataformas, arquitectura y entrega, hoja de ruta de seis meses, plan de personal, informe ejecutivo y un paquete final sujeto a revisión.",
      instructionsTitle: "Instrucciones de la evaluación integral",
      instructions: [
        "La evaluación Integral captura un commit inmutable antes de recopilar o analizar evidencia.",
        "La misma identidad continúa por todas las etapas principales y profundas.",
        "La evidencia de negocio, partes interesadas o tiempo de ejecución no disponible se declara en lugar de inventarse.",
        "La entrega al cliente permanece bloqueada hasta que una persona autorizada apruebe el paquete exacto.",
      ],
    },
  },
  phase: {
    idle: "No iniciada",
    starting: "Iniciando",
    running: "Ejecutándose automáticamente",
    review_required: "Se requiere revisión humana",
    complete: "Completa",
    failed: "La ejecución falló o está bloqueada",
    timed_out: "La continuación agotó el tiempo",
  },
  stageLabels: {
    ...EN.stageLabels,
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
  },
};

const DEFAULT_STAGE_PERCENT: Record<string, number> = {
  request_accepted: 4,
  repo_evidence: 18,
  repository_evidence: 18,
  scanner_worker: 42,
  scanner_reconciliation: 52,
  evidence_attachment: 62,
  scoring: 74,
  reports: 86,
  truth_and_review_gates: 96,
  complete: 100,
};

function normalizeTier(value: string | null | undefined): AssessmentTier {
  return value === "comprehensive" || value === "mid" || value === "full" || value === "deep" ? "comprehensive" : "express";
}

function scopeId(prefix: "customer" | "project", value: string, fallback: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

function statusClass(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (["green", "passed", "approved", "complete", "completed", "attached", "verified", "available", "ok", "ready_for_human_decision", "review_required"].includes(normalized)) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "skipped", "human_review_required", "pending_review", "requested", "ready"].includes(normalized)) return "status yellow";
  if (["red", "failed", "error", "rejected", "timeout", "timed_out", "blocked", "unavailable", "interrupted"].includes(normalized)) return "status red";
  return "status gray";
}

function assessmentUrl(path: string): string {
  if (typeof window !== "undefined") return new URL(`/api/nico${path}`, window.location.origin).href;
  return path;
}

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function parseResponse(response: Response): Promise<AssessmentResult> {
  let data: AssessmentResult & {detail?: string | {message?: string; code?: string}; error?: string};
  try {
    data = await response.json();
  } catch {
    throw new Error(`Assessment endpoint returned invalid JSON (${response.status}).`);
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.message || data.detail?.code;
    throw new Error(detail || data.error || `Assessment request failed (${response.status}).`);
  }
  return data;
}

function saveBase64Pdf(encoded: string, filename: string) {
  const binary = window.atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const blob = new Blob([bytes], {type: "application/pdf"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "nico-assessment.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function stageResult(result: AssessmentResult | null, stageId: string): StageResult | null {
  const value = result?.record?.stage_results?.[stageId];
  return value && typeof value === "object" ? value : null;
}

function comprehensiveReports(result: AssessmentResult | null): ReportPackage | null {
  if (!result) return null;
  const candidates = [
    stageResult(result, "final_comprehensive_report_generation"),
    stageResult(result, "risk_reduction_and_executive_briefing"),
    stageResult(result, "decision_report_generation"),
  ];
  for (const item of candidates) {
    const report = item?.report_package || item?.reports;
    if (report && typeof report === "object") return report;
  }
  return result.reports || null;
}

function comprehensiveAssessment(result: AssessmentResult | null): AssessmentDocument | null {
  if (!result) return null;
  const scoring = stageResult(result, "evidence_reconciliation_and_scoring");
  const finalReport = stageResult(result, "final_comprehensive_report_generation");
  const document = finalReport?.assessment || scoring?.assessment;
  return document && typeof document === "object" ? document : result.assessment || null;
}

function progressItems(tier: AssessmentTier, result: AssessmentResult | null): ProgressItem[] {
  if (!result) return [];
  if (tier === "express") return result.progress || [];
  const stageResults = result.record?.stage_results || {};
  return Object.entries(stageResults).map(([step, value]) => ({
    step,
    status: String(value.status || "unknown"),
    message: String(value.message || value.summary || "Stage evidence recorded."),
    evidence: value.evidence && !Array.isArray(value.evidence) ? value.evidence as Record<string, unknown> : undefined,
  }));
}

function stablePhase(tier: AssessmentTier, result: AssessmentResult): RunPhase | null {
  const status = String(result.status || result.record?.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(status)) return "failed";
  if (tier === "express") return ["complete", "completed"].includes(status) ? "complete" : null;
  if (status === "review_required") return "review_required";
  return null;
}

function ListBlock({items, empty}: {items?: string[]; empty: string}) {
  if (!items?.length) return <p className="muted">{empty}</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export default function AssessmentWorkspace({locale = "en"}: {locale?: Locale}) {
  const copy = locale === "es-MX" ? ES : EN;
  const [tier, setTier] = useState<AssessmentTier>("express");
  const [repository, setRepository] = useState("");
  const [clientName, setClientName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pollAttempt, setPollAttempt] = useState(0);
  const [copied, setCopied] = useState("");
  const [scope, setScope] = useState<RunScope>({customerId: "default_customer", projectId: "default_project"});
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const runSequence = useRef(0);

  useEffect(() => {
    document.documentElement.lang = locale === "es-MX" ? "es-MX" : "en";
    const url = new URL(window.location.href);
    const requested = normalizeTier(url.searchParams.get("tier"));
    setTier(requested);
    if (url.searchParams.get("tier") !== requested) {
      url.searchParams.set("tier", requested);
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
    return () => { runSequence.current += 1; };
  }, [locale]);

  useEffect(() => {
    if (!startedAt || !(phase === "starting" || phase === "running")) return;
    const update = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, phase]);

  const tierCopy = copy.tiers[tier];
  const document = useMemo(() => tier === "express" ? result : comprehensiveAssessment(result), [tier, result]);
  const reports = useMemo(() => tier === "express" ? result?.reports || null : comprehensiveReports(result), [tier, result]);
  const coverage = document?.evidence_coverage || result?.evidence_coverage;
  const score = document?.maturity_signal?.presented_score ?? document?.maturity_signal?.score;
  const sections = document?.sections || [];
  const running = phase === "starting" || phase === "running";
  const items = progressItems(tier, result);
  const currentStageId = String(result?.current_stage || result?.record?.current_stage || items.find((item) => ["queued", "running", "pending", "planned"].includes(String(item.status || "").toLowerCase()))?.step || "");
  const explicitProgress = Number(result?.progress_percent ?? result?.record?.progress_percent);
  const percent = phase === "complete" || phase === "review_required" ? 100 : Number.isFinite(explicitProgress) ? Math.max(0, Math.min(100, explicitProgress)) : DEFAULT_STAGE_PERCENT[currentStageId] ?? (running ? 5 : 0);
  const currentStage = copy.stageLabels[currentStageId] || currentStageId.replaceAll("_", " ") || copy.phase[phase];
  const elapsedLabel = `${Math.floor(elapsedSeconds / 60)}:${String(elapsedSeconds % 60).padStart(2, "0")}`;
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent))
    ? `${coverage.label || copy.evidenceReadiness}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
    : copy.coveragePending;
  const scoreLabel = typeof score === "number" && Number.isFinite(score) ? `${score}/100` : copy.notScored;
  const scannerStatus = tier === "express"
    ? result?.scanner_evidence?.scanner_status || result?.scanner?.status || result?.scanner_evidence?.status || copy.pending
    : String(stageResult(result, "dependency_security_static_analysis")?.status || copy.pending);
  const reportStatus = reports?.pdf_base64 || reports?.markdown ? copy.complete : copy.pending;
  const reviewStatus = phase === "review_required" ? copy.phase.review_required : copy.pending;
  const immutableCommit = result?.commit_sha || result?.repository_snapshot?.commit_sha || "—";

  function selectTier(next: AssessmentTier) {
    if (running) return;
    setTier(next);
    setResult(null);
    setError("");
    setMessage("");
    setPhase("idle");
    setPollAttempt(0);
    setElapsedSeconds(0);
    setStartedAt(null);
    setCopied("");
    const url = new URL(window.location.href);
    url.searchParams.set("tier", next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function continueAssessment(selectedTier: AssessmentTier, initial: AssessmentResult, currentScope: RunScope, sequence: number) {
    let current = initial;
    for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt += 1) {
      if (sequence !== runSequence.current) return;
      setResult(current);
      const stable = stablePhase(selectedTier, current);
      if (stable) {
        setPhase(stable);
        setPollAttempt(attempt);
        setMessage(stable === "review_required"
          ? `${copy.tiers[selectedTier].label} completed every automated stage and stopped at the required human-review gate.`
          : stable === "complete"
            ? "Express completed its evidence, scoring, report, and truth-gate stages. Human review remains required before delivery."
            : `${copy.tiers[selectedTier].label} stopped because a required stage failed or was blocked.`);
        return;
      }

      setPhase("running");
      setPollAttempt(attempt);
      setMessage(`${copy.tiers[selectedTier].label}: ${copy.stageLabels[String(current.current_stage || current.record?.current_stage || "")] || currentStage}.`);

      const runId = String(current.run_id || "");
      if (!runId) throw new Error("The assessment response did not include a run ID for autonomous continuation.");
      if (selectedTier === "comprehensive") {
        const response = await fetch(assessmentUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({max_stages: 1}),
          cache: "no-store",
        });
        current = await parseResponse(response);
      } else {
        await sleep(POLL_INTERVAL_MS);
        const response = await fetch(assessmentUrl(`/assessment/express-run/${encodeURIComponent(runId)}/status`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({customer_id: current.customer_id || currentScope.customerId, project_id: current.project_id || currentScope.projectId}),
          cache: "no-store",
        });
        current = await parseResponse(response);
      }
      await sleep(POLL_INTERVAL_MS);
    }

    setResult(current);
    setPhase("timed_out");
    setMessage(copy.timeoutNotice);
  }

  async function runAssessment() {
    if (!authorized) {
      setError(copy.authorizationError);
      return;
    }
    const sequence = runSequence.current + 1;
    runSequence.current = sequence;
    const currentScope = {
      customerId: scopeId("customer", clientName, "default_customer"),
      projectId: scopeId("project", projectName, "default_project"),
    };
    setScope(currentScope);
    setPhase("starting");
    setResult(null);
    setError("");
    setMessage(`${copy.phase.starting}: ${tierCopy.label}`);
    setPollAttempt(0);
    setStartedAt(Date.now());
    setElapsedSeconds(0);
    setCopied("");

    const payload = {
      repository,
      customer_id: currentScope.customerId,
      project_id: currentScope.projectId,
      client_name: clientName,
      project_name: projectName,
      authorized_by: "public_assessment_requester",
      authorization_scope: "authorized defensive repository assessment",
      authorization_confirmed: true,
      authorized: true,
      timeframe_days: 180,
    };

    try {
      const startPath = tier === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake";
      const body = tier === "express" ? {...payload, assessment_mode: "express"} : payload;
      const response = await fetch(assessmentUrl(startPath), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
        cache: "no-store",
      });
      const data = await parseResponse(response);
      if (sequence !== runSequence.current) return;
      setResult(data);
      await continueAssessment(tier, data, currentScope, sequence);
    } catch (caught) {
      if (sequence !== runSequence.current) return;
      setPhase("failed");
      setError(caught instanceof Error ? caught.message : copy.startError);
      setMessage(copy.backendUnavailable);
    }
  }

  async function copyMarkdown() {
    if (!reports?.markdown) return;
    await navigator.clipboard.writeText(reports.markdown);
    setCopied(locale === "es-MX" ? "Markdown copiado" : "Markdown copied");
  }

  function downloadPdf() {
    if (!reports?.pdf_base64) {
      setError(reports?.pdf_error || (locale === "es-MX" ? "No se devolvió un PDF para este informe preliminar." : "A PDF was not returned for this draft report."));
      return;
    }
    saveBase64Pdf(reports.pdf_base64, reports.pdf_filename || `nico-${tier}-assessment.pdf`);
  }

  return <main className="shell" data-assessment-service-count="2" data-assessment-locale={locale}>
    <section className="hero">
      <p className="eyebrow">{copy.heroEyebrow}</p>
      <h1>{copy.heroTitle}</h1>
      <p className="lead">{copy.heroLead}</p>
    </section>

    <section id="assessment" className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">{tierCopy.eyebrow}</p><h2>{tierCopy.title}</h2></div>
        <span className="status gray">{coverageLabel}</span>
      </div>
      <p className="summary-box">{tierCopy.summary}</p>
      <div className={styles.tierGrid} aria-label="Assessment type">
        {(["express", "comprehensive"] as AssessmentTier[]).map((value) => <button
          type="button"
          key={value}
          className={tier === value ? "primary-button" : ""}
          aria-pressed={tier === value}
          disabled={running}
          onClick={() => selectTier(value)}
        >{copy.tiers[value].label}</button>)}
      </div>
      <details className="help-details"><summary>{tierCopy.instructionsTitle}</summary><ul>{tierCopy.instructions.map((item) => <li key={item}>{item}</li>)}</ul></details>
      <p className="warning-box">{copy.authorizationWarning}</p>
      <div className="form-grid">
        <label>{copy.repositoryLabel}<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={copy.repositoryPlaceholder} disabled={running} /></label>
        <label>{copy.clientLabel}<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder={copy.clientPlaceholder} disabled={running} /></label>
        <label>{copy.projectLabel}<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder={copy.projectPlaceholder} disabled={running} /></label>
      </div>
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} disabled={running} />{copy.authorizationConfirm}</label>
      <button type="button" className="primary-button" disabled={!authorized || !repository.trim() || running} onClick={runAssessment}>
        {running ? `${copy.phase.running}: ${tierCopy.label}` : `${locale === "es-MX" ? "Ejecutar" : "Run"} ${tierCopy.label}`}
      </button>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    <section className="section panel" aria-live="polite">
      <div className="section-head">
        <div><p className="eyebrow">{copy.runStateEyebrow}</p><h2>{result?.run_id || copy.phase[phase]}</h2></div>
        <span className={statusClass(phase)}>{copy.phase[phase]}</span>
      </div>
      <p className={phase === "failed" ? "error-box" : phase === "review_required" ? "warning-box" : "summary-box"}>{message || (locale === "es-MX" ? "Selecciona un servicio y ejecuta un repositorio autorizado." : "Select a service and run an authorized repository.")}</p>
      {running ? <>
        <div className={styles.progressMeta}>
          <span><b>{copy.currentStage}</b>{currentStage}</span>
          <span><b>{copy.progress}</b>{Math.round(percent)}%</span>
          <span><b>{copy.elapsed}</b>{elapsedLabel}</span>
          <span><b>{copy.checks}</b>{pollAttempt}</span>
        </div>
        <div className={styles.progressBar} role="progressbar" aria-label={`${currentStage} in progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{width: `${Math.max(2, Math.min(100, percent))}%`}} /></div>
      </> : null}

      {result ? <>
        <div className="grid four target-grid">
          <article><b>{copy.runId}</b><span>{result.run_id || copy.notVerified}</span></article>
          <article><b>{copy.immutableCommit}</b><span>{immutableCommit}</span></article>
          <article><b>{copy.scanner}</b><span>{scannerStatus}</span></article>
          <article><b>{copy.report}</b><span>{reportStatus}</span></article>
        </div>
        <div className="grid four target-grid">
          <article><b>{copy.humanReview}</b><span>{reviewStatus}</span></article>
          <article><b>{copy.maturity}</b><span>{document?.maturity_signal?.level || copy.pending}</span></article>
          <article><b>{copy.technicalScore}</b><span>{scoreLabel}</span></article>
          <article><b>{copy.durableRecord}</b><span>{result.persistence?.durable === true ? (locale === "es-MX" ? "Sí" : "Yes") : result.persistence?.recorded ? copy.recordedNotDurable : copy.notVerified}</span></article>
        </div>
        {document?.executive_summary ? <p className="summary-box">{document.executive_summary}</p> : null}

        {items.length ? <div className={styles.timeline}>{items.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
          <div className="result-head"><b>{copy.stageLabels[String(item.step || "")] || String(item.step || "step").replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{item.status || "unknown"}</span></div>
          <p>{item.message || "Stage evidence recorded."}</p>
          {item.evidence && Object.keys(item.evidence).length ? <details className="help-details"><summary>{copy.stepEvidence}</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}
        </article>)}</div> : null}

        {sections.length ? <div className="results-grid">{sections.map((section, index) => {
          const sectionScore = typeof (section.presented_score ?? section.score) === "number" ? `${section.presented_score ?? section.score}/100` : copy.notScored;
          const sectionStatus = section.presented_status || section.status || "unknown";
          return <article className="result-card" key={section.id || `${section.label}-${index}`}>
            <div className="result-head"><b>{section.label || section.id}</b><span className={statusClass(sectionStatus)}>{sectionStatus} · {sectionScore}</span></div>
            <p>{section.summary}</p>
            <details className="help-details"><summary>{copy.evidence} ({section.evidence?.length || 0})</summary><ListBlock items={section.evidence} empty={copy.noItems} /></details>
            {section.findings?.length ? <details className="help-details"><summary>{copy.findings} ({section.findings.length})</summary><ListBlock items={section.findings} empty={copy.noItems} /></details> : null}
            {section.unavailable?.length ? <details className="help-details"><summary>{copy.unavailable} ({section.unavailable.length})</summary><ListBlock items={section.unavailable} empty={copy.noItems} /></details> : null}
          </article>;
        })}</div> : null}

        <div className="report-actions">
          <button type="button" disabled={!reports?.markdown} onClick={copyMarkdown}>{copy.copyMarkdown}</button>
          <button type="button" disabled={!reports?.pdf_base64} onClick={downloadPdf}>{copy.downloadPdf}</button>
          {copied ? <span className="muted">{copied}</span> : null}
        </div>
        {phase === "review_required" ? <p className="warning-box">{copy.reviewNotice}</p> : null}
        {document?.unavailable_data_notes?.length ? <details className="help-details"><summary>{copy.unavailable} ({document.unavailable_data_notes.length})</summary><ListBlock items={document.unavailable_data_notes} empty={copy.noItems} /></details> : null}
      </> : null}
    </section>
  </main>;
}
