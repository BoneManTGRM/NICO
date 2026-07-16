"use client";

import {useEffect} from "react";

const CONFIGURED_API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const ASSESSMENT_PATH = /^\/assessment\/(?:github|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const LEGACY_EXPRESS_PATH = "/assessment/github";
const EXPRESS_START_PATH = "/assessment/express-run";
const EXPRESS_POLL_INTERVAL_MS = 3000;
const EXPRESS_MAX_POLL_ATTEMPTS = 240;
const EXPRESS_STATUS_MAX_CONSECUTIVE_TRANSPORT_FAILURES = 8;
const EXPRESS_STATUS_RETRY_BASE_MS = 1500;
const EXPRESS_STATUS_RETRY_MAX_MS = 12000;
const RETRYABLE_STATUS_HTTP_CODES = new Set([408, 422, 425, 429, 500, 502, 503, 504]);
const TERMINAL_EXPRESS_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);

export const ASSESSMENT_FAILURE_EVENT = "nico:assessment-request-failed";

export type AssessmentFailureEvidence = {
  http_status: number;
  route: string;
  status: string;
  code: string;
  message: string;
  run_id: string;
  assessment_type: string;
  progress: Array<{step: string; status: string; message: string}>;
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function boundedText(value: unknown, limit = 320): string {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 3)}...`;
}

function boundedProgress(value: unknown): AssessmentFailureEvidence["progress"] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 16).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    return [{
      step: boundedText(record.step, 80) || "unknown_step",
      status: boundedText(record.status, 40) || "unknown",
      message: boundedText(record.message, 240) || "No bounded failure message was returned.",
    }];
  });
}

function payloadDetail(payload: Record<string, unknown>): Record<string, unknown> {
  return payload.detail && typeof payload.detail === "object"
    ? payload.detail as Record<string, unknown>
    : payload;
}

async function publishFailure(response: Response, route: string) {
  let payload: Record<string, unknown> = {};
  try {
    const parsed = await response.json();
    if (parsed && typeof parsed === "object") payload = parsed as Record<string, unknown>;
  } catch {
    // The HTTP status and route still provide bounded diagnostic evidence.
  }

  const detail = payloadDetail(payload);
  const evidence: AssessmentFailureEvidence = {
    http_status: response.status,
    route,
    status: boundedText(detail.status || payload.status, 40) || "error",
    code: boundedText(detail.code || payload.code, 80) || `http_${response.status}`,
    message: boundedText(detail.message || payload.message || payload.error, 320)
      || `Assessment request failed with HTTP ${response.status}.`,
    run_id: boundedText(detail.run_id || payload.run_id, 120),
    assessment_type: boundedText(detail.assessment_type || payload.assessment_type, 40),
    progress: boundedProgress(detail.progress || payload.progress),
  };

  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: evidence}));
}

function clearFailure() {
  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: null}));
}

function jsonFailure(status: number, code: string, message: string, runId = "") {
  return new Response(JSON.stringify({
    status: "error",
    detail: {
      status: "error",
      code,
      message,
      run_id: runId,
      assessment_type: "express",
    },
  }), {
    status,
    headers: {"Content-Type": "application/json", "Cache-Control": "no-store"},
  });
}

async function responsePayload(response: Response): Promise<Record<string, unknown>> {
  try {
    const payload = await response.clone().json();
    return payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

function proxyUrl(path: string) {
  return new URL(`/api/nico${path}`, window.location.origin);
}

function statusRetryDelayMs(consecutiveFailures: number) {
  return Math.min(
    EXPRESS_STATUS_RETRY_BASE_MS * (2 ** Math.max(0, consecutiveFailures - 1)),
    EXPRESS_STATUS_RETRY_MAX_MS,
  );
}

function retryableStatusResponse(
  response: Response,
  payload: Record<string, unknown>,
  exactRunId: string,
) {
  if (!RETRYABLE_STATUS_HTTP_CODES.has(response.status)) return false;
  const detail = payloadDetail(payload);
  const lifecycleStatus = boundedText(detail.status || payload.status, 40).toLowerCase();
  const responseRunId = boundedText(detail.run_id || payload.run_id, 120);

  // A terminal response tied to this exact run is evidence, not a transport outage.
  if (responseRunId === exactRunId && TERMINAL_EXPRESS_STATUSES.has(lifecycleStatus)) return false;

  const code = boundedText(detail.code || payload.code, 80);
  if (["assessment_backend_not_configured", "assessment_proxy_route_not_allowed"].includes(code)) return false;
  return true;
}

function exhaustedStatusFailure(runId: string, lastCode = "") {
  const suffix = lastCode ? ` Last bounded transport code: ${lastCode}.` : "";
  return jsonFailure(
    503,
    "express_status_temporarily_unreachable",
    `The Express run remains accepted under the same exact run ID, but ${EXPRESS_STATUS_MAX_CONSECUTIVE_TRANSPORT_FAILURES} consecutive short status requests could not complete.${suffix} Review Recovery before starting another run.`,
    runId,
  );
}

async function startExpressLifecycle(
  originalFetch: typeof window.fetch,
  input: RequestInfo | URL,
  init: RequestInit | undefined,
): Promise<Response> {
  let startResponse: Response;
  try {
    const target = proxyUrl(EXPRESS_START_PATH);
    startResponse = input instanceof Request
      ? await originalFetch(new Request(target, input), init)
      : await originalFetch(target, init);
  } catch {
    const failure = jsonFailure(
      502,
      "express_start_transport_failed",
      "NICO could not start the Express lifecycle through the frontend deployment. Review Vercel-to-Railway connectivity before retrying.",
    );
    await publishFailure(failure.clone(), EXPRESS_START_PATH);
    return failure;
  }

  if (!startResponse.ok) {
    await publishFailure(startResponse.clone(), EXPRESS_START_PATH);
    return startResponse;
  }

  const started = await responsePayload(startResponse);
  const runId = boundedText(started.run_id, 120);
  const customerId = boundedText(started.customer_id, 120);
  const projectId = boundedText(started.project_id, 120);
  if (!runId.startsWith("express_run_") || !customerId || !projectId) {
    const failure = jsonFailure(
      502,
      "express_start_missing_identity",
      "The Express lifecycle start response did not include its exact run and tenant identity, so NICO stopped rather than risk a duplicate or cross-scope run.",
      runId,
    );
    await publishFailure(failure.clone(), EXPRESS_START_PATH);
    return failure;
  }

  let consecutiveStatusTransportFailures = 0;
  for (let attempt = 1; attempt <= EXPRESS_MAX_POLL_ATTEMPTS; attempt += 1) {
    await sleep(EXPRESS_POLL_INTERVAL_MS);
    const statusPath = `/assessment/express-run/${encodeURIComponent(runId)}/status`;
    let statusResponse: Response;
    try {
      statusResponse = await originalFetch(proxyUrl(statusPath), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({customer_id: customerId, project_id: projectId}),
        cache: "no-store",
        credentials: "same-origin",
        keepalive: true,
      });
    } catch {
      consecutiveStatusTransportFailures += 1;
      if (consecutiveStatusTransportFailures < EXPRESS_STATUS_MAX_CONSECUTIVE_TRANSPORT_FAILURES) {
        await sleep(statusRetryDelayMs(consecutiveStatusTransportFailures));
        continue;
      }
      const failure = exhaustedStatusFailure(runId, "browser_transport_interrupted");
      await publishFailure(failure.clone(), statusPath);
      return failure;
    }

    if (!statusResponse.ok) {
      const payload = await responsePayload(statusResponse);
      if (retryableStatusResponse(statusResponse, payload, runId)) {
        consecutiveStatusTransportFailures += 1;
        if (consecutiveStatusTransportFailures < EXPRESS_STATUS_MAX_CONSECUTIVE_TRANSPORT_FAILURES) {
          await sleep(statusRetryDelayMs(consecutiveStatusTransportFailures));
          continue;
        }
        const detail = payloadDetail(payload);
        const failure = exhaustedStatusFailure(
          runId,
          boundedText(detail.code || payload.code, 80) || `http_${statusResponse.status}`,
        );
        await publishFailure(failure.clone(), statusPath);
        return failure;
      }
      await publishFailure(statusResponse.clone(), statusPath);
      return statusResponse;
    }

    consecutiveStatusTransportFailures = 0;
    const payload = await responsePayload(statusResponse);
    const status = boundedText(payload.status, 40).toLowerCase();
    if (["complete", "completed"].includes(status)) return statusResponse;
    if (TERMINAL_EXPRESS_STATUSES.has(status)) {
      const failure = jsonFailure(
        503,
        boundedText(payload.code, 80) || "express_terminal_failure",
        boundedText(payload.message, 320) || "The Express run stopped before completion.",
        runId,
      );
      await publishFailure(failure.clone(), statusPath);
      return failure;
    }
  }

  const timeout = jsonFailure(
    504,
    "express_status_poll_limit_reached",
    `Express continuation reached its bounded ${EXPRESS_MAX_POLL_ATTEMPTS}-check limit. The exact run ID is preserved; review Recovery before starting another run.`,
    runId,
  );
  await publishFailure(timeout.clone(), `/assessment/express-run/${encodeURIComponent(runId)}/status`);
  return timeout;
}

export default function AssessmentApiTransportBridge() {
  useEffect(() => {
    if (!CONFIGURED_API_URL) return;

    let configured: URL;
    try {
      configured = new URL(CONFIGURED_API_URL);
    } catch {
      return;
    }

    const configuredPath = configured.pathname.replace(/\/$/, "");
    const originalFetch = window.fetch.bind(window);

    const bridgedFetch: typeof window.fetch = async (input, init) => {
      let requested: URL;
      try {
        requested = new URL(requestUrl(input), window.location.href);
      } catch {
        return originalFetch(input, init);
      }

      if (requested.origin !== configured.origin) return originalFetch(input, init);
      if (configuredPath && !requested.pathname.startsWith(`${configuredPath}/`)) return originalFetch(input, init);

      const apiPath = configuredPath ? requested.pathname.slice(configuredPath.length) : requested.pathname;
      if (!ASSESSMENT_PATH.test(apiPath)) return originalFetch(input, init);

      clearFailure();
      if (apiPath === LEGACY_EXPRESS_PATH) return startExpressLifecycle(originalFetch, input, init);

      const target = new URL(`/api/nico${apiPath}${requested.search}`, window.location.origin);
      const response = input instanceof Request
        ? await originalFetch(new Request(target, input), init)
        : await originalFetch(target, init);
      if (!response.ok) await publishFailure(response.clone(), apiPath);
      return response;
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
