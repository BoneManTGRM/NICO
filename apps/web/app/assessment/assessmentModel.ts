import type {
  Assessment,
  Copy,
  Evidence,
  Phase,
  ProgressItem,
  Report,
  Result,
  Section,
  Service,
  Stage,
} from "./assessmentTypes";

export function normalizeService(value: string | null): Service {
  return ["comprehensive", "strategic", "mid", "full", "deep"].includes(String(value || "").toLowerCase())
    ? "comprehensive"
    : "express";
}

export function publicDepth(service: Service): "core" | "strategic" {
  return service === "express" ? "core" : "strategic";
}

export function scopeId(prefix: string, value: string, fallback: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

export function statusClass(status?: string): string {
  const value = String(status || "").toLowerCase();
  if (["green", "complete", "completed", "attached", "verified", "review_required"].includes(value)) return "status green";
  if (["yellow", "pending", "running", "queued", "planned", "ready", "starting", "skipped", "review_limited"].includes(value)) return "status yellow";
  if (["red", "failed", "blocked", "error", "unavailable", "timed_out", "interrupted", "rejected"].includes(value)) return "status red";
  return "status gray";
}

export function scoreClass(score: number | null | undefined): string {
  if (typeof score !== "number" || !Number.isFinite(score)) return "status gray";
  if (score >= 80) return "status green";
  if (score >= 70) return "status yellow";
  return "status red";
}

export function compactIdentifier(value: string, lead = 12, tail = 8): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= lead + tail + 1) return normalized;
  return `${normalized.slice(0, lead)}…${normalized.slice(-tail)}`;
}

export function formatStatus(status: unknown, copy: Copy): string {
  const raw = String(status || "").trim();
  const value = raw.toLowerCase().replace(/[\s-]+/g, "_");
  if (!value) return copy.notVerified;
  if (value.includes("review_limited") && value.includes("not_scored")) return copy.reviewLimitedNotScored;
  if (["complete", "completed", "attached", "verified", "green"].includes(value)) return copy.phases.complete;
  if (value === "review_limited") return localeLimited(copy);
  if (["review_required", "human_review_required"].includes(value)) return copy.phases.review_required;
  if (["running", "starting", "in_progress"].includes(value)) return copy.phases.running;
  if (["pending", "queued", "planned", "ready", "not_started"].includes(value)) return copy.awaitingStage;
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return copy.phases.failed;
  if (["timed_out", "timeout"].includes(value)) return copy.phases.timed_out;
  if (value.includes("unavailable") || value === "not_available") return copy.unavailableStatus;
  if (value === "not_applicable") return copy.notApplicable;
  return value.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function localeLimited(copy: Copy): string {
  return copy.heroEyebrow.startsWith("EVALUACIÓN") ? "REVISIÓN LIMITADA" : "REVIEW LIMITED";
}

export function persistenceStatus(persistence: Result["persistence"], phase: Phase, copy: Copy): string {
  const verified = persistence?.durable === true || persistence?.durability_verified === true;
  if (verified) return copy.verifiedPersistentStorage;
  const terminalPhase = ["review_required", "complete", "failed", "timed_out"].includes(phase);
  return terminalPhase ? copy.notVerified : copy.verificationPending;
}

export function apiUrl(path: string): string {
  return new URL(`/api/nico${path}`, window.location.origin).href;
}

export function stage(result: Result | null, id: string): Stage | null {
  const value = result?.record?.stage_results?.[id];
  return value && typeof value === "object" ? value : null;
}

export function evidenceRecord(value: Evidence | undefined): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function assessmentFor(service: Service, result: Result | null): Assessment | null {
  if (!result) return null;
  if (service === "express") return result.assessment || result;
  return stage(result, "final_comprehensive_report_generation")?.assessment
    || stage(result, "evidence_reconciliation_and_scoring")?.assessment
    || result.assessment
    || null;
}

export function reportFor(service: Service, result: Result | null): Report | null {
  if (!result) return null;
  if (service === "express") return result.reports || null;
  for (const id of ["final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation"]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    if (report) return report;
  }
  return result.reports || null;
}

export function terminal(service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return "failed";
  if (service === "express" && ["complete", "completed"].includes(value)) return "complete";
  if (service === "comprehensive" && (value === "review_required" || (["complete", "completed"].includes(value) && result.human_review_required !== false))) return "review_required";
  return null;
}

export function progressFor(service: Service, result: Result | null): ProgressItem[] {
  if (!result) return [];
  if (service === "express") return result.progress || [];
  return Object.entries(result.record?.stage_results || {}).map(([stepId, value]) => ({
    step: stepId,
    status: value.status,
    message: value.message || value.summary,
    evidence: value.evidence && !Array.isArray(value.evidence) ? value.evidence : undefined,
  }));
}

export function progressPercent(phase: Phase, result: Result | null, running: boolean): number {
  if (phase === "complete" || phase === "review_required") return 100;
  const raw = Number(result?.progress_percent ?? result?.record?.progress_percent);
  return Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : running ? 5 : 0;
}

export function immutableCommitFor(result: Result | null): string {
  const snapshot = evidenceRecord(stage(result, "immutable_repository_snapshot")?.evidence);
  const repository = evidenceRecord(stage(result, "repository_and_delivery_evidence")?.evidence);
  return result?.commit_sha
    || result?.repository_snapshot?.commit_sha
    || String(snapshot.commit_sha || snapshot.snapshot_commit_sha || repository.snapshot_commit_sha || "");
}

export function scannerStatusFor(service: Service, result: Result | null, running: boolean): unknown {
  if (service === "express") {
    return result?.scanner_evidence?.scanner_status || result?.scanner?.status || result?.scanner_evidence?.status || (running ? "running" : "pending");
  }
  return stage(result, "dependency_security_static_analysis")?.status
    || stage(result, "deep_scanner_triage")?.status
    || (running ? "running" : "pending");
}

export async function parseJson(response: Response, copy: Copy): Promise<Result> {
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

export async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function savePdf(encoded: string, filename: string): void {
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

export function sectionPresentation(section: Section, copy: Copy) {
  const value = section.presented_score ?? section.score;
  const score = typeof value === "number" ? `${value}/100` : copy.notScored;
  const assurance = String(section.assurance_label || section.presented_status || section.status || "unknown");
  const risk = String(section.risk_disposition || "");
  return {
    scoreValue: typeof value === "number" ? value : null,
    score,
    technicalClass: scoreClass(typeof value === "number" ? value : null),
    assurance,
    assuranceLabel: formatStatus(assurance, copy),
    assuranceClass: statusClass(assurance),
    risk,
    riskLabel: risk ? formatStatus(risk, copy) : "",
    riskClass: statusClass(risk),
  };
}
