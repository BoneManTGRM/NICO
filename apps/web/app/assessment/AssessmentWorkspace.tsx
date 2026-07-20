"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import styles from "./assessment.module.css";

type Locale = "en" | "es-MX";
type Service = "express" | "comprehensive";
type Phase = "idle" | "starting" | "running" | "review_required" | "complete" | "failed" | "timed_out";
type Report = {markdown?: string; pdf_base64?: string; pdf_filename?: string; pdf_error?: string};
type Section = {id?: string; label?: string; score?: number | null; presented_score?: number | null; status?: string; presented_status?: string; summary?: string; evidence?: string[]; findings?: string[]; unavailable?: string[]};
type Assessment = {executive_summary?: string; evidence_coverage?: {calculated?: boolean; percent?: number; label?: string}; maturity_signal?: {level?: string; score?: number; presented_score?: number}; sections?: Section[]; unavailable_data_notes?: string[]};
type Stage = {status?: string; message?: string; summary?: string; evidence?: Record<string, unknown> | string[]; assessment?: Assessment; report_package?: Report; reports?: Report};
type Result = Assessment & {status?: string; run_id?: string; commit_sha?: string; customer_id?: string; project_id?: string; current_stage?: string | null; progress_percent?: number; progress?: Array<{step?: string; status?: string; message?: string; evidence?: Record<string, unknown>}>; assessment?: Assessment; reports?: Report; record?: {status?: string; current_stage?: string | null; progress_percent?: number; stage_results?: Record<string, Stage>}; repository_snapshot?: {commit_sha?: string}; scanner?: {status?: string}; scanner_evidence?: {status?: string; scanner_status?: string}; persistence?: {recorded?: boolean; durable?: boolean}};
type Scope = {customerId: string; projectId: string};
type Text = {
  title: string; lead: string; coverage: string; warning: string; repo: string; repoPlaceholder: string; client: string; project: string; confirm: string; run: string;
  state: string; stage: string; progress: string; elapsed: string; checks: string; runId: string; commit: string; scanner: string; report: string; review: string;
  maturity: string; score: string; durable: string; pending: string; notScored: string; notVerified: string; copied: string; copy: string; download: string;
  select: string; unavailable: string; evidence: string; findings: string; stepEvidence: string; reviewNotice: string; backendError: string; authError: string;
  services: Record<Service, {label: string; eyebrow: string; heading: string; summary: string; instructions: string[]}>;
  phases: Record<Phase, string>;
};

const EN: Text = {
  title: "One workspace. Two evidence-bound services.", lead: "Choose Express for a fast technical baseline or Comprehensive for the complete snapshot-bound assessment. Both use native backend identities and stop at required human review.", coverage: "Coverage calculated after run",
  warning: "Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.", repo: "Repository owner/name or GitHub URL", repoPlaceholder: "your-org/your-repo", client: "Client name, optional", project: "Project name, optional", confirm: "I confirm I own this target or have explicit permission to assess it.", run: "Run",
  state: "AUTOMATED RUN STATE", stage: "Current stage", progress: "Progress", elapsed: "Elapsed", checks: "Status checks", runId: "Run ID", commit: "Immutable commit", scanner: "Scanner", report: "Report", review: "Human review", maturity: "Maturity signal", score: "Technical score", durable: "Durable record", pending: "Pending", notScored: "Not scored", notVerified: "Not verified", copied: "Markdown copied", copy: "Copy Markdown", download: "Download draft PDF", select: "Select a service and run an authorized repository.", unavailable: "Unavailable or limited evidence", evidence: "Evidence", findings: "Findings", stepEvidence: "Step evidence", reviewNotice: "Automated work is complete. NICO did not approve findings or authorize client delivery. A human must review the exact evidence-bound artifact.", backendError: "The assessment backend could not be reached from this deployment.", authError: "Confirm that you own the target or have explicit permission to assess it.",
  services: {
    express: {label: "Express", eyebrow: "EXPRESS ASSESSMENT", heading: "Fast evidence-bound technical baseline", summary: "Repository evidence, calibrated scoring, repair intelligence, and a downloadable draft report.", instructions: ["Publishes real backend stages.", "Uses the exact run's reconciled evidence.", "Discloses missing evidence and requires human review."]},
    comprehensive: {label: "Comprehensive", eyebrow: "COMPREHENSIVE ASSESSMENT", heading: "Complete snapshot-bound technical diligence", summary: "One immutable commit, modern scanners, functional and platform review, architecture and delivery analysis, six-month roadmap, staffing plan, executive briefing, and one review-gated report package.", instructions: ["Captures one immutable commit before evidence collection.", "Continues the same native run through every core and deep stage.", "Discloses unavailable evidence rather than fabricating it.", "Blocks client delivery until human approval."]},
  },
  phases: {idle: "Not started", starting: "Starting", running: "Running automatically", review_required: "Human review required", complete: "Complete", failed: "Run failed or blocked", timed_out: "Continuation timed out"},
};

