import type {Assessment, Copy, Evidence, Phase, ProgressItem, Report, Result, Section, Service, Stage} from "./assessmentTypes";

const TRANSIENT_HTTP_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const BROWSER_EVIDENCE_KEY_LIMIT = 24;
const BROWSER_ARRAY_PREVIEW_LIMIT = 8;

export class AssessmentApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId: string;

  constructor(
    message: string,
    options: {status: number; code?: string; retryable?: boolean; requestId?: string},
  ) {
    super(message);
    this.name = "AssessmentApiError";
    this.status = options.status;
    this.code = String(options.code || "");
    this.retryable = options.retryable ?? TRANSIENT_HTTP_STATUS.has(options.status);
    this.requestId = String(options.requestId || "");
  }
}

export function scopeId(prefix: string, value: string, fallback: string): string {
  const slug = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

export function toneKey(status?: string): "green" | "yellow" | "red" | "gray" {
  const value = String(status || "").toLowerCase().replace(/[\s-]+/g, "_");
  if (["green", "complete", "completed", "attached", "verified", "approved", "accepted", "review_required"].includes(value)) return "green";
  if (["yellow", "partial", "pending", "running", "queued", "planned", "ready", "starting", "checking", "unavailable", "skipped", "review_limited"].includes(value)) return "yellow";
  if (["red", "failed", "blocked", "error", "timed_out", "interrupted", "rejected", "critical"].includes(value)) return "red";
  return "gray";
}

export function statusClass(status?: string): string {
  return `status ${toneKey(status)}`;
}

export function scoreTone(score: number | null | undefined): "green" | "yellow" | "red" | "gray" {
  if (typeof score !== "number" || !Number.isFinite(score)) return "gray";
  if (score >= 80) return "green";
  if (score >= 70) return "yellow";
  return "red";
}

export function scoreClass(score: number | null | undefined): string {
  return `status ${scoreTone(score)}`;
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
  if (["complete", "completed", "attached", "green"].includes(value)) return copy.phases.complete;
  if (["verified", "approved", "accepted"].includes(value)) return copy.verifiedLabel || "Verified";
  if (value === "partial") return copy.partialLabel || "Partial";
  if (value === "review_limited") return copy.reviewLimitedLabel || (copy.heroEyebrow.startsWith("EVALUACIÓN") ? "Revisión limitada" : "Review limited");
  if (["review_required", "human_review_required"].includes(value)) return copy.phases.review_required;
  if (value === "checking") return copy.phases.checking;
  if (["running", "starting", "in_progress"].includes(value)) return copy.phases.running;
  if (value === "unavailable") return copy.phases.unavailable;
  if (["pending", "queued", "planned", "ready", "not_started"].includes(value)) return copy.awaitingStage;
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return copy.phases.failed;
  if (["timed_out", "timeout"].includes(value)) return copy.phases.timed_out;
  if (value.includes("unavailable") || value === "not_available") return copy.unavailableStatus;
  if (value === "not_applicable") return copy.notApplicable;
  return value.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export function persistenceStatus(persistence: Result["persistence"], phase: Phase, copy: Copy): string {
  const verified = persistence?.durable === true || persistence?.durability_verified === true;
  if (verified) return copy.verifiedPersistentStorage;
  return ["review_required", "complete", "unavailable", "failed", "timed_out"].includes(phase) ? copy.notVerified : copy.verificationPending;
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

function compactBrowserValue(value: unknown): unknown {
  if (value == null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    const primitives = value.slice(0, BROWSER_ARRAY_PREVIEW_LIMIT).filter((item) => item == null || ["string", "number", "boolean"].includes(typeof item));
    return {
      type: "array",
      item_count: value.length,
      preview: primitives,
      preview_truncated: value.length > primitives.length,
    };
  }
  if (typeof value === "object") {
    return {
      type: "object",
      key_count: Object.keys(value as Record<string, unknown>).length,
      keys: Object.keys(value as Record<string, unknown>).slice(0, BROWSER_ARRAY_PREVIEW_LIMIT),
    };
  }
  return String(value);
}

export function browserEvidencePreview(value: Evidence | undefined): Record<string, unknown> | undefined {
  const record = evidenceRecord(value);
  const entries = Object.entries(record);
  if (!entries.length) return undefined;
  const preview: Record<string, unknown> = {};
  for (const [key, item] of entries.slice(0, BROWSER_EVIDENCE_KEY_LIMIT)) preview[key] = compactBrowserValue(item);
  preview._browser_rendering_boundary = {
    bounded: entries.length > BROWSER_EVIDENCE_KEY_LIMIT || entries.some(([, item]) => item != null && typeof item === "object"),
    top_level_key_count: entries.length,
    keys_retained: Math.min(entries.length, BROWSER_EVIDENCE_KEY_LIMIT),
    complete_evidence: "Retained in the canonical report and machine-readable assessment artifacts.",
  };
  return preview;
}

export function assessmentFor(_service: Service, result: Result | null): Assessment | null {
  if (!result) return null;
  return stage(result, "final_comprehensive_report_generation")?.assessment
    || stage(result, "evidence_reconciliation_and_scoring")?.assessment
    || result.assessment
    || null;
}

export function reportFor(_service: Service, result: Result | null): Report | null {
  if (!result) return null;
  for (const id of ["final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation"]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    if (report) return report;
  }
  return result.reports || null;
}

export function terminal(_service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) return "failed";
  if (value === "review_required" || (["complete", "completed"].includes(value) && result.human_review_required !== false)) return "review_required";
  return null;
}

export function progressFor(_service: Service, result: Result | null): ProgressItem[] {
  if (!result) return [];
  return Object.entries(result.record?.stage_results || {}).map(([stepId, value]) => {
    const normalizedStatus = String(value.status || "").toLowerCase().replace(/[\s-]+/g, "_");
    const completed = ["complete", "completed", "success", "passed", "verified"].includes(normalizedStatus);
    return {
      step: stepId,
      status: value.status,
      message: value.message || value.summary || (completed ? "✓" : undefined),
      evidence: browserEvidencePreview(value.evidence),
    };
  });
}

export function progressPercent(phase: Phase, result: Result | null, running: boolean): number {
  if (phase === "complete" || phase === "review_required") return 100;
  const raw = Number(result?.progress_percent ?? result?.record?.progress_percent);
  return Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : running ? 5 : 0;
}

export function immutableCommitFor(result: Result | null): string {
  const snapshot = evidenceRecord(stage(result, "immutable_repository_snapshot")?.evidence);
  const repository = evidenceRecord(stage(result, "repository_and_delivery_evidence")?.evidence);
  return result?.commit_sha || result?.repository_snapshot?.commit_sha || String(snapshot.commit_sha || snapshot.snapshot_commit_sha || repository.snapshot_commit_sha || "");
}

export function scannerStatusFor(_service: Service, result: Result | null, running: boolean): unknown {
  return stage(result, "dependency_security_static_analysis")?.status
    || stage(result, "deep_scanner_triage")?.status
    || (running ? "running" : "pending");
}

export async function parseJson(response: Response, copy: Copy): Promise<Result> {
  type ErrorDetail = {message?: unknown; code?: unknown; retryable?: unknown; request_id?: unknown};
  let data: Result & {detail?: string | ErrorDetail; error?: string};
  try {
    data = await response.json() as Result & {detail?: string | ErrorDetail; error?: string};
  } catch {
    throw new AssessmentApiError(copy.invalidJson, {
      status: response.status,
      code: "assessment_invalid_json",
      retryable: TRANSIENT_HTTP_STATUS.has(response.status),
      requestId: response.headers.get("x-request-id") || "",
    });
  }
  if (!response.ok) {
    const detail = data.detail && typeof data.detail === "object" ? data.detail : {};
    const message = typeof data.detail === "string"
      ? data.detail
      : String(detail.message || detail.code || data.error || `${copy.backendError} (${response.status})`);
    throw new AssessmentApiError(message, {
      status: response.status,
      code: String(detail.code || data.error || "assessment_request_failed"),
      retryable: typeof detail.retryable === "boolean"
        ? detail.retryable
        : TRANSIENT_HTTP_STATUS.has(response.status),
      requestId: String(detail.request_id || response.headers.get("x-request-id") || ""),
    });
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
  const assurance = String(section.assurance_status || section.assurance_label || section.presented_status || section.status || "unavailable");
  const risk = String(section.risk_disposition || "");
  return {
    score,
    technicalTone: scoreTone(typeof value === "number" ? value : null),
    assuranceLabel: formatStatus(assurance, copy),
    assuranceTone: toneKey(assurance),
    risk,
    riskLabel: risk ? formatStatus(risk, copy) : "",
    riskTone: toneKey(risk),
  };
}
