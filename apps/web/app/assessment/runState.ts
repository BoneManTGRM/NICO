export type AssessmentTier = "express" | "mid" | "full";

export type RunSnapshot = {
  run_id?: string;
  current_stage?: string;
  progress_percent?: number;
  updated_at?: string;
  generated_at?: string;
  status?: string;
  progress?: Array<{step?: string; status?: string; message?: string}>;
};

const STAGE_ORDER: Record<string, number> = {
  request_accepted: 10,
  repo_evidence: 20,
  repository_evidence: 20,
  scanner_worker: 30,
  scanner_reconciliation: 40,
  evidence_attachment: 50,
  accuracy_review: 60,
  scoring: 70,
  score_reconciliation: 75,
  reports: 80,
  report_generation: 80,
  approval_request: 90,
  truth_and_review_gates: 95,
  complete: 100,
};

const TERMINAL = new Set(["complete", "completed", "review_required", "failed", "blocked", "error", "rejected", "interrupted", "timed_out"]);

function activeStep(snapshot: RunSnapshot | null | undefined): string {
  if (!snapshot) return "";
  const active = snapshot.progress?.find((item) => ["queued", "running", "pending", "planned"].includes(String(item.status || "").toLowerCase()));
  return String(active?.step || snapshot.current_stage || "");
}

function timestamp(snapshot: RunSnapshot | null | undefined): number {
  const value = snapshot?.updated_at || snapshot?.generated_at;
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}

function progress(snapshot: RunSnapshot | null | undefined): number {
  const explicit = Number(snapshot?.progress_percent);
  if (Number.isFinite(explicit)) return Math.max(0, Math.min(100, explicit));
  return STAGE_ORDER[activeStep(snapshot)] || 0;
}

function stageRank(snapshot: RunSnapshot | null | undefined): number {
  return STAGE_ORDER[activeStep(snapshot)] || 0;
}

export function isTerminalRun(snapshot: RunSnapshot | null | undefined): boolean {
  return TERMINAL.has(String(snapshot?.status || "").toLowerCase());
}

export function reconcileRunSnapshot(previous: RunSnapshot | null, incoming: RunSnapshot): RunSnapshot {
  if (!previous || previous.run_id !== incoming.run_id) return incoming;
  if (isTerminalRun(previous) && !isTerminalRun(incoming)) return previous;

  const previousRank = stageRank(previous);
  const incomingRank = stageRank(incoming);
  const previousProgress = progress(previous);
  const incomingProgress = progress(incoming);
  const incomingIsOlder = timestamp(incoming) > 0 && timestamp(previous) > timestamp(incoming);
  const regresses = incomingRank < previousRank || incomingProgress < previousProgress;

  if (incomingIsOlder || regresses) return previous;
  return incoming;
}

export function friendlyAssessmentName(
  tier: AssessmentTier,
  repository?: string,
  clientName?: string,
  projectName?: string,
  generatedAt?: string,
): string {
  const tierLabel = tier === "express" ? "Express Assessment" : tier === "mid" ? "Mid Assessment" : "Full Assessment";
  const subject = projectName?.trim() || clientName?.trim() || repository?.trim() || "Authorized Repository";
  const parsed = generatedAt ? new Date(generatedAt) : new Date();
  const date = Number.isNaN(parsed.getTime()) ? new Date() : parsed;
  const dateLabel = new Intl.DateTimeFormat("en", {day: "2-digit", month: "short", year: "numeric"}).format(date);
  return `${tierLabel} · ${subject} · ${dateLabel}`;
}

export function truthGateHasStalled(
  snapshot: RunSnapshot | null | undefined,
  unchangedSinceMs: number,
  nowMs = Date.now(),
  thresholdMs = 5 * 60 * 1000,
): boolean {
  if (!snapshot || isTerminalRun(snapshot)) return false;
  return activeStep(snapshot) === "truth_and_review_gates" && nowMs - unchangedSinceMs >= thresholdMs;
}