const ES: Text = {
  ...EN,
  title: "Un espacio de trabajo. Dos servicios vinculados a evidencia.", lead: "Elige Express para una línea base técnica rápida o Integral para la evaluación completa vinculada a una instantánea exacta. Ambos usan identidades nativas del backend y se detienen ante la revisión humana obligatoria.", coverage: "Cobertura calculada después de la ejecución",
  warning: "Evalúa únicamente repositorios que te pertenezcan o para los que tengas autorización explícita. NICO realiza evaluaciones defensivas de solo lectura y no efectúa cambios destructivos.", repo: "Propietario/nombre del repositorio o URL de GitHub", repoPlaceholder: "tu-organización/tu-repositorio", client: "Nombre del cliente, opcional", project: "Nombre del proyecto, opcional", confirm: "Confirmo que soy propietario de este objetivo o que tengo autorización explícita para evaluarlo.", run: "Ejecutar",
  state: "ESTADO DE EJECUCIÓN AUTOMATIZADA", stage: "Etapa actual", progress: "Progreso", elapsed: "Tiempo transcurrido", checks: "Comprobaciones de estado", runId: "ID de ejecución", commit: "Commit inmutable", scanner: "Analizadores", report: "Informe", review: "Revisión humana", maturity: "Señal de madurez", score: "Puntuación técnica", durable: "Registro durable", pending: "Pendiente", notScored: "Sin puntuación", notVerified: "No verificado", copied: "Markdown copiado", copy: "Copiar Markdown", download: "Descargar PDF preliminar", select: "Selecciona un servicio y ejecuta un repositorio autorizado.", unavailable: "Evidencia no disponible o limitada", evidence: "Evidencia", findings: "Hallazgos", stepEvidence: "Evidencia de la etapa", reviewNotice: "El trabajo automatizado terminó. NICO no aprobó hallazgos ni autorizó la entrega. Una persona debe revisar el artefacto exacto vinculado a evidencia.", backendError: "No se pudo acceder al backend de evaluación desde este despliegue.", authError: "Confirma que eres propietario del objetivo o que tienes autorización explícita para evaluarlo.",
  services: {
    express: {label: "Express", eyebrow: "EVALUACIÓN EXPRESS", heading: "Línea base técnica rápida vinculada a evidencia", summary: "Evidencia del repositorio, puntuación calibrada, inteligencia de reparación y un informe preliminar descargable.", instructions: ["Publica etapas reales del backend.", "Usa la evidencia conciliada de la ejecución exacta.", "Declara la evidencia ausente y requiere revisión humana."]},
    comprehensive: {label: "Integral", eyebrow: "EVALUACIÓN INTEGRAL", heading: "Diligencia técnica completa vinculada a una instantánea", summary: "Un commit inmutable, analizadores modernos, revisión funcional y de plataformas, arquitectura y entrega, hoja de ruta de seis meses, plan de personal, informe ejecutivo y un paquete final sujeto a revisión.", instructions: ["Captura un commit inmutable antes de recopilar evidencia.", "Continúa la misma ejecución nativa por todas las etapas.", "Declara la evidencia no disponible en lugar de inventarla.", "Bloquea la entrega hasta la aprobación humana."]},
  },
  phases: {idle: "No iniciada", starting: "Iniciando", running: "Ejecutándose automáticamente", review_required: "Se requiere revisión humana", complete: "Completa", failed: "La ejecución falló o está bloqueada", timed_out: "La continuación agotó el tiempo"},
};

