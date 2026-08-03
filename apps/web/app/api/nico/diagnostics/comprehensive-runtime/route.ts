import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 45;

const HEALTH_WARMUP_BUDGET_MS = 28_000;
const HEALTH_REQUEST_TIMEOUT_MS = 8_000;
const HEALTH_RETRY_DELAY_MS = 2_000;
const DIAGNOSTIC_TIMEOUT_MS = 14_000;
const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

type JsonRecord = Record<string, unknown>;

type BackendResolution = {
  backend: URL | null;
  configuredCount: number;
  conflict: boolean;
};

type UpstreamObservation = {
  httpStatus: number | null;
  payload: JsonRecord;
  failureClass: string;
};

type WarmupResult = UpstreamObservation & {
  attempts: number;
  elapsedMs: number;
  healthy: boolean;
};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function configuredBackend(): BackendResolution {
  const candidates = [
    process.env.NICO_API_URL,
    process.env.NICO_BACKEND_URL,
    process.env.NEXT_PUBLIC_NICO_API_URL,
  ];
  const seen = new Map<string, URL>();

  for (const raw of candidates) {
    const configured = String(raw || "").trim();
    if (!configured) continue;
    try {
      const url = new URL(configured.endsWith("/") ? configured : `${configured}/`);
      if (url.username || url.password) continue;
      if (!["http:", "https:"].includes(url.protocol)) continue;
      if (process.env.NODE_ENV === "production" && url.protocol !== "https:") continue;
      seen.set(url.href, url);
    } catch {
      // Invalid deployment values are reported through the bounded response below.
    }
  }

  const values = [...seen.values()];
  return {
    backend: values.length === 1 ? values[0] : null,
    configuredCount: values.length,
    conflict: values.length > 1,
  };
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function boundedHeaders(requestId: string, upstreamRequests: number): HeadersInit {
  return {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "CDN-Cache-Control": "no-store",
    "Vercel-CDN-Cache-Control": "no-store",
    "X-Request-ID": requestId,
    "X-NICO-Readiness-Upstream-Requests": String(upstreamRequests),
  };
}

function blockedReadiness(
  requestId: string,
  reason: string,
  message: string,
  upstreamRequests: number,
  extra: JsonRecord = {},
  transportStatus = 200,
): Response {
  const retryable = TRANSIENT_STATUS.has(transportStatus);
  return Response.json(
    {
      status: "blocked",
      configured: false,
      reason,
      message,
      retryable,
      detail: {
        code: reason,
        message,
        retryable,
        request_id: requestId,
      },
      survives_container_replacement_verified: false,
      persistence: {
        survives_container_replacement_verified: false,
        durability_verified: false,
      },
      preflight_proxy: {
        status: retryable ? "transient_failure" : "bounded_failure",
        upstream_requests: upstreamRequests,
        health_warmup_budget_ms: HEALTH_WARMUP_BUDGET_MS,
        health_request_timeout_ms: HEALTH_REQUEST_TIMEOUT_MS,
        health_retry_delay_ms: HEALTH_RETRY_DELAY_MS,
        diagnostic_timeout_ms: DIAGNOSTIC_TIMEOUT_MS,
        browser_retry_authoritative: retryable,
        ...extra,
      },
      human_review_required: true,
      client_delivery_allowed: false,
    },
    {
      status: transportStatus,
      headers: {
        ...boundedHeaders(requestId, upstreamRequests),
        ...(retryable ? {"Retry-After": "2"} : {}),
      },
    },
  );
}

function upstreamReason(payload: JsonRecord, status: number | null, fallback: string): string {
  const detail = record(payload.detail);
  return String(
    detail.code
      || payload.reason
      || payload.code
      || (status ? `comprehensive_runtime_upstream_${status}` : fallback),
  ).trim();
}

async function observeUpstream(
  url: URL,
  requestId: string,
  timeoutMs: number,
): Promise<UpstreamObservation> {
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        "Cache-Control": "no-cache",
        "X-Request-ID": requestId,
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const payload = record(await response.json().catch(() => null));
    return {
      httpStatus: response.status,
      payload,
      failureClass: Object.keys(payload).length ? "" : `upstream_${response.status}_invalid_json`,
    };
  } catch (error) {
    return {
      httpStatus: null,
      payload: {},
      failureClass: error instanceof DOMException && error.name === "TimeoutError"
        ? "timeout"
        : "network_error",
    };
  }
}

