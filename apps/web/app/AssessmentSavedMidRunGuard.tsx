"use client";

import {useEffect} from "react";

const MID_ACTIVE_RUN_KEY = "nico.mid.active_run";
const MID_LAST_TERMINAL_RUN_KEY = "nico.mid.last_terminal_run";
const MID_START_PATH = /^\/(?:api\/nico\/)?assessment\/mid-run$/;
const FAILURE_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);

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

function requestBody(init?: RequestInit): JsonRecord {
  if (typeof init?.body !== "string") return {};
  try {
    const value = JSON.parse(init.body);
    return value && typeof value === "object" ? value as JsonRecord : {};
  } catch {
    return {};
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

function lifecycleIdentity(payload: JsonRecord | null) {
  const detail = record(payload?.detail);
  return {
    runId: String(detail.run_id || payload?.run_id || ""),
    status: String(detail.status || payload?.status || "").toLowerCase(),
  };
}

function finalMidArtifactsReady(payload: JsonRecord | null): boolean {
  if (!payload) return false;
  const detail = record(payload.detail);
  const source = Object.keys(detail).length ? detail : payload;
  const status = String(source.status || "").toLowerCase();
  const reportStatus = String(source.report_generation_status || "").toLowerCase();
  const approval = record(source.approval_request);
  return ["complete", "completed"].includes(status)
    && reportStatus === "complete"
    && Boolean(approval.approval_id);
}

function clearSavedRun(runId: string) {
  try {
    if (window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) === runId) {
      window.sessionStorage.removeItem(MID_ACTIVE_RUN_KEY);
    }
  } catch {
    // The backend response remains authoritative when browser storage is unavailable.
  }
}

function rememberTerminalRun(runId: string, payload: JsonRecord | null) {
  try {
    const identity = lifecycleIdentity(payload);
    window.sessionStorage.setItem(MID_LAST_TERMINAL_RUN_KEY, JSON.stringify({
      run_id: runId,
      status: identity.status || "terminal",
      recorded_at: new Date().toISOString(),
    }));
  } catch {
    // The durable backend record remains the source of truth.
  }
}

function canonicalStatusBody(body: JsonRecord): JsonRecord {
  return {
    repository: String(body.repository || ""),
    customer_id: String(body.customer_id || "default_customer"),
    project_id: String(body.project_id || "default_project"),
    authorization_confirmed: true,
    authorized: true,
    auto_continue: true,
  };
}

function safeUnavailableResponse(runId: string, body: JsonRecord): Response {
  return new Response(JSON.stringify({
    status: "running",
    run_id: runId,
    repository: body.repository || "",
    customer_id: body.customer_id || "default_customer",
    project_id: body.project_id || "default_project",
    assessment_type: "mid",
    service_tier: "mid",
    current_stage: "status_recovery",
    progress_percent: 18,
    progress: [{
      step: "status_recovery",
      status: "running",
      message: `Saved Mid run ${runId} could not be reached. NICO preserved the exact run and did not create a duplicate assessment. Review Recovery if the run becomes stale.`,
    }],
    status_transport: {
      status: "temporarily_unreachable",
      recovery_required_if_stale: true,
      duplicate_start_allowed: false,
    },
    human_review_required: true,
    client_ready: false,
  }), {
    status: 200,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

export default function AssessmentSavedMidRunGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    const guardedFetch: typeof window.fetch = async (input, init) => {
      const url = requestUrl(input);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      if (!url || method !== "POST" || !MID_START_PATH.test(url.pathname)) {
        return originalFetch(input, init);
      }

      let savedRunId = "";
      try {
        savedRunId = window.sessionStorage.getItem(MID_ACTIVE_RUN_KEY) || "";
      } catch {
        savedRunId = "";
      }
      if (!savedRunId.startsWith("midrun_")) return originalFetch(input, init);

      const body = requestBody(init);
      const prefix = url.pathname.startsWith("/api/nico/") ? "/api/nico" : "";
      const liveUrl = new URL(`${prefix}/assessment/mid-run/${encodeURIComponent(savedRunId)}/live-status`, url.origin);
      liveUrl.searchParams.set("customer_id", String(body.customer_id || "default_customer"));
      liveUrl.searchParams.set("project_id", String(body.project_id || "default_project"));
      try {
        const liveResponse = await originalFetch(liveUrl, {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          signal: AbortSignal.timeout(12_000),
        });
        const payload = await responsePayload(liveResponse);
        const identity = lifecycleIdentity(payload);
        const exactTerminalFailure = identity.runId === savedRunId && FAILURE_STATUSES.has(identity.status);
        const exactTerminalSuccess = identity.runId === savedRunId && finalMidArtifactsReady(payload);

        if (exactTerminalFailure || exactTerminalSuccess) {
          rememberTerminalRun(savedRunId, payload);
          clearSavedRun(savedRunId);
          return originalFetch(input, init);
        }

        if (liveResponse.ok && payload?.continuation_required === true) {
          const canonicalUrl = new URL(`${prefix}/assessment/mid-run/${encodeURIComponent(savedRunId)}/status`, url.origin);
          return originalFetch(canonicalUrl, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(canonicalStatusBody(body)),
            cache: "no-store",
            credentials: "same-origin",
          });
        }

        if (liveResponse.ok && payload) return liveResponse;
        if (liveResponse.status === 404) {
          clearSavedRun(savedRunId);
          return originalFetch(input, init);
        }
        return safeUnavailableResponse(savedRunId, body);
      } catch {
        return safeUnavailableResponse(savedRunId, body);
      }
    };

    window.fetch = guardedFetch;
    return () => {
      if (window.fetch === guardedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
