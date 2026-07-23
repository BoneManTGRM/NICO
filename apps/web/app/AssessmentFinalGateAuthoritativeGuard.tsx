"use client";

import {useEffect} from "react";

const STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)\/([^/?#]+)\/status$/;
type JsonRecord = Record<string, unknown>;

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

async function payloadFrom(response: Response): Promise<JsonRecord | null> {
  try {
    const value = await response.clone().json();
    return value && typeof value === "object" ? value as JsonRecord : null;
  } catch {
    return null;
  }
}

function responseFrom(original: Response, payload: JsonRecord): Response {
  const headers = new Headers(original.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Cache-Control", "no-store");
  return new Response(JSON.stringify(payload), {status: 200, statusText: "OK", headers});
}

function progressItems(payload: JsonRecord): JsonRecord[] {
  return Array.isArray(payload.progress)
    ? payload.progress.filter((item) => item && typeof item === "object") as JsonRecord[]
    : [];
}

function usableReportArtifacts(payload: JsonRecord): boolean {
  const reports = record(payload.reports);
  const markdown = String(reports.markdown || "").trim();
  const html = String(reports.html || "").trim();
  const pdf = String(reports.pdf_base64 || "").trim();
  return Boolean(markdown && html && pdf);
}

function reportGenerationComplete(payload: JsonRecord): boolean {
  return usableReportArtifacts(payload);
}

function browserGeneratedStall(payload: JsonRecord): boolean {
  const transport = record(payload.status_transport);
  if (String(transport.code || "").toLowerCase() === "assessment_final_gate_stalled") return true;
  return progressItems(payload).some((item) =>
    String(record(item.evidence).code || "").toLowerCase() === "assessment_final_gate_stalled"
  );
}

function repairFalseFinalGateBlock(payload: JsonRecord): JsonRecord {
  if (!browserGeneratedStall(payload)) return payload;

  // A browser-generated timeout is not backend terminal evidence. Remove the false
  // blocked projection, retain any completed report artifacts, and continue polling
  // the exact run in a fail-closed nonterminal state.
  const output = structuredClone(payload);
  const reportReady = usableReportArtifacts(output);
  output.status = "running";
  output.current_stage = "truth_and_review_gates";
  output.progress_percent = Math.max(94, Math.min(99, Number(output.progress_percent) || 94));
  output.report_generation_status = reportReady ? "complete" : String(output.report_generation_status || "running");
  output.recovery_required = false;
  output.duplicate_start_allowed = false;
  output.human_review_required = true;
  output.client_ready = false;
  output.client_delivery_allowed = false;
  output.delivery_status = "blocked_pending_backend_completion_and_human_review";
  output.status_transport = {
    ...record(output.status_transport),
    status: "browser_false_stall_removed_waiting_for_backend",
    code: "browser_final_gate_false_block_removed",
    report_ready: reportReady,
    exact_run_terminal_evidence: false,
    terminal_state_written: false,
    browser_projection_only: true,
    browser_terminalization_forbidden: true,
    duplicate_start_allowed: false,
    recovery_required: false,
  };

  const cleaned = progressItems(output).filter((item) => {
    const code = String(record(item.evidence).code || "").toLowerCase();
    return code !== "assessment_final_gate_stalled";
  });
  const gateIndex = cleaned.findIndex((item) => String(item.step || "").toLowerCase() === "truth_and_review_gates");
  const gateStep = {
    ...(gateIndex >= 0 ? cleaned[gateIndex] : {}),
    step: "truth_and_review_gates",
    status: "running",
    message: reportReady
      ? "Markdown, HTML, and PDF artifacts are available. Waiting for the backend to persist the exact run's terminal completion state."
      : "Waiting for the backend to persist final report and terminal completion evidence for this exact run.",
    evidence: {
      ...record(gateIndex >= 0 ? cleaned[gateIndex].evidence : {}),
      report_generation_complete: reportReady,
      usable_report_artifacts: reportReady,
      required_formats: ["markdown", "html", "pdf"],
      human_review_required: true,
      client_delivery_allowed: false,
      exact_run_terminal_evidence: false,
      browser_terminalization_forbidden: true,
    },
  };
  if (gateIndex >= 0) cleaned[gateIndex] = gateStep;
  else cleaned.push(gateStep);
  output.progress = cleaned;
  return output;
}

export default function AssessmentFinalGateAuthoritativeGuard() {
  useEffect(() => {
    const previousFetch = window.fetch.bind(window);
    const guardedFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      const url = requestUrl(input);
      if (!url || !STATUS_PATH.test(url.pathname)) return response;
      const payload = await payloadFrom(response);
      if (!payload) return response;
      const repaired = repairFalseFinalGateBlock(payload);
      return repaired === payload ? response : responseFrom(response, repaired);
    };
    window.fetch = guardedFetch;
    return () => { if (window.fetch === guardedFetch) window.fetch = previousFetch; };
  }, []);
  return null;
}

export {browserGeneratedStall, reportGenerationComplete, repairFalseFinalGateBlock, usableReportArtifacts};
