import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 20;

const UPSTREAM_TIMEOUT_MS = 12_000;
const RETRY_DELAYS_MS = [0];
const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

type JsonRecord = Record<string, unknown>;

type BackendResolution = {
  backend: URL | null;
  configuredCount: number;
  conflict: boolean;
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

function boundedHeaders(requestId: string, attempts: number): HeadersInit {
  return {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "CDN-Cache-Control": "no-store",
    "Vercel-CDN-Cache-Control": "no-store",
    "X-Request-ID": requestId,
    "X-NICO-Readiness-Proxy-Attempts": String(attempts),
  };
}

function blockedReadiness(
  requestId: string,
  reason: string,
  message: string,
  attempts: number,
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
        attempts,
        timeout_ms: UPSTREAM_TIMEOUT_MS,
        browser_retry_authoritative: retryable,
        ...extra,
      },
      human_review_required: true,
      client_delivery_allowed: false,
    },
    {
      status: transportStatus,
      headers: {
        ...boundedHeaders(requestId, attempts),
        ...(retryable ? {"Retry-After": "2"} : {}),
      },
    },
  );
}

function upstreamReason(payload: JsonRecord, status: number): string {
  const detail = record(payload.detail);
  return String(
    detail.code
      || payload.reason
      || payload.code
      || `comprehensive_runtime_upstream_${status}`,
  ).trim();
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

  const upstream = new URL("/diagnostics/comprehensive-runtime", resolution.backend);
  let lastStatus: number | null = null;
  let lastFailure = "network_error";

  for (let attempt = 0; attempt < RETRY_DELAYS_MS.length; attempt += 1) {
    const delay = RETRY_DELAYS_MS[attempt];
    if (delay) await wait(delay);
    try {
      const response = await fetch(upstream, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "Cache-Control": "no-cache",
          "X-Request-ID": requestId,
        },
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
      lastStatus = response.status;
      const payload = record(await response.json().catch(() => null));

      if (response.ok && Object.keys(payload).length) {
        return Response.json(payload, {
          status: 200,
          headers: boundedHeaders(requestId, attempt + 1),
        });
      }

      lastFailure = Object.keys(payload).length
        ? upstreamReason(payload, response.status)
        : `upstream_${response.status}_invalid_json`;
      if (TRANSIENT_STATUS.has(response.status)) {
        return blockedReadiness(
          requestId,
          lastFailure,
          "The Comprehensive assessment service is temporarily busy and will be checked again.",
          attempt + 1,
          {last_upstream_status: response.status},
          503,
        );
      }
      return blockedReadiness(
        requestId,
        lastFailure,
        "The Comprehensive assessment service is not ready yet.",
        attempt + 1,
        {last_upstream_status: response.status},
      );
    } catch (error) {
      lastFailure = error instanceof DOMException && error.name === "TimeoutError"
        ? "timeout"
        : "network_error";
      if (attempt < RETRY_DELAYS_MS.length - 1) continue;
    }
  }

  return blockedReadiness(
    requestId,
    "assessment_backend_unreachable",
    "The Comprehensive assessment backend did not answer within the bounded readiness window.",
    RETRY_DELAYS_MS.length,
    {
      last_upstream_status: lastStatus,
      failure_class: lastFailure,
      backend_candidate_count: 1,
    },
    503,
  );
}
