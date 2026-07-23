"use client";

import {useEffect} from "react";

const STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)\/([^/?#]+)\/status$/;
const TERMINAL = new Set(["complete", "completed", "blocked", "failed", "error", "interrupted", "rejected"]);
const FINAL_GATE_MIN_PERCENT = 94;
const FINAL_GATE_MAX_POLLS = 20;

type JsonRecord = Record<string, unknown>;
type RunState = {highestPercent: number; highestStage: string; finalGatePolls: number; lastPayload?: JsonRecord};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.origin);
  } catch {
    return null;
  }
}

async function responsePayload(response: Response): Promise<JsonRecord | null> {
  try {
    const value = await response.clone().json();
    return value && typeof value === "object" ? value as JsonRecord : null;
  } catch {
    return null;
  }
}

function jsonResponse(original: Response, payload: JsonRecord): Response {
  const headers = new Headers(original.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Cache-Control", "no-store");
  return new Response(JSON.stringify(payload), {status: 200, statusText: "OK", headers});
}

function boundedPercent(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0;
}

function tierOf(payload: JsonRecord, runId: string): "express" | "mid" | "full" {
  const explicit = String(payload.assessment_type || payload.service_tier || "").toLowerCase();
  if (explicit === "mid" || runId.startsWith("midrun_")) return "mid";
  if (explicit === "full" || runId.startsWith("fullrun_")) return "full";
  return "express";
}

function completionEvidence(payload: JsonRecord): JsonRecord {
  const assessment = record(payload.assessment_completion);
  if (Object.keys(assessment).length) return assessment;
  return record(payload.express_completion);
}

function completionEvidenceReady(payload: JsonRecord): boolean {
  const completion = completionEvidence(payload);
  return String(completion.status || "").toLowerCase() === "complete_pending_human_review"
    && completion.report_formats_ready === true
    && completion.score_ready === true
    && completion.sections_ready === true
    && completion.human_review_required === true;
}

function reportReady(payload: JsonRecord, tier: "express" | "mid" | "full"): boolean {
  const reports = record(payload.reports);
  if (tier === "express") return Boolean(reports.markdown || reports.html || reports.pdf_base64 || reports.report_id);
  if (tier === "mid") {
    const midReport = record(payload.mid_report);
    return String(payload.report_generation_status || midReport.status || "").toLowerCase() === "complete"
      && Boolean(midReport.report_id || reports.report_id || reports.markdown || reports.pdf_base64);
  }
  return Boolean(reports.report_id || reports.markdown || reports.pdf_base64);
}

function reviewReady(payload: JsonRecord, tier: "express" | "mid" | "full"): boolean {
  if (tier === "express") return payload.human_review_required === true;
  if (tier === "mid") return Boolean(record(payload.approval_request).approval_id);
  return Boolean(record(payload.approval).approval_id || record(payload.approval_request).approval_id);
}

function reconcileProgress(previous: JsonRecord | undefined, next: JsonRecord, state: RunState): JsonRecord {
  const output = structuredClone(next);
  const nextPercent = boundedPercent(output.progress_percent);
  if (nextPercent >= state.highestPercent) {
    state.highestPercent = nextPercent;
    state.highestStage = String(output.current_stage || state.highestStage || "");
  } else {
    output.progress_percent = state.highestPercent;
    if (state.highestStage) output.current_stage = state.highestStage;
  }
  if (previous) {
    for (const field of ["repository_snapshot", "repository_evidence", "scanner", "scanner_evidence", "assessment", "reports", "mid_report", "approval", "approval_request", "persistence", "assessment_completion", "express_completion"] as const) {
      if (output[field] == null && previous[field] != null) output[field] = structuredClone(previous[field]);
    }
  }
  return output;
}

function waitingProjection(payload: JsonRecord, state: RunState, tier: string): JsonRecord {
  const output = structuredClone(payload);
  const reportsReady = reportReady(payload, tier as "express" | "mid" | "full");
  const reviewEvidenceReady = reviewReady(payload, tier as "express" | "mid" | "full");
  const completionContractPresent = completionEvidenceReady(payload);
  output.status = "running";
  output.current_stage = "truth_and_review_gates";
  output.progress_percent = Math.max(FINAL_GATE_MIN_PERCENT, Math.min(99, boundedPercent(output.progress_percent)));
  output.recovery_required = false;
  output.duplicate_start_allowed = false;
  output.human_review_required = true;
  output.client_ready = false;
  output.client_delivery_allowed = false;
  output.status_transport = {
    ...record(output.status_transport),
    status: "final_gate_waiting_for_backend_terminal_status",
    code: "assessment_final_gate_waiting",
    final_gate_polls: state.finalGatePolls,
    report_ready: reportsReady,
    review_ready: reviewEvidenceReady,
    completion_contract_present: completionContractPresent,
    exact_run_terminal_evidence: false,
    terminal_state_written: false,
    duplicate_start_allowed: false,
    recovery_required: false,
    browser_terminalization_forbidden: true,
  };
  const progress = Array.isArray(output.progress)
    ? output.progress.filter((item) => item && typeof item === "object") as JsonRecord[]
    : [];
  const waiting = {
    step: "truth_and_review_gates",
    status: "running",
    message: "Report artifacts may be available, but the exact backend run has not persisted a terminal status. Waiting for backend completion truth without starting a duplicate assessment.",
    evidence: {
      code: "assessment_final_gate_waiting",
      final_gate_polls: state.finalGatePolls,
      report_ready: reportsReady,
      review_ready: reviewEvidenceReady,
      completion_contract_present: completionContractPresent,
      exact_run_terminal_evidence: false,
      terminal_state_written: false,
      browser_terminalization_forbidden: true,
    },
  };
  const existingIndex = progress.findIndex((item) => String(item.step || "").toLowerCase() === "truth_and_review_gates");
  if (existingIndex >= 0) progress[existingIndex] = waiting;
  else progress.push(waiting);
  output.progress = progress;
  return output;
}

function normalizeFinalGate(payload: JsonRecord, runId: string, state: RunState): JsonRecord {
  const status = String(payload.status || "").toLowerCase();
  const tier = tierOf(payload, runId);

  // Only the backend's top-level exact-run status may end polling. Report files,
  // review flags, completion subdocuments, and browser timeouts are supporting
  // evidence; none may manufacture a top-level terminal state in the browser.
  if (TERMINAL.has(status)) {
    state.finalGatePolls = 0;
    if (status === "complete" || status === "completed") {
      state.highestPercent = 100;
      state.highestStage = "complete";
    }
    return payload;
  }

  const percent = boundedPercent(payload.progress_percent);
  const atFinalGate = percent >= FINAL_GATE_MIN_PERCENT
    || String(payload.current_stage || "").toLowerCase() === "truth_and_review_gates";
  if (!atFinalGate) {
    state.finalGatePolls = 0;
    return payload;
  }

  state.finalGatePolls += 1;
  const hasSupportingCompletionEvidence = completionEvidenceReady(payload)
    || (reportReady(payload, tier) && reviewReady(payload, tier));
  if (hasSupportingCompletionEvidence || state.finalGatePolls >= FINAL_GATE_MAX_POLLS) {
    return waitingProjection(payload, state, tier);
  }
  return payload;
}

export default function AssessmentProgressIntegrityGuard() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const states = new Map<string, RunState>();
    const guardedFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const url = requestUrl(input);
      const match = url ? STATUS_PATH.exec(url.pathname) : null;
      if (!match) return response;
      const payload = await responsePayload(response);
      if (!payload) return response;
      const runId = decodeURIComponent(match[1]);
      const state = states.get(runId) || {highestPercent: 0, highestStage: "", finalGatePolls: 0};
      const reconciled = reconcileProgress(state.lastPayload, payload, state);
      const finalized = normalizeFinalGate(reconciled, runId, state);
      state.lastPayload = structuredClone(finalized);
      states.set(runId, state);
      return jsonResponse(response, finalized);
    };
    window.fetch = guardedFetch;
    return () => { if (window.fetch === guardedFetch) window.fetch = previousFetch; };
  }, []);
  return null;
}

export {
  FINAL_GATE_MAX_POLLS,
  FINAL_GATE_MIN_PERCENT,
  completionEvidenceReady,
  normalizeFinalGate,
  reconcileProgress,
  reportReady,
  reviewReady,
  waitingProjection,
};
