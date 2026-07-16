"use client";

import {useEffect} from "react";

const ASSESSMENT_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const STATUS_PATH = /^\/(?:api\/nico\/)?assessment\/(?:express-run|mid-run|full-run)\/([^/?#]+)\/status$/;
const TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);
const ACTIVE_STATUSES = new Set(["queued", "running", "pending", "planned", "starting"]);

const RETAINED_TERMINAL_FIELDS = [
  "repository",
  "customer_id",
  "project_id",
  "assessment_type",
  "service_tier",
  "repository_snapshot",
  "repository_evidence",
  "scanner",
  "scanner_evidence",
  "reports",
  "mid_report",
  "approval_request",
  "approval",
  "persistence",
] as const;

type JsonRecord = Record<string, unknown>;
type ProgressRecord = {step?: unknown; status?: unknown; message?: unknown; evidence?: unknown};

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
    const parsed = await response.clone().json();
    return parsed && typeof parsed === "object" ? parsed as JsonRecord : null;
  } catch {
    return null;
  }
}

function lifecycleIdentity(payload: JsonRecord | null) {
  const detail = record(payload?.detail);
  return {
    runId: String(detail.run_id || payload?.run_id || ""),
    status: String(detail.status || payload?.status || "").toLowerCase(),
    code: String(detail.code || payload?.code || ""),
  };
}

function progressItems(payload: JsonRecord): ProgressRecord[] {
  return Array.isArray(payload.progress)
    ? payload.progress.filter((item): item is ProgressRecord => Boolean(item) && typeof item === "object")
    : [];
}

function jsonResponse(payload: JsonRecord): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

function recoveryResponse(
  runId: string,
  response: Response,
  payload: JsonRecord | null,
  lastGood: JsonRecord | undefined,
): Response {
  const output: JsonRecord = lastGood ? structuredClone(lastGood) : {
    status: "running",
    run_id: runId,
    current_stage: "status_recovery",
    progress_percent: 4,
    progress: [],
    human_review_required: true,
    client_ready: false,
  };
  const identity = lifecycleIdentity(payload);
  const code = identity.code || `http_${response.status}`;
  const message = `Live status returned HTTP ${response.status} (${code}) without exact-run terminal evidence. Exact run ${runId} remains preserved and NICO will continue read-only checks without starting a duplicate assessment.`;
  const items = progressItems(output);
  const activeIndex = items.findIndex((item) => ACTIVE_STATUSES.has(String(item.status || "").toLowerCase()));
  const replacement: ProgressRecord = {
    ...(activeIndex >= 0 ? items[activeIndex] : {}),
    step: activeIndex >= 0 ? items[activeIndex].step : String(output.current_stage || "status_recovery"),
    status: "running",
    message,
  };
  if (activeIndex >= 0) items[activeIndex] = replacement;
  else items.push(replacement);

  output.status = "running";
  output.run_id = String(output.run_id || runId);
  output.progress = items;
  output.human_review_required = true;
  output.client_ready = false;
  output.status_transport = {
    status: "temporarily_unreachable",
    http_status: response.status,
    code,
    exact_run_terminal_evidence: false,
    duplicate_start_allowed: false,
    recovery_required_if_stale: true,
  };
  return jsonResponse(output);
}

