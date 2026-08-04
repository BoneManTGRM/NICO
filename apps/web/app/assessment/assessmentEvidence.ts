import type {
  Assessment,
  Evidence,
  Phase,
  ProgressItem,
  Report,
  Result,
  Service,
  Stage,
} from "./assessmentTypes";

const BROWSER_EVIDENCE_KEY_LIMIT = 24;
const BROWSER_ARRAY_PREVIEW_LIMIT = 8;

export function stage(result: Result | null, id: string): Stage | null {
  const value = result?.record?.stage_results?.[id];
  return value && typeof value === "object" ? value : null;
}

export function evidenceRecord(
  value: Evidence | undefined,
): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function compactBrowserValue(value: unknown): unknown {
  if (
    value == null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    const primitives = value
      .slice(0, BROWSER_ARRAY_PREVIEW_LIMIT)
      .filter(
        (item) =>
          item == null || ["string", "number", "boolean"].includes(typeof item),
      );
    return {
      type: "array",
      item_count: value.length,
      preview: primitives,
      preview_truncated: value.length > primitives.length,
    };
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return {
      type: "object",
      key_count: Object.keys(record).length,
      keys: Object.keys(record).slice(0, BROWSER_ARRAY_PREVIEW_LIMIT),
    };
  }
  return String(value);
}

export function browserEvidencePreview(
  value: Evidence | undefined,
): Record<string, unknown> | undefined {
  const record = evidenceRecord(value);
  const entries = Object.entries(record);
  if (!entries.length) {
    return undefined;
  }
  const preview: Record<string, unknown> = {};
  for (const [key, item] of entries.slice(0, BROWSER_EVIDENCE_KEY_LIMIT)) {
    preview[key] = compactBrowserValue(item);
  }
  preview._browser_rendering_boundary = {
    bounded:
      entries.length > BROWSER_EVIDENCE_KEY_LIMIT ||
      entries.some(([, item]) => item != null && typeof item === "object"),
    top_level_key_count: entries.length,
    keys_retained: Math.min(entries.length, BROWSER_EVIDENCE_KEY_LIMIT),
    complete_evidence:
      "Retained in the canonical report and machine-readable assessment artifacts.",
  };
  return preview;
}

function assessmentRecord(value: unknown): Assessment | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Assessment)
    : null;
}

function canonicalReportAssessment(result: Result): Assessment | null {
  for (const id of [
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
  ]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    const canonical = report?.json;
    if (!canonical || typeof canonical !== "object" || Array.isArray(canonical)) {
      continue;
    }
    const assessment = assessmentRecord(
      (canonical as Record<string, unknown>).assessment,
    );
    if (assessment) {
      return assessment;
    }
  }
  const directCanonical = result.reports?.json;
  if (
    directCanonical &&
    typeof directCanonical === "object" &&
    !Array.isArray(directCanonical)
  ) {
    return assessmentRecord(
      (directCanonical as Record<string, unknown>).assessment,
    );
  }
  return null;
}

function assessmentCompleteness(value: Assessment): number {
  const maturity = value.maturity_signal;
  const score = maturity?.presented_score ?? maturity?.score;
  const sections = Array.isArray(value.sections) ? value.sections.length : 0;
  return (
    (typeof score === "number" && Number.isFinite(score) ? 1000 : 0) +
    sections * 10 +
    (value.executive_summary ? 5 : 0) +
    (value.evidence_coverage ? 3 : 0) +
    (Array.isArray(value.unavailable_data_notes)
      ? value.unavailable_data_notes.length
      : 0)
  );
}

export function assessmentFor(
  _service: Service,
  result: Result | null,
): Assessment | null {
  if (!result) {
    return null;
  }
  const candidates = [
    canonicalReportAssessment(result),
    stage(result, "final_comprehensive_report_generation")?.assessment || null,
    stage(result, "evidence_reconciliation_and_scoring")?.assessment || null,
    result.assessment || null,
  ].filter((value): value is Assessment => Boolean(value));
  if (!candidates.length) {
    return null;
  }
  return candidates.reduce((best, candidate) =>
    assessmentCompleteness(candidate) > assessmentCompleteness(best)
      ? candidate
      : best,
  );
}

export function reportFor(
  _service: Service,
  result: Result | null,
): Report | null {
  if (!result) {
    return null;
  }
  for (const id of [
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
  ]) {
    const value = stage(result, id);
    const report = value?.report_package || value?.reports;
    if (report) {
      return report;
    }
  }
  return result.reports || null;
}

type CompletionMetric = {
  label: string;
  completed: number | null;
  total: number | null;
  percent: number | null;
  definition: string;
};

export type EvidenceCompletionView = {
  automatable: CompletionMetric;
  disposition: CompletionMetric;
  analyzers: CompletionMetric;
  overall: CompletionMetric & {gapPercent: number | null};
};

function completionMetric(
  value: unknown,
  fallbackLabel: string,
): CompletionMetric {
  const record =
    value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  const percent =
    typeof record.percent === "number" && Number.isFinite(record.percent)
      ? Math.max(0, Math.min(100, Math.round(record.percent)))
      : null;
  return {
    label: String(record.label || fallbackLabel),
    completed: typeof record.completed === "number" ? record.completed : null,
    total: typeof record.total === "number" ? record.total : null,
    percent,
    definition: String(record.definition || ""),
  };
}