const STAGE_LABELS: Record<string, string> = {
  request_accepted: "Request accepted", repo_evidence: "Repository evidence", repository_evidence: "Repository evidence", scanner_worker: "Scanner suite", scanner_reconciliation: "Scanner reconciliation", evidence_attachment: "Evidence attachment", scoring: "Technical scoring", reports: "Report generation", truth_and_review_gates: "Truth and review gates",
  authorization_and_scope: "Authorization and scope", immutable_repository_snapshot: "Immutable repository snapshot", repository_and_delivery_evidence: "Repository and delivery evidence", dependency_security_static_analysis: "Dependency, security, and static analysis", ci_cd_architecture_complexity_velocity: "CI/CD, architecture, complexity, and velocity", evidence_reconciliation_and_scoring: "Evidence reconciliation and scoring", decision_report_generation: "Core decision report", deep_scanner_triage: "Deep scanner triage", functional_qa: "Functional QA", platform_parity: "Platform parity", deployment_and_infrastructure: "Deployment and infrastructure", architecture_and_data_flow: "Architecture and data flow", developer_delivery_process: "Developer delivery process", stakeholder_and_business_alignment: "Stakeholder and business alignment", requirements_traceability: "Requirements traceability", historical_trends_and_change_failure: "Historical trends and change failure", six_month_roadmap: "Six-month roadmap", staffing_sequencing_and_cost: "Staffing, sequencing, and cost", risk_reduction_and_executive_briefing: "Risk reduction and executive briefing", final_comprehensive_report_generation: "Final Comprehensive report", cross_format_truth_verification: "Cross-format truth verification", human_review_request: "Human-review request", client_acceptance_pending: "Client acceptance pending",
};