async function warmBackend(backend: URL, requestId: string): Promise<WarmupResult> {
  const startedAt = Date.now();
  const deadline = startedAt + HEALTH_WARMUP_BUDGET_MS;
  let attempts = 0;
  let latest: UpstreamObservation = {
    httpStatus: null,
    payload: {},
    failureClass: "not_attempted",
  };

  while (Date.now() < deadline) {
    attempts += 1;
    const remaining = Math.max(1, deadline - Date.now());
    latest = await observeUpstream(
      new URL("/health", backend),
      requestId,
      Math.min(HEALTH_REQUEST_TIMEOUT_MS, remaining),
    );
    const healthy = (
      latest.httpStatus != null
      && latest.httpStatus >= 200
      && latest.httpStatus < 300
      && String(latest.payload.status || "").toLowerCase() === "ok"
    );
    if (healthy) {
      return {
        ...latest,
        attempts,
        elapsedMs: Date.now() - startedAt,
        healthy: true,
      };
    }
    const delay = Math.min(HEALTH_RETRY_DELAY_MS, Math.max(0, deadline - Date.now()));
    if (delay > 0) await wait(delay);
  }

  return {
    ...latest,
    attempts,
    elapsedMs: Date.now() - startedAt,
    healthy: false,
  };
}

export async function GET(request: NextRequest): Promise<Response> {
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  const resolution = configuredBackend();

  if (resolution.conflict) {
    return blockedReadiness(
      requestId,
      "assessment_backend_configuration_conflict",
      "Multiple assessment backend origins are configured.",
      0,
      {backend_candidate_count: resolution.configuredCount},
    );
  }
  if (!resolution.backend) {
    return blockedReadiness(
      requestId,
      "assessment_backend_not_configured",
      "The assessment backend URL is unavailable or unsafe for this deployment.",
      0,
      {backend_candidate_count: resolution.configuredCount},
    );
  }

  // Railway can return a temporary edge error while a sleeping container imports
  // the production application. Poll only the lightweight health endpoint inside
  // one bounded warm-up budget, then ask the authoritative Comprehensive route.
  // Health can wake the process but can never authorize an assessment.
  const warmup = await warmBackend(resolution.backend, requestId);
  const diagnostic = await observeUpstream(
    new URL("/diagnostics/comprehensive-runtime", resolution.backend),
    requestId,
    DIAGNOSTIC_TIMEOUT_MS,
  );
  const upstreamRequests = warmup.attempts + 1;

  if (
    diagnostic.httpStatus != null
    && diagnostic.httpStatus >= 200
    && diagnostic.httpStatus < 300
    && Object.keys(diagnostic.payload).length
  ) {
    return Response.json(diagnostic.payload, {
      status: 200,
      headers: boundedHeaders(requestId, upstreamRequests),
    });
  }

  const reason = upstreamReason(
    diagnostic.payload,
    diagnostic.httpStatus,
    "assessment_backend_unreachable",
  );
  const transient = diagnostic.httpStatus == null || TRANSIENT_STATUS.has(diagnostic.httpStatus);
  return blockedReadiness(
    requestId,
    reason,
    transient
      ? "The Comprehensive assessment service did not become ready within the bounded warm-up window."
      : "The Comprehensive assessment service is not ready yet.",
    upstreamRequests,
    {
      backend_candidate_count: 1,
      warmup_healthy: warmup.healthy,
      warmup_attempts: warmup.attempts,
      warmup_elapsed_ms: warmup.elapsedMs,
      warmup_http_status: warmup.httpStatus,
      warmup_failure_class: warmup.failureClass,
      diagnostic_http_status: diagnostic.httpStatus,
      diagnostic_failure_class: diagnostic.failureClass,
      health_used_as_readiness_evidence: false,
    },
    transient ? 503 : 200,
  );
}
