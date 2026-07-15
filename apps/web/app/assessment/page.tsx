"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import styles from "./assessment.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 240;
const MID_RUN_EVENT = "nico:mid-run-selected";
const TIER_EVENT = "nico:assessment-tier-selected";
const FULL_TOOLS = [
  "pip-audit",
  "npm-audit",
  "osv-scanner",
  "bandit",
  "semgrep",
  "eslint",
  "typescript",
  "gitleaks",
  "trufflehog",
];

const DEFAULT_STAGE_PERCENT: Record<string, number> = {
  request_accepted: 4,
  repo_evidence: 18,
  repository_evidence: 18,
  scanner_worker: 42,
  scanner_reconciliation: 52,
  evidence_attachment: 62,
  accuracy_review: 66,
  scoring: 74,
  score_reconciliation: 76,
  reports: 86,
  report_generation: 86,
  approval_request: 94,
  truth_and_review_gates: 96,
  complete: 100,
};

const STAGE_LABELS: Record<string, string> = {
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
  complete: "Complete",
};

type AssessmentTier = "express" | "mid" | "full";
type RunPhase = "idle" | "starting" | "running" | "review_required" | "complete" | "failed" | "timed_out";
type EvidenceCoverage = {percent?: number; calculated?: boolean; label?: string; numerator?: number; denominator?: number};
type Section = {
  id?: string;
  label?: string;
  score?: number | null;
  status?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
  confidence?: string;
};
type ProgressItem = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
type AssessmentDocument = {
  status?: string;
  executive_summary?: string;
  maturity_signal?: {level?: string; score?: number; summary?: string; evidence_readiness_score?: number};
  evidence_coverage?: EvidenceCoverage;
  sections?: Section[];
  findings?: string[];
  repairs?: string[];
  unavailable_data_notes?: string[];
  human_review_required?: boolean;
  client_ready?: boolean;
};
type AssessmentResult = AssessmentDocument & {
  status?: string;
  run_id?: string;
  repository?: string;
  customer_id?: string;
  project_id?: string;
  generated_at?: string;
  updated_at?: string;
  current_stage?: string;
  progress_percent?: number;
  progress?: ProgressItem[];
  assessment?: AssessmentDocument;
  repository_snapshot?: {snapshot_id?: string; commit_sha?: string};
  repository_evidence?: {status?: string; evidence_id?: string; snapshot_commit_sha?: string; unavailable_data_notes?: string[]};
  scanner?: {scan_id?: string; status?: string};
  scanner_evidence?: {status?: string; scan_id?: string; scanner_status?: string; unavailable_data_notes?: string[]};
  reports?: {
    markdown?: string;
    html?: string;
    pdf_base64?: string;
    pdf_filename?: string;
    pdf_error?: string;
    report_id?: string;
    report_path?: string;
    pdf_sha256?: string;
  };
  mid_report?: {status?: string; report_id?: string; draft_status?: string; pdf_filename?: string; pdf_sha256?: string};
  report_generation_status?: string;
  report_generation_note?: string;
  report_generation_error?: string;
  approval_request?: {approval_id?: string; status?: string; draft_report_id?: string; exception_item_count?: number};
  approval_request_status?: string;
  approval?: {approval_id?: string; status?: string; report_id?: string; review_validation?: {status?: string; blockers?: string[]}};
  persistence?: {recorded?: boolean; durable?: boolean; adapter?: string; note?: string};
  human_review_required?: boolean;
  client_ready?: boolean;
};
type RunScope = {customerId: string; projectId: string};

const TIER_COPY: Record<AssessmentTier, {eyebrow: string; title: string; summary: string; instructions: string[]}> = {
  express: {
    eyebrow: "EXPRESS ASSESSMENT",
    title: "Fast evidence-bound technical baseline",
    summary: "Repository evidence, calibrated scoring, decision-ready repair intelligence, and a downloadable draft report.",
    instructions: [
      "Express now publishes real backend stages instead of displaying a fake poll-based percentage.",
      "The report is generated directly from this run's reconciled evidence.",
      "Missing or failed evidence remains disclosed and human review is still required.",
    ],
  },
  mid: {
    eyebrow: "MID ASSESSMENT",
    title: "Complete snapshot-bound assessment",
    summary: "One exact commit, modern scanner suite, evidence attachment, technical score, decision-ready draft, and human-review request.",
    instructions: [
      "Mid binds repository evidence and scanners to one exact run and snapshot.",
      "NICO continues the same run through evidence, scanners, scoring, report generation, and review-request creation.",
      "The score reflects verified evidence and material findings; it is not forced upward.",
    ],
  },
  full: {
    eyebrow: "FULL ASSESSMENT",
    title: "Deep multi-section technical assessment",
    summary: "Repository evidence, comprehensive scanners, multi-section scoring, trust-gated reports, and final-review request.",
    instructions: [
      "Full runs the complete repository and scanner evidence pipeline.",
      "NICO continues through evidence attachment, scoring, report generation, and review-request creation.",
      "Approval and client delivery remain separate human decisions.",
    ],
  },
};