function terminalResponse(
  runId: string,
  response: Response,
  payload: JsonRecord,
  lastGood: JsonRecord | undefined,
): Response {
  const detail = record(payload.detail);
  const source = Object.keys(detail).length ? detail : payload;
  const identity = lifecycleIdentity(payload);
  const terminalStatus = TERMINAL_STATUSES.has(identity.status) ? identity.status : "failed";
  const output: JsonRecord = structuredClone(source);

  for (const key of RETAINED_TERMINAL_FIELDS) {
    if (output[key] == null && lastGood?.[key] != null) output[key] = structuredClone(lastGood[key]);
  }

  const code = String(output.code || identity.code || `http_${response.status}`);
  const terminalMessage = String(
    output.message
    || output.error
    || `Exact run ${runId} became ${terminalStatus} before every required stage completed.`,
  );
  const interruptedStatus = terminalStatus === "blocked" || terminalStatus === "rejected" ? "blocked" : "interrupted";
  const retainedProgress = progressItems(output).length
    ? progressItems(output)
    : lastGood
      ? progressItems(lastGood)
      : [];
  const normalizedProgress = retainedProgress.map((item) => {
    const itemStatus = String(item.status || "").toLowerCase();
    if (!ACTIVE_STATUSES.has(itemStatus)) return structuredClone(item);
    return {
      ...structuredClone(item),
      status: interruptedStatus,
      message: `This stage did not complete because the exact run became ${terminalStatus}. ${terminalMessage}`,
    };
  });
  if (!normalizedProgress.some((item) => TERMINAL_STATUSES.has(String(item.status || "").toLowerCase()))) {
    normalizedProgress.push({
      step: String(output.failure_stage || output.current_stage || terminalStatus),
      status: terminalStatus,
      message: terminalMessage,
      evidence: {code, http_status: response.status, exact_run_terminal_evidence: true},
    });
  }

  const scanner = record(output.scanner);
  if (ACTIVE_STATUSES.has(String(scanner.status || "").toLowerCase())) {
    output.scanner = {
      ...scanner,
      status: "interrupted",
      current_stage: "interrupted",
      message: "The scanner's last confirmed state was active when the exact run became terminal.",
    };
  }
  const scannerEvidence = record(output.scanner_evidence);
  if (
    ACTIVE_STATUSES.has(String(scannerEvidence.status || "").toLowerCase())
    || ACTIVE_STATUSES.has(String(scannerEvidence.scanner_status || "").toLowerCase())
  ) {
    output.scanner_evidence = {
      ...scannerEvidence,
      status: "interrupted",
      scanner_status: "interrupted",
    };
  }

  const reports = record(output.reports);
  const reportReady = Boolean(reports.markdown || reports.pdf_base64 || reports.report_id);
  if (!reportReady) {
    output.report_generation_status = terminalStatus === "blocked" || terminalStatus === "rejected" ? "blocked" : "failed";
    output.report_generation_note = terminalMessage;
  }

  output.status = terminalStatus;
  output.run_id = runId;
  output.current_stage = String(output.failure_stage || output.current_stage || terminalStatus);
  output.progress_percent = 100;
  output.progress = normalizedProgress;
  output.human_review_required = true;
  output.client_ready = false;
  output.status_transport = {
    status: "exact_run_terminal",
    http_status: response.status,
    code,
    exact_run_terminal_evidence: true,
    duplicate_start_allowed: false,
    recovery_required: Boolean(output.recovery_required),
  };
  return jsonResponse(output);
}

export default function AssessmentStatusOutcomeGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const lastGoodByRun = new Map<string, JsonRecord>();

    const guardedFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      if (!url || !ASSESSMENT_PATH.test(url.pathname)) return originalFetch(input, init);

      const statusMatch = STATUS_PATH.exec(url.pathname);
      let response: Response;
      try {
        response = await originalFetch(input, init);
      } catch (error) {
        if (!statusMatch) throw error;
        const runId = decodeURIComponent(statusMatch[1]);
        const lastGood = lastGoodByRun.get(runId);
        if (!lastGood) throw error;
        return recoveryResponse(
          runId,
          new Response(null, {status: 503, statusText: "Status transport interrupted"}),
          {code: "browser_transport_interrupted"},
          lastGood,
        );
      }

      const payload = await responsePayload(response);
      if (!statusMatch) {
        if (response.ok && payload) {
          const runId = String(payload.run_id || "");
          if (runId) lastGoodByRun.set(runId, payload);
        }
        return response;
      }

      const runId = decodeURIComponent(statusMatch[1]);
      if (response.ok && payload) {
        lastGoodByRun.set(runId, payload);
        return response;
      }

      const identity = lifecycleIdentity(payload);
      if (payload && identity.runId === runId && TERMINAL_STATUSES.has(identity.status)) {
        return terminalResponse(runId, response, payload, lastGoodByRun.get(runId));
      }

      // By the time this outer outcome guard receives the response, the inner
      // exact-run retry transport has already exhausted its bounded attempts.
      // A non-terminal status outage must remain running rather than forcing the
      // unified page's outer catch block into a false terminal state.
      return recoveryResponse(runId, response, payload, lastGoodByRun.get(runId));
    };

    window.fetch = guardedFetch;
    return () => {
      if (window.fetch === guardedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
