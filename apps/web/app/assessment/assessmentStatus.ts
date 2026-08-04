import type {Copy, Phase, Result, Section} from "./assessmentTypes";

export function scopeId(prefix: string, value: string, fallback: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 72);
  return slug ? `${prefix}_${slug}` : fallback;
}

export function toneKey(status?: string): "green" | "yellow" | "red" | "gray" {
  const value = String(status || "")
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  if (
    [
      "green",
      "complete",
      "completed",
      "attached",
      "verified",
      "approved",
      "accepted",
      "review_required",
    ].includes(value)
  ) {
    return "green";
  }
  if (
    [
      "yellow",
      "partial",
      "pending",
      "running",
      "queued",
      "planned",
      "ready",
      "starting",
      "checking",
      "unavailable",
      "skipped",
      "review_limited",
    ].includes(value)
  ) {
    return "yellow";
  }
  if (
    [
      "red",
      "failed",
      "blocked",
      "error",
      "timed_out",
      "interrupted",
      "rejected",
      "critical",
    ].includes(value)
  ) {
    return "red";
  }
  return "gray";
}

export function statusClass(status?: string): string {
  return `status ${toneKey(status)}`;
}

export function scoreTone(
  score: number | null | undefined,
): "green" | "yellow" | "red" | "gray" {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return "gray";
  }
  if (score >= 80) {
    return "green";
  }
  if (score >= 70) {
    return "yellow";
  }
  return "red";
}

export function scoreClass(score: number | null | undefined): string {
  return `status ${scoreTone(score)}`;
}

export function compactIdentifier(
  value: string,
  lead = 12,
  tail = 8,
): string {
  const normalized = String(value || "").trim();
  if (normalized.length <= lead + tail + 1) {
    return normalized;
  }
  return `${normalized.slice(0, lead)}…${normalized.slice(-tail)}`;
}

export function formatStatus(status: unknown, copy: Copy): string {
  const raw = String(status || "").trim();
  const value = raw.toLowerCase().replace(/[\s-]+/g, "_");
  if (!value) {
    return copy.notVerified;
  }
  if (value.includes("review_limited") && value.includes("not_scored")) {
    return copy.reviewLimitedNotScored;
  }
  if (["complete", "completed", "attached", "green"].includes(value)) {
    return copy.phases.complete;
  }
  if (["verified", "approved", "accepted"].includes(value)) {
    return copy.verifiedLabel || "Verified";
  }
  if (value === "partial") {
    return copy.partialLabel || "Partial";
  }
  if (value === "review_limited") {
    return (
      copy.reviewLimitedLabel ||
      (copy.heroEyebrow.startsWith("EVALUACIÓN")
        ? "Revisión limitada"
        : "Review limited")
    );
  }
  if (["review_required", "human_review_required"].includes(value)) {
    return copy.phases.review_required;
  }
  if (value === "checking") {
    return copy.phases.checking;
  }
  if (["running", "starting", "in_progress"].includes(value)) {
    return copy.phases.running;
  }
  if (value === "unavailable") {
    return copy.phases.unavailable;
  }
  if (["pending", "queued", "planned", "ready", "not_started"].includes(value)) {
    return copy.awaitingStage;
  }
  if (["failed", "blocked", "error", "rejected", "interrupted"].includes(value)) {
    return copy.phases.failed;
  }
  if (["timed_out", "timeout"].includes(value)) {
    return copy.phases.timed_out;
  }
  if (value.includes("unavailable") || value === "not_available") {
    return copy.unavailableStatus;
  }
  if (value === "not_applicable") {
    return copy.notApplicable;
  }
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function persistenceStatus(
  persistence: Result["persistence"],
  phase: Phase,
  copy: Copy,
): string {
  const verified =
    persistence?.durable === true ||
    persistence?.durability_verified === true;
  if (verified) {
    return copy.verifiedPersistentStorage;
  }
  return [
    "review_required",
    "complete",
    "unavailable",
    "failed",
    "timed_out",
  ].includes(phase)
    ? copy.notVerified
    : copy.verificationPending;
}

export function sectionPresentation(section: Section, copy: Copy) {
  const value = section.presented_score ?? section.score;
  const score = typeof value === "number" ? `${value}/100` : copy.notScored;
  const assurance = String(
    section.assurance_status ||
      section.assurance_label ||
      section.presented_status ||
      section.status ||
      "unavailable",
  );
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