function normalizeTier(value: string | null | undefined): AssessmentTier {
  return value === "mid" || value === "full" ? value : "express";
}

function scopeId(prefix: "customer" | "project", value: string, fallback: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

function statusClass(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (["green", "passed", "approved", "complete", "completed", "attached", "verified", "available", "ok", "ready_for_human_decision", "review_required"].includes(normalized)) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "skipped", "human_review_required", "pending_review", "requested"].includes(normalized)) return "status yellow";
  if (["red", "failed", "error", "rejected", "timeout", "timed_out", "blocked", "unavailable", "interrupted"].includes(normalized)) return "status red";
  return "status gray";
}

function phaseLabel(phase: RunPhase) {
  if (phase === "idle") return "Not started";
  if (phase === "starting") return "Starting";
  if (phase === "running") return "Running automatically";
  if (phase === "review_required") return "Human review required";
  if (phase === "timed_out") return "Continuation timed out";
  if (phase === "failed") return "Run failed or blocked";
  return "Complete";
}

function phaseStatus(phase: RunPhase) {
  if (phase === "review_required" || phase === "complete") return "complete";
  if (phase === "starting" || phase === "running") return "running";
  if (phase === "failed") return "failed";
  if (phase === "timed_out") return "timed_out";
  return "not_started";
}

function assessmentDocument(tier: AssessmentTier, result: AssessmentResult | null): AssessmentDocument | null {
  if (!result) return null;
  return tier === "express" ? result : result.assessment || null;
}

function currentScannerStatus(result: AssessmentResult | null): string {
  if (!result) return "not started";
  return result.scanner_evidence?.scanner_status || result.scanner?.status || result.scanner_evidence?.status || "not started";
}

function currentReportStatus(tier: AssessmentTier, result: AssessmentResult | null): string {
  if (!result) return "not started";
  if (tier === "express") return result.reports?.pdf_base64 || result.reports?.markdown ? "complete" : result.status || "not started";
  if (tier === "mid") return result.report_generation_status || result.mid_report?.status || "pending";
  return result.reports?.report_id ? "complete" : "pending";
}

function currentReviewStatus(tier: AssessmentTier, result: AssessmentResult | null): string {
  if (!result) return "not requested";
  if (tier === "express") return result.human_review_required ? "required" : "not requested";
  if (tier === "mid") return result.approval_request?.status || result.approval_request_status || "pending";
  return result.approval?.status || "pending";
}

function hasFailedProgress(result: AssessmentResult) {
  return (result.progress || []).some((item) => ["failed", "blocked", "error", "interrupted"].includes(String(item.status || "").toLowerCase()));
}

function stablePhase(tier: AssessmentTier, result: AssessmentResult): RunPhase | null {
  const status = String(result.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(status) || hasFailedProgress(result)) return "failed";

  if (tier === "express") {
    return ["complete", "completed"].includes(status) ? "complete" : null;
  }

  if (tier === "mid") {
    if (result.report_generation_status === "blocked" || result.approval_request_status === "blocked") return "failed";
    const reportReady = result.report_generation_status === "complete" && Boolean(result.mid_report?.report_id || result.reports?.markdown);
    const reviewReady = Boolean(result.approval_request?.approval_id) && ["pending", "pending_review", "requested", "review_required"].includes(String(result.approval_request?.status || result.approval_request_status || "pending").toLowerCase());
    if (status === "complete" && reportReady && reviewReady) return "review_required";
    return null;
  }

  const reportReady = Boolean(result.reports?.report_id || result.reports?.markdown);
  const reviewReady = Boolean(result.approval?.approval_id);
  if (status === "complete" && reportReady && reviewReady) return "review_required";
  return null;
}