export function evidenceCompletionFor(
  assessment: Assessment | null,
): EvidenceCompletionView | null {
  if (!assessment) {
    return null;
  }
  const contract = assessment.evidence_completion_contract;
  if (!contract || typeof contract !== "object" || Array.isArray(contract)) {
    return null;
  }
  const record = contract as Record<string, unknown>;
  const overall = completionMetric(
    record.overall_engagement_evidence,
    "Overall engagement evidence",
  );
  const overallRecord =
    record.overall_engagement_evidence &&
    typeof record.overall_engagement_evidence === "object"
      ? (record.overall_engagement_evidence as Record<string, unknown>)
      : {};
  return {
    automatable: completionMetric(
      record.automatable_repository_evidence,
      "Automatable repository evidence processed",
    ),
    disposition: completionMetric(
      record.required_evidence_disposition,
      "Required evidence disposition",
    ),
    analyzers: completionMetric(
      record.analyzer_completion,
      "Successful analyzer completion",
    ),
    overall: {
      ...overall,
      gapPercent:
        typeof overallRecord.gap_percent === "number"
          ? overallRecord.gap_percent
          : null,
    },
  };
}

export type InternalReviewState = {
  approved: boolean;
  completed: boolean;
  deliveryAllowed: boolean;
  status: string;
};

export function internalReviewStateFor(
  result: Result | null,
): InternalReviewState {
  const record =
    result?.record && typeof result.record === "object"
      ? (result.record as Record<string, unknown>)
      : {};
  const status = String(result?.status || record.status || "").toLowerCase();
  const deliveryAllowed =
    result?.client_delivery_allowed === true ||
    record.client_delivery_allowed === true;
  const completed =
    result?.human_review_completed === true ||
    record.human_review_completed === true ||
    status === "approved" ||
    status === "rejected";
  return {
    approved: status === "approved" && deliveryAllowed,
    completed,
    deliveryAllowed,
    status,
  };
}

export function internalReviewHrefFor(
  result: Result | null,
  locale: string,
): string {
  const record =
    result?.record && typeof result.record === "object"
      ? (result.record as Record<string, unknown>)
      : {};
  const identity =
    record.identity &&
    typeof record.identity === "object" &&
    !Array.isArray(record.identity)
      ? (record.identity as Record<string, unknown>)
      : {};
  const params = new URLSearchParams({
    service: "comprehensive",
    run_id: String(result?.run_id || identity.run_id || ""),
    customer_id: String(
      result?.customer_id || identity.customer_id || "default_customer",
    ),
    project_id: String(
      result?.project_id || identity.project_id || "default_project",
    ),
    lang: locale === "es-MX" ? "es-MX" : "en",
  });
  return `/operations/final-review?${params.toString()}`;
}

export function terminal(_service: Service, result: Result): Phase | null {
  const value = String(result.status || result.record?.status || "").toLowerCase();
  const deliveryAllowed =
    result.client_delivery_allowed === true ||
    result.record?.client_delivery_allowed === true;
  if (value === "approved" && deliveryAllowed) {
    return "complete";
  }
  if (
    ["failed", "blocked", "error", "rejected", "interrupted"].includes(value)
  ) {
    return "failed";
  }
  if (
    value === "review_required" ||
    (["complete", "completed"].includes(value) &&
      result.human_review_required !== false)
  ) {
    return "review_required";
  }
  return null;
}

export function progressFor(
  _service: Service,
  result: Result | null,
): ProgressItem[] {
  if (!result) {
    return [];
  }
  return Object.entries(result.record?.stage_results || {}).map(
    ([stepId, value]) => {
      const normalizedStatus = String(value.status || "")
        .toLowerCase()
        .replace(/[\s-]+/g, "_");
      const completed = [
        "complete",
        "completed",
        "success",
        "passed",
        "verified",
      ].includes(normalizedStatus);
      return {
        step: stepId,
        status: value.status,
        message: value.message || value.summary || (completed ? "✓" : undefined),
        evidence: browserEvidencePreview(value.evidence),
      };
    },
  );
}

export function progressPercent(
  phase: Phase,
  result: Result | null,
  running: boolean,
): number {
  if (phase === "complete" || phase === "review_required") {
    return 100;
  }
  const raw = Number(result?.progress_percent ?? result?.record?.progress_percent);
  return Number.isFinite(raw)
    ? Math.max(0, Math.min(100, raw))
    : running
      ? 5
      : 0;
}

export function immutableCommitFor(result: Result | null): string {
  const snapshot = evidenceRecord(
    stage(result, "immutable_repository_snapshot")?.evidence,
  );
  const repository = evidenceRecord(
    stage(result, "repository_and_delivery_evidence")?.evidence,
  );
  return (
    result?.commit_sha ||
    result?.repository_snapshot?.commit_sha ||
    String(
      snapshot.commit_sha ||
        snapshot.snapshot_commit_sha ||
        repository.snapshot_commit_sha ||
        "",
    )
  );
}

export function scannerStatusFor(
  _service: Service,
  result: Result | null,
  running: boolean,
): unknown {
  return (
    stage(result, "dependency_security_static_analysis")?.status ||
    stage(result, "deep_scanner_triage")?.status ||
    (running ? "running" : "pending")
  );
}
