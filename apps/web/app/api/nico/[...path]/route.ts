import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const EXPRESS_START = "/assessment/express-run";
const EXPRESS_STATUS = /^\/assessment\/express-run\/[^/?#]+\/status$/;
const COMPREHENSIVE_INTAKE = "/assessment/comprehensive-intake";
const COMPREHENSIVE_STATUS = /^\/assessment\/comprehensive-run\/[^/?#]+$/;
const COMPREHENSIVE_CONTINUE = /^\/assessment\/comprehensive-run\/[^/?#]+\/continue$/;
const COMPREHENSIVE_REVIEW_QUEUE = /^\/assessment\/comprehensive-run\/[^/?#]+\/review-queue$/;
const COMPREHENSIVE_REVIEW_WORK = /^\/assessment\/comprehensive-run\/[^/?#]+\/review-work$/;
const COMPREHENSIVE_REVIEW = /^\/assessment\/comprehensive-run\/[^/?#]+\/review$/;
const COMPREHENSIVE_APPROVED_DELIVERY = /^\/assessment\/comprehensive-run\/[^/?#]+\/approved-delivery-package$/;
const COMPREHENSIVE_REPORT_ARTIFACT = /^\/assessment\/comprehensive-run\/[^/?#]+\/report\/(?:markdown|html|json|pdf)$/;
const ALLOWED_DIAGNOSTIC_PATH = /^\/diagnostics\/(?:express-runtime|comprehensive-runtime)$/;
const BROWSER_PROJECTION_HEADER = "x-nico-browser-projection";
const BROWSER_PROJECTION_VALUE = "terminal-manifest-v1";
const TRANSIENT_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);
const RETRY_DELAYS_MS = [0, 1_500, 4_000];
const SINGLE_ATTEMPT_DELAYS_MS = [0];
const ARTIFACT_RETRY_DELAYS_MS = [0];
const SHORT_READ_TIMEOUT_MS = 20_000;
const CONTINUATION_WRITE_TIMEOUT_MS = 80_000;
const ARTIFACT_READ_TIMEOUT_MS = 240_000;
const WRITE_TIMEOUT_MS = 240_000;

type BackendResolution = {
  backend: URL | null;
  configuredCount: number;
  conflict: boolean;
};

function jsonError(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
  return Response.json(
    {status: "error", detail: {code, message, ...extra}},
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        ...(TRANSIENT_STATUS.has(status) ? {"Retry-After": "5"} : {}),
      },
    },
  );
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
      // Invalid deployment values are ignored and reported through the bounded error below.
    }
  }

  const values = [...seen.values()];
  return {
    backend: values.length === 1 ? values[0] : null,
    configuredCount: values.length,
    conflict: values.length > 1,
  };
}

function assessmentRouteAllowed(method: string, path: string): boolean {
  if (method === "POST" && (path === EXPRESS_START || EXPRESS_STATUS.test(path))) return true;
  if (method === "POST" && path === COMPREHENSIVE_INTAKE) return true;
  if (method === "GET" && COMPREHENSIVE_STATUS.test(path)) return true;
  if (method === "POST" && COMPREHENSIVE_CONTINUE.test(path)) return true;
  if (method === "GET" && COMPREHENSIVE_REVIEW_QUEUE.test(path)) return true;
  if ((method === "GET" || method === "POST") && COMPREHENSIVE_REVIEW_WORK.test(path)) return true;
  if (method === "POST" && COMPREHENSIVE_REVIEW.test(path)) return true;
  if (method === "GET" && COMPREHENSIVE_APPROVED_DELIVERY.test(path)) return true;
  if (method === "GET" && COMPREHENSIVE_REPORT_ARTIFACT.test(path)) return true;
  return false;
}

function protectedReviewRoute(method: string, path: string): boolean {
  return (method === "GET" && COMPREHENSIVE_REVIEW_QUEUE.test(path))
    || ((method === "GET" || method === "POST") && COMPREHENSIVE_REVIEW_WORK.test(path))
    || (method === "POST" && COMPREHENSIVE_REVIEW.test(path))
    || (method === "GET" && COMPREHENSIVE_APPROVED_DELIVERY.test(path));
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function upstreamReadPolicy(method: string, path: string): {timeoutMs: number; retryDelaysMs: number[]; readClass: string} {
  const artifactRead = method === "GET" && COMPREHENSIVE_REPORT_ARTIFACT.test(path);
  if (artifactRead) {
    return {
      timeoutMs: ARTIFACT_READ_TIMEOUT_MS,
      retryDelaysMs: ARTIFACT_RETRY_DELAYS_MS,
      readClass: "exact-run-artifact",
    };
  }
  const continuationWrite = method === "POST" && COMPREHENSIVE_CONTINUE.test(path);
  if (continuationWrite) {
    return {
      timeoutMs: CONTINUATION_WRITE_TIMEOUT_MS,
      retryDelaysMs: SINGLE_ATTEMPT_DELAYS_MS,
      readClass: "single-attempt-continuation",
    };
  }
  const shortRead = method === "GET" || ALLOWED_DIAGNOSTIC_PATH.test(path);
  return {
    timeoutMs: shortRead ? SHORT_READ_TIMEOUT_MS : WRITE_TIMEOUT_MS,
    retryDelaysMs: RETRY_DELAYS_MS,
    readClass: shortRead ? "short-status" : "bounded-write",
  };
}

async function proxyNico(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return jsonError(404, "nico_proxy_route_not_allowed", "The requested NICO route is not available through this proxy.");
  }

  const apiPath = `/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  const assessmentAllowed = assessmentRouteAllowed(request.method, apiPath);
  const diagnosticAllowed = request.method === "GET" && ALLOWED_DIAGNOSTIC_PATH.test(apiPath);
  if (!assessmentAllowed && !diagnosticAllowed) {
    return jsonError(404, "nico_proxy_route_not_allowed", "Only native assessment lifecycle routes, exact-run report artifacts, and bounded runtime diagnostics are available through this proxy. Authorized NICO Comprehensive review and delivery are limited to their exact protected routes.");
  }

  const resolution = configuredBackend();
  if (resolution.conflict) {
    return jsonError(
      503,
      "assessment_backend_configuration_conflict",
      "Multiple different assessment backend origins are configured. A run cannot safely fail over between independent stores; configure all NICO backend variables to the same canonical origin.",
      {backend_candidate_count: resolution.configuredCount, retryable: false},
    );
  }
  const backend = resolution.backend;
  if (!backend) {
    return jsonError(503, "assessment_backend_not_configured", "The assessment backend URL is unavailable or unsafe for this deployment.");
  }

  const headers = new Headers({Accept: request.headers.get("accept") || "application/json"});
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const browserProjection = request.headers.get(BROWSER_PROJECTION_HEADER)?.trim().toLowerCase();
  if (browserProjection === BROWSER_PROJECTION_VALUE) {
    headers.set("X-NICO-Browser-Projection", BROWSER_PROJECTION_VALUE);
  }
  if (protectedReviewRoute(request.method, apiPath)) {
    const adminToken = request.headers.get("x-nico-admin-token");
    if (adminToken) headers.set("X-NICO-Admin-Token", adminToken);
  }
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  headers.set("X-Request-ID", requestId);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  const policy = upstreamReadPolicy(request.method, apiPath);
  const upstream = new URL(`${apiPath}${request.nextUrl.search}`, backend);
  let lastStatus: number | null = null;
  let lastFailure = "network_error";

  for (let attempt = 0; attempt < policy.retryDelaysMs.length; attempt += 1) {
    const delay = policy.retryDelaysMs[attempt];
    if (delay) await wait(delay);
    try {
      const response = await fetch(upstream, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(policy.timeoutMs),
      });
      lastStatus = response.status;
      if (TRANSIENT_STATUS.has(response.status) && attempt < policy.retryDelaysMs.length - 1) {
        await response.arrayBuffer();
        lastFailure = `upstream_${response.status}`;
        continue;
      }

      const responseHeaders = new Headers({
        "Cache-Control": "no-store",
        "X-NICO-Proxy-Attempts": String(attempt + 1),
        "X-NICO-Proxy-Read-Class": policy.readClass,
        "X-NICO-Backend-Candidate-Count": "1",
        "X-Request-ID": requestId,
      });
      for (const name of [
        "content-type",
        "content-length",
        "content-disposition",
        "retry-after",
        "x-nico-run-id",
        "x-nico-report-id",
        "x-nico-artifact-sha256",
        "x-nico-canonical-truth-sha256",
        "x-nico-human-review-required",
        "x-nico-client-delivery-allowed",
        "x-nico-delivery-package-sha256",
        "x-nico-accepted-edition-sha256",
        "x-nico-delivery-certificate-sha256",
      ]) {
        const value = response.headers.get(name);
        if (value) responseHeaders.set(name, value);
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (error) {
      lastFailure = error instanceof DOMException && error.name === "TimeoutError" ? "timeout" : "network_error";
      if (attempt >= policy.retryDelaysMs.length - 1) break;
    }
  }

  const continuationFailure = policy.readClass === "single-attempt-continuation";
  const timeoutFailure = lastFailure === "timeout";
  return jsonError(
    timeoutFailure ? 504 : 502,
    continuationFailure && timeoutFailure
      ? "assessment_run_continue_timeout"
      : "assessment_backend_unreachable",
    continuationFailure
      ? "The Comprehensive continuation request did not complete within its bounded single-attempt transport window. Recover the exact run status before attempting any further stage advancement."
      : "The canonical assessment backend could not be reached after bounded cold-start retries.",
    {
      request_id: requestId,
      attempts: policy.retryDelaysMs.length,
      request_class: policy.readClass,
      timeout_ms: policy.timeoutMs,
      backend_candidate_count: 1,
      last_upstream_status: lastStatus,
      failure_class: lastFailure,
      retryable: true,
    },
  );
}

export const GET = proxyNico;
export const POST = proxyNico;