function activeProgressItem(result: AssessmentResult | null): ProgressItem | null {
  if (!result?.progress?.length) return null;
  return result.progress.find((item) => ["queued", "running", "pending", "planned"].includes(String(item.status || "").toLowerCase()))
    || result.progress[result.progress.length - 1]
    || null;
}

function progressMessage(tier: AssessmentTier, result: AssessmentResult | null, attempt: number) {
  if (!result) return `Starting ${TIER_COPY[tier].eyebrow.toLowerCase()}...`;
  const active = activeProgressItem(result);
  if (active?.message) return active.message;
  if (tier === "mid" && result.report_generation_note) return result.report_generation_note;
  return `Continuing exact run ${result.run_id || ""}. Status check ${attempt}/${MAX_POLL_ATTEMPTS}.`;
}

function calculatedProgress(tier: AssessmentTier, result: AssessmentResult | null, phase: RunPhase): number | null {
  if (phase === "complete" || phase === "review_required") return 100;
  const explicit = Number(result?.progress_percent);
  if (Number.isFinite(explicit)) return Math.max(0, Math.min(100, explicit));
  const active = activeProgressItem(result);
  const step = String(active?.step || result?.current_stage || "");
  if (DEFAULT_STAGE_PERCENT[step] != null) return DEFAULT_STAGE_PERCENT[step];
  if (phase === "starting") return 3;
  if (phase === "running") return tier === "express" ? 12 : 8;
  return null;
}

function stageLabel(result: AssessmentResult | null, phase: RunPhase): string {
  const step = String(activeProgressItem(result)?.step || result?.current_stage || "");
  return STAGE_LABELS[step] || (phase === "starting" ? "Request submission" : phaseLabel(phase));
}