function normalizeService(value: string | null): Service { return ["comprehensive", "mid", "full", "deep"].includes(String(value || "")) ? "comprehensive" : "express"; }
function scopeId(prefix: string, value: string, fallback: string): string { const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72); return slug ? `${prefix}_${slug}` : fallback; }
function statusClass(status?: string): string { const value = String(status || "").toLowerCase(); if (["complete", "completed", "attached", "verified", "review_required"].includes(value)) return "status green"; if (["pending", "running", "queued", "planned", "ready", "starting"].includes(value)) return "status yellow"; if (["failed", "blocked", "error", "unavailable", "timed_out"].includes(value)) return "status red"; return "status gray"; }
function api(path: string): string { return new URL(`/api/nico${path}`, window.location.origin).href; }
function stage(result: Result | null, id: string): Stage | null { const value = result?.record?.stage_results?.[id]; return value && typeof value === "object" ? value : null; }
function assessmentFor(service: Service, result: Result | null): Assessment | null { if (!result) return null; if (service === "express") return result; return stage(result, "final_comprehensive_report_generation")?.assessment || stage(result, "evidence_reconciliation_and_scoring")?.assessment || result.assessment || null; }
function reportFor(service: Service, result: Result | null): Report | null { if (!result) return null; if (service === "express") return result.reports || null; for (const id of ["final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation"]) { const value = stage(result, id); const report = value?.report_package || value?.reports; if (report) return report; } return result.reports || null; }
function terminal(service: Service, result: Result): Phase | null { const value = String(result.status || result.record?.status || "").toLowerCase(); if (["failed", "blocked", "error", "rejected"].includes(value)) return "failed"; if (service === "express" && ["complete", "completed"].includes(value)) return "complete"; if (service === "comprehensive" && value === "review_required") return "review_required"; return null; }
async function wait(ms: number): Promise<void> { await new Promise((resolve) => window.setTimeout(resolve, ms)); }
async function json(response: Response): Promise<Result> { const data = await response.json() as Result & {detail?: string | {message?: string}; error?: string}; if (!response.ok) { const detail = typeof data.detail === "string" ? data.detail : data.detail?.message; throw new Error(detail || data.error || `Assessment request failed (${response.status}).`); } return data; }
function savePdf(encoded: string, filename: string): void { const binary = window.atob(encoded); const bytes = new Uint8Array(binary.length); for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i); const blob = new Blob([bytes.buffer], {type: "application/pdf"}); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0); }
function List({items, empty}: {items?: string[]; empty: string}) { return items?.length ? <ul className="tight-list">{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p className="muted">{empty}</p>; }

export default function AssessmentWorkspace({locale = "en"}: {locale?: Locale}) {
  const text = locale === "es-MX" ? ES : EN;
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

  useEffect(() => { document.documentElement.lang = locale; const url = new URL(window.location.href); const next = normalizeService(url.searchParams.get("tier")); setService(next); if (url.searchParams.get("tier") !== next) { url.searchParams.set("tier", next); window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`); } return () => { sequence.current += 1; }; }, [locale]);
  useEffect(() => { if (!started || !["starting", "running"].includes(phase)) return; const update = () => setElapsed(Math.floor((Date.now() - started) / 1000)); update(); const timer = window.setInterval(update, 1000); return () => window.clearInterval(timer); }, [started, phase]);

  const copy = text.services[service];
  const assessment = useMemo(() => assessmentFor(service, result), [service, result]);
  const report = useMemo(() => reportFor(service, result), [service, result]);
  const running = phase === "starting" || phase === "running";
  const stageId = String(result?.current_stage || result?.record?.current_stage || "");
  const percentValue = Number(result?.progress_percent ?? result?.record?.progress_percent);
  const percent = phase === "complete" || phase === "review_required" ? 100 : Number.isFinite(percentValue) ? Math.max(0, Math.min(100, percentValue)) : running ? 5 : 0;
  const coverage = assessment?.evidence_coverage;
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent)) ? `${coverage.label || text.evidence}: ${coverage.percent}%` : text.coverage;
  const scoreValue = assessment?.maturity_signal?.presented_score ?? assessment?.maturity_signal?.score;
  const scoreLabel = typeof scoreValue === "number" ? `${scoreValue}/100` : text.notScored;
  const immutableCommit = result?.commit_sha || result?.repository_snapshot?.commit_sha || "—";
  const scannerStatus = service === "express" ? result?.scanner_evidence?.scanner_status || result?.scanner?.status || result?.scanner_evidence?.status || text.pending : stage(result, "dependency_security_static_analysis")?.status || text.pending;
  const progressItems = service === "express" ? result?.progress || [] : Object.entries(result?.record?.stage_results || {}).map(([step, value]) => ({step, status: value.status, message: value.message || value.summary, evidence: value.evidence && !Array.isArray(value.evidence) ? value.evidence : undefined}));

  function choose(next: Service): void { if (running) return; setService(next); setResult(null); setPhase("idle"); setMessage(""); setError(""); setAttempt(0); setStarted(null); setElapsed(0); setCopied(false); const url = new URL(window.location.href); url.searchParams.set("tier", next); window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`); }

  async function continueRun(selected: Service, initial: Result, scope: Scope, token: number): Promise<void> {
    let current = initial;
    for (let count = 1; count <= 360; count += 1) {
      if (token !== sequence.current) return;
      setResult(current);
      const stable = terminal(selected, current);
      if (stable) { setPhase(stable); setAttempt(count); setMessage(stable === "review_required" ? `${text.services[selected].label} completed automated stages and stopped at human review.` : stable === "complete" ? "Express completed its automated stages." : `${text.services[selected].label} stopped because a required stage failed or was blocked.`); return; }
      setPhase("running"); setAttempt(count); setMessage(`${text.services[selected].label}: ${STAGE_LABELS[String(current.current_stage || current.record?.current_stage || "")] || text.phases.running}.`);
      const runId = String(current.run_id || ""); if (!runId) throw new Error("The assessment response did not include a run ID.");
      if (selected === "comprehensive") { current = await json(await fetch(api(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({max_stages: 1}), cache: "no-store"})); }
      else { await wait(3000); current = await json(await fetch(api(`/assessment/express-run/${encodeURIComponent(runId)}/status`), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({customer_id: current.customer_id || scope.customerId, project_id: current.project_id || scope.projectId}), cache: "no-store"})); }
      await wait(3000);
    }
    setResult(current); setPhase("timed_out"); setMessage(text.phases.timed_out);
  }

  async function run(): Promise<void> {
    if (!authorized) { setError(text.authError); return; }
    const token = sequence.current + 1; sequence.current = token;
    const scope = {customerId: scopeId("customer", client, "default_customer"), projectId: scopeId("project", project, "default_project")};
    setPhase("starting"); setResult(null); setError(""); setMessage(`${text.phases.starting}: ${copy.label}`); setAttempt(0); setStarted(Date.now()); setElapsed(0); setCopied(false);
    const body = {repository, customer_id: scope.customerId, project_id: scope.projectId, client_name: client, project_name: project, authorized_by: "public_assessment_requester", authorization_scope: "authorized defensive repository assessment", authorization_confirmed: true, authorized: true, timeframe_days: 180};
    try { const path = service === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake"; const data = await json(await fetch(api(path), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(service === "express" ? {...body, assessment_mode: "express"} : body), cache: "no-store"})); if (token !== sequence.current) return; setResult(data); await continueRun(service, data, scope, token); }
    catch (caught) { if (token !== sequence.current) return; setPhase("failed"); setError(caught instanceof Error ? caught.message : text.backendError); setMessage(text.backendError); }
  }

  async function copyMarkdown(): Promise<void> { if (!report?.markdown) return; await navigator.clipboard.writeText(report.markdown); setCopied(true); }
  function downloadPdf(): void { if (!report?.pdf_base64) { setError(report?.pdf_error || text.backendError); return; } savePdf(report.pdf_base64, report.pdf_filename || `nico-${service}-assessment.pdf`); }

  return <main className="shell" data-assessment-service-count="2" data-assessment-locale={locale}>
    <section className="hero"><p className="eyebrow">NICO ASSESSMENTS</p><h1>{text.title}</h1><p className="lead">{text.lead}</p></section>
    <section id="assessment" className="section panel">
      <div className="section-head"><div><p className="eyebrow">{copy.eyebrow}</p><h2>{copy.heading}</h2></div><span className="status gray">{coverageLabel}</span></div>
      <p className="summary-box">{copy.summary}</p>
      <div className={styles.tierGrid} aria-label="Assessment type">{(["express", "comprehensive"] as Service[]).map((value) => <button type="button" key={value} className={service === value ? "primary-button" : ""} aria-pressed={service === value} disabled={running} onClick={() => choose(value)}>{text.services[value].label}</button>)}</div>
      <details className="help-details"><summary>{copy.label} instructions</summary><ul>{copy.instructions.map((item) => <li key={item}>{item}</li>)}</ul></details>
      <p className="warning-box">{text.warning}</p>
      <div className="form-grid"><label>{text.repo}<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={text.repoPlaceholder} disabled={running} /></label><label>{text.client}<input value={client} onChange={(event) => setClient(event.target.value)} disabled={running} /></label><label>{text.project}<input value={project} onChange={(event) => setProject(event.target.value)} disabled={running} /></label></div>
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} disabled={running} />{text.confirm}</label>
      <button type="button" className="primary-button" disabled={!authorized || !repository.trim() || running} onClick={run}>{running ? `${text.phases.running}: ${copy.label}` : `${text.run} ${copy.label}`}</button>
      {error ? <p className="error-box">{error}</p> : null}
    </section>
    <section className="section panel" aria-live="polite">
      <div className="section-head"><div><p className="eyebrow">{text.state}</p><h2>{result?.run_id || text.phases[phase]}</h2></div><span className={statusClass(phase)}>{text.phases[phase]}</span></div>
      <p className={phase === "failed" ? "error-box" : phase === "review_required" ? "warning-box" : "summary-box"}>{message || text.select}</p>
      {running ? <><div className={styles.progressMeta}><span><b>{text.stage}</b>{STAGE_LABELS[stageId] || stageId.replaceAll("_", " ") || text.phases[phase]}</span><span><b>{text.progress}</b>{Math.round(percent)}%</span><span><b>{text.elapsed}</b>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span><span><b>{text.checks}</b>{attempt}</span></div><div className={styles.progressBar} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{width: `${Math.max(2, percent)}%`}} /></div></> : null}
      {result ? <><div className="grid four target-grid"><article><b>{text.runId}</b><span>{result.run_id || text.notVerified}</span></article><article><b>{text.commit}</b><span>{immutableCommit}</span></article><article><b>{text.scanner}</b><span>{scannerStatus}</span></article><article><b>{text.report}</b><span>{report?.markdown || report?.pdf_base64 ? text.phases.complete : text.pending}</span></article></div><div className="grid four target-grid"><article><b>{text.review}</b><span>{phase === "review_required" ? text.phases.review_required : text.pending}</span></article><article><b>{text.maturity}</b><span>{assessment?.maturity_signal?.level || text.pending}</span></article><article><b>{text.score}</b><span>{scoreLabel}</span></article><article><b>{text.durable}</b><span>{result.persistence?.durable ? (locale === "es-MX" ? "Sí" : "Yes") : result.persistence?.recorded ? "Recorded" : text.notVerified}</span></article></div>
        {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
        {progressItems.length ? <div className={styles.timeline}>{progressItems.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}><div className="result-head"><b>{STAGE_LABELS[String(item.step || "")] || String(item.step || "step").replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{item.status || "unknown"}</span></div><p>{item.message || "Stage evidence recorded."}</p>{item.evidence ? <details className="help-details"><summary>{text.stepEvidence}</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}</article>)}</div> : null}
        {assessment?.sections?.length ? <div className="results-grid">{assessment.sections.map((section, index) => { const value = section.presented_score ?? section.score; const label = typeof value === "number" ? `${value}/100` : text.notScored; const state = section.presented_status || section.status || "unknown"; return <article className="result-card" key={section.id || index}><div className="result-head"><b>{section.label || section.id}</b><span className={statusClass(state)}>{state} · {label}</span></div><p>{section.summary}</p><details className="help-details"><summary>{text.evidence} ({section.evidence?.length || 0})</summary><List items={section.evidence} empty={text.notVerified} /></details>{section.findings?.length ? <details className="help-details"><summary>{text.findings} ({section.findings.length})</summary><List items={section.findings} empty={text.notVerified} /></details> : null}{section.unavailable?.length ? <details className="help-details"><summary>{text.unavailable} ({section.unavailable.length})</summary><List items={section.unavailable} empty={text.notVerified} /></details> : null}</article>; })}</div> : null}
        <div className="report-actions"><button type="button" disabled={!report?.markdown} onClick={copyMarkdown}>{text.copy}</button><button type="button" disabled={!report?.pdf_base64} onClick={downloadPdf}>{text.download}</button>{copied ? <span className="muted">{text.copied}</span> : null}</div>
        {phase === "review_required" ? <p className="warning-box">{text.reviewNotice}</p> : null}
        {assessment?.unavailable_data_notes?.length ? <details className="help-details"><summary>{text.unavailable} ({assessment.unavailable_data_notes.length})</summary><List items={assessment.unavailable_data_notes} empty={text.notVerified} /></details> : null}
      </> : null}
    </section>
  </main>;
}