function assessmentUrl(path: string): string {
  if (typeof window !== "undefined") return new URL(`/api/nico${path}`, window.location.origin).href;
  return `${API_URL}${path}`;
}

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function parseResponse(response: Response): Promise<AssessmentResult> {
  let data: AssessmentResult & {detail?: AssessmentResult & {message?: string; code?: string}; error?: string};
  try {
    data = await response.json();
  } catch {
    throw new Error(`Assessment endpoint returned invalid JSON (${response.status}).`);
  }
  if (!response.ok) {
    throw new Error(data?.detail?.message || data?.detail?.code || data?.error || `Assessment request failed (${response.status}).`);
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

function ListBlock({items, empty = "No items returned."}: {items?: string[]; empty?: string}) {
  if (!items?.length) return <p className="muted">{empty}</p>;
  return <ul className="tight-list">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

export default function UnifiedAssessmentPage() {
  const [tier, setTierState] = useState<AssessmentTier>("express");
  const [repository, setRepository] = useState("BoneManTGRM/NICO");
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
    const requested = normalizeTier(new URLSearchParams(window.location.search).get("tier"));
    setTierState(requested);
    window.dispatchEvent(new CustomEvent(TIER_EVENT, {detail: {tier: requested}}));
    return () => { runSequence.current += 1; };
  }, []);

  useEffect(() => {
    if (!startedAt || !(phase === "starting" || phase === "running")) return;
    const update = () => setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, phase]);

  const copy = TIER_COPY[tier];
  const document = useMemo(() => assessmentDocument(tier, result), [tier, result]);
  const coverage = document?.evidence_coverage || result?.evidence_coverage;
  const score = document?.maturity_signal?.score;
  const sections = document?.sections || [];
  const running = phase === "starting" || phase === "running";
  const backendConfigured = Boolean(API_URL);
  const percent = calculatedProgress(tier, result, phase);
  const currentStage = stageLabel(result, phase);

  function selectTier(next: AssessmentTier) {
    if (running) return;
    setTierState(next);
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
    window.history.replaceState(window.history.state, "", `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
    window.dispatchEvent(new CustomEvent(TIER_EVENT, {detail: {tier: next}}));
  }

  function rememberMidRun(current: AssessmentResult) {
    const runId = String(current.run_id || "");
    if (!runId.startsWith("midrun_")) return;
    try {
      window.sessionStorage.setItem("nico.mid.active_run", runId);
    } catch {
      // The result still carries the exact run identity.
    }
    window.dispatchEvent(new CustomEvent(MID_RUN_EVENT, {detail: {run_id: runId}}));
  }

  async function continueAssessment(
    selectedTier: AssessmentTier,
    initial: AssessmentResult,
    currentScope: RunScope,
    sequence: number,
  ) {
    let current = initial;
    for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt += 1) {
      if (sequence !== runSequence.current) return;
      setResult(current);
      if (selectedTier === "mid") rememberMidRun(current);
      const stable = stablePhase(selectedTier, current);
      if (stable) {
        setPhase(stable);
        setPollAttempt(attempt);
        setMessage(stable === "review_required"
          ? `${TIER_COPY[selectedTier].eyebrow} completed every automated stage and stopped at the required human-review gate.`
          : stable === "complete"
            ? "Express completed its evidence, scoring, report, and truth-gate stages. Human review remains required before delivery."
            : `${TIER_COPY[selectedTier].eyebrow} stopped because a required stage failed or was blocked.`);
        return;
      }

      setPhase("running");
      setPollAttempt(attempt);
      setMessage(progressMessage(selectedTier, current, attempt));
      await sleep(POLL_INTERVAL_MS);
      if (sequence !== runSequence.current) return;

      const runId = String(current.run_id || "");
      if (!runId) throw new Error("The assessment response did not include a run ID for autonomous continuation.");
      const statusPath = selectedTier === "express"
        ? `/assessment/express-run/${encodeURIComponent(runId)}/status`
        : selectedTier === "mid"
          ? `/assessment/mid-run/${encodeURIComponent(runId)}/status`
          : `/assessment/full-run/${encodeURIComponent(runId)}/status`;
      const body: Record<string, unknown> = selectedTier === "express"
        ? {customer_id: current.customer_id || currentScope.customerId, project_id: current.project_id || currentScope.projectId}
        : {
            repository: current.repository || repository,
            customer_id: current.customer_id || currentScope.customerId,
            project_id: current.project_id || currentScope.projectId,
            client_name: clientName,
            project_name: projectName,
            authorized_by: "unified_assessment_requester",
            authorization_scope: "authorized defensive repository assessment",
            authorization_confirmed: true,
            authorized: true,
            timeframe_days: 180,
            run_scanners: true,
            refresh_full_evidence: true,
            auto_continue: true,
            scan_id: current.scanner?.scan_id || current.scanner_evidence?.scan_id || "",
          };
      if (selectedTier === "full") {
        body.mode = "full";
        body.build_reports = true;
        body.create_final_review_request = true;
        body.tools = FULL_TOOLS;
      }
      const response = await fetch(assessmentUrl(statusPath), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
        cache: "no-store",
      });
      current = await parseResponse(response);
    }

    setResult(current);
    setPhase("timed_out");
    setMessage(`Automatic continuation reached its bounded ${MAX_POLL_ATTEMPTS}-check limit. The exact run ID is preserved and can be reviewed in Recovery without starting a duplicate run.`);
  }

  async function runAssessment() {
    if (!backendConfigured) {
      setError("The assessment backend URL is not configured for this deployment.");
      return;
    }
    if (!authorized) {
      setError("Confirm that you own the target or have explicit permission to assess it.");
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
    setMessage(`Starting ${copy.eyebrow.toLowerCase()}...`);
    setPollAttempt(0);
    setStartedAt(Date.now());
    setElapsedSeconds(0);
    setCopied("");

    const common = {
      repository,
      customer_id: currentScope.customerId,
      project_id: currentScope.projectId,
      client_name: clientName,
      project_name: projectName,
      authorized_by: "unified_assessment_requester",
      authorization_scope: "authorized defensive repository assessment",
      authorization_confirmed: true,
      authorized: true,
      timeframe_days: 180,
      refresh_full_evidence: true,
    };

    try {
      const startPath = tier === "express" ? "/assessment/express-run" : tier === "mid" ? "/assessment/mid-run" : "/assessment/full-run";
      const payload = tier === "express"
        ? {...common, assessment_mode: "express"}
        : tier === "mid"
          ? {...common, run_scanners: true, auto_continue: true, tools: FULL_TOOLS}
          : {...common, mode: "full", run_scanners: true, build_reports: true, create_final_review_request: true, auto_continue: true, tools: FULL_TOOLS};
      const response = await fetch(assessmentUrl(startPath), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      const data = await parseResponse(response);
      if (sequence !== runSequence.current) return;
      setResult(data);
      if (tier === "mid") rememberMidRun(data);
      await continueAssessment(tier, data, currentScope, sequence);
    } catch (caught) {
      if (sequence !== runSequence.current) return;
      setPhase("failed");
      setError(caught instanceof Error ? caught.message : "Assessment failed.");
      setMessage("The run stopped without converting missing or failed evidence into a passing result.");
    }
  }

  async function copyMarkdown() {
    const markdown = result?.reports?.markdown;
    if (!markdown) return;
    await navigator.clipboard.writeText(markdown);
    setCopied("Markdown copied");
  }

  function downloadPdf() {
    const encoded = result?.reports?.pdf_base64;
    if (!encoded) {
      setError(result?.reports?.pdf_error || "A PDF was not returned for this draft report.");
      return;
    }
    saveBase64Pdf(encoded, result?.reports?.pdf_filename || `${tier}-nico-assessment.pdf`);
  }

  const scoreLabel = typeof score === "number" && Number.isFinite(score) ? `${score}/100` : "Not scored";
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent))
    ? `${coverage.label || "Evidence coverage"}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
    : "Coverage calculated after run";
  const elapsedLabel = `${Math.floor(elapsedSeconds / 60)}:${String(elapsedSeconds % 60).padStart(2, "0")}`;

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO ASSESSMENTS</p>
      <h1>One form. Three assessment depths.</h1>
      <p className="lead">Choose Express, Mid, or Full. NICO displays truthful backend stages, completes every automated step available for the tier, and stops at completion or a required human-review gate.</p>
    </section>

    <section id="assessment" className="section panel">
      <div className="section-head">
        <div><p className="eyebrow">{copy.eyebrow}</p><h2>{copy.title}</h2></div>
        <span className="status gray">{coverageLabel}</span>
      </div>
      <p className="summary-box">{copy.summary}</p>
      <div className={styles.tierGrid} aria-label="Assessment type">
        {(["express", "mid", "full"] as AssessmentTier[]).map((value) => <button
          type="button"
          key={value}
          className={tier === value ? "primary-button" : ""}
          aria-pressed={tier === value}
          disabled={running}
          onClick={() => selectTier(value)}
        >{value === "express" ? "Express" : value === "mid" ? "Mid" : "Full"}</button>)}
      </div>
      <details className="help-details"><summary>{tier === "express" ? "Express" : tier === "mid" ? "Mid" : "Full"} instructions</summary><ul>{copy.instructions.map((item) => <li key={item}>{item}</li>)}</ul></details>
      <p className="warning-box">Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.</p>
      <div className="form-grid">
        <label>Repository owner/name or GitHub URL<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="your-org/your-repo" disabled={running} /></label>
        <label>Client name, optional<input value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Client name" disabled={running} /></label>
        <label>Project name, optional<input value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" disabled={running} /></label>
      </div>
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} disabled={running} />I confirm I own this target or have explicit permission to assess it.</label>
      <button type="button" className="primary-button" disabled={!backendConfigured || !authorized || !repository.trim() || running} onClick={runAssessment}>
        {running ? `Running ${tier === "express" ? "Express" : tier === "mid" ? "Mid" : "Full"} automatically...` : `Run ${tier === "express" ? "Express" : tier === "mid" ? "Mid" : "Full"} assessment`}
      </button>
      {!backendConfigured ? <p className="error-box">The assessment backend URL is not configured.</p> : null}
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    <section className="section panel" aria-live="polite">
      <div className="section-head">
        <div><p className="eyebrow">AUTOMATED RUN STATE</p><h2>{result?.run_id || phaseLabel(phase)}</h2></div>
        <span className={statusClass(phaseStatus(phase))}>{phaseLabel(phase)}</span>
      </div>
      <p className={phase === "failed" ? "error-box" : phase === "review_required" ? "warning-box" : "summary-box"}>{message || "Select an assessment tier and run an authorized repository."}</p>
      {running ? <>
        <div className={styles.progressMeta}>
          <span><b>Current stage</b>{currentStage}</span>
          <span><b>Progress</b>{percent == null ? "Working" : `${Math.round(percent)}%`}</span>
          <span><b>Elapsed</b>{elapsedLabel}</span>
          <span><b>Status checks</b>{pollAttempt}</span>
        </div>
        <div
          className={`${styles.progressBar} ${percent == null ? styles.indeterminate : ""}`}
          role="progressbar"
          aria-label={`${currentStage} in progress`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent == null ? undefined : Math.round(percent)}
        ><span style={percent == null ? undefined : {width: `${Math.max(2, Math.min(100, percent))}%`}} /></div>
      </> : null}
      {phase === "timed_out" && result?.run_id ? <p className="warning-box">Run ID {result.run_id} was preserved. Review it through <a href="/operations/recovery">Recovery</a>; do not start a duplicate run unless the saved run is explicitly terminal.</p> : null}

      {result ? <>
        <div className="grid four target-grid">
          <article><b>Run ID</b><span>{result.run_id || "not recorded"}</span></article>
          <article><b>Scanner</b><span>{currentScannerStatus(result)}</span></article>
          <article><b>Report</b><span>{currentReportStatus(tier, result)}</span></article>
          <article><b>Human review</b><span>{currentReviewStatus(tier, result)}</span></article>
        </div>
        <div className="grid four target-grid">
          <article><b>Maturity signal</b><span>{document?.maturity_signal?.level || "Pending"}</span></article>
          <article><b>Technical score</b><span>{scoreLabel}</span></article>
          <article><b>Evidence readiness</b><span>{document?.maturity_signal?.evidence_readiness_score ?? "Pending"}</span></article>
          <article><b>Durable record</b><span>{result.persistence?.durable === true ? "Yes" : result.persistence?.recorded ? "Recorded, not durable" : "Not verified"}</span></article>
        </div>
        {document?.executive_summary ? <p className="summary-box">{document.executive_summary}</p> : null}

        {result.progress?.length ? <div className={styles.timeline}>{result.progress.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
          <div className="result-head"><b>{STAGE_LABELS[String(item.step || "")] || String(item.step || "step").replaceAll("_", " ")}</b><span className={statusClass(item.status)}>{item.status || "unknown"}</span></div>
          <p>{item.message || "No message returned."}</p>
          {item.evidence && Object.keys(item.evidence).length ? <details className="help-details"><summary>Step evidence</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}
        </article>)}</div> : null}

        {sections.length ? <div className="results-grid">{sections.map((section, index) => {
          const sectionScore = typeof section.score === "number" && section.status !== "gray" ? `${section.score}/100` : "Not scored";
          return <article className="result-card" key={section.id || `${section.label}-${index}`}>
            <div className="result-head"><b>{section.label || section.id}</b><span className={statusClass(section.status)}>{section.status || "unknown"} · {sectionScore}</span></div>
            <p>{section.summary}</p>
            <details className="help-details"><summary>Evidence ({section.evidence?.length || 0})</summary><ListBlock items={section.evidence} /></details>
            {section.findings?.length ? <details className="help-details"><summary>Findings ({section.findings.length})</summary><ListBlock items={section.findings} /></details> : null}
            {section.unavailable?.length ? <details className="help-details"><summary>Unavailable or limited evidence ({section.unavailable.length})</summary><ListBlock items={section.unavailable} /></details> : null}
          </article>;
        })}</div> : null}

        <div className="report-actions">
          <button type="button" disabled={!result.reports?.markdown} onClick={copyMarkdown}>Copy Markdown</button>
          <button type="button" disabled={!result.reports?.pdf_base64} onClick={downloadPdf}>Download draft PDF</button>
          {tier === "mid" && result.run_id && phase === "review_required" ? <a className="secondary-link" href={`/mid-review?run_id=${encodeURIComponent(result.run_id)}&customer_id=${encodeURIComponent(scope.customerId)}&project_id=${encodeURIComponent(scope.projectId)}`}>Open human review</a> : null}
          {copied ? <span className="muted">{copied}</span> : null}
        </div>
        {phase === "review_required" ? <p className="warning-box">Automated assessment work is complete. NICO did not approve findings, create a delivery link, or deliver the report. A human must review the exact evidence-bound artifact.</p> : null}
        {document?.unavailable_data_notes?.length ? <details className="help-details"><summary>Assessment-wide unavailable evidence ({document.unavailable_data_notes.length})</summary><ListBlock items={document.unavailable_data_notes} /></details> : null}
      </> : null}
    </section>
  </main>;
}
