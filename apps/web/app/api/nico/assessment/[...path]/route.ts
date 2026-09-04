import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const SESSION_COOKIE = "nico-specialist-session";
const STATUS_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+$/;
const CONTINUE_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/continue$/;
const ARTIFACT_PATH = /^\/assessment\/comprehensive-run\/[^/?#]+\/(?:report\/(?:markdown|html|json|pdf)|localized-report\/(?:en|es-MX)(?:\/pdf)?|approved-delivery-package)$/;
const ALLOWED_PATH = /^\/assessment\/(?:comprehensive-intake|comprehensive-run(?:\/[^/?#]+(?:\/(?:continue|review-queue|review-work|review|authorize-delivery|approved-delivery-package|automated-delivery-package|report\/(?:markdown|html|json|pdf)|localized-report\/(?:en|es-MX)(?:\/pdf)?))?)?)$/;
const RESPONSE_HEADERS = [
  "content-type", "content-length", "content-disposition", "retry-after",
  "x-nico-run-id", "x-nico-commit-sha", "x-nico-report-id",
  "x-nico-report-language", "x-nico-assessment-rerun", "x-nico-pdf-sha256",
  "x-nico-artifact-sha256", "x-nico-accepted-pdf-sha256",
  "x-nico-accepted-edition-language", "x-nico-accepted-edition-manifest-sha256",
  "x-nico-canonical-truth-sha256", "x-nico-human-review-required",
  "x-nico-approval-status", "x-nico-delivery-status",
  "x-nico-client-delivery-allowed", "x-nico-localized-artifact-requires-new-approval",
  "x-nico-localized-artifact-approval-invalidated", "x-nico-artifact-finality",
  "x-nico-frozen-source-artifact", "x-nico-delivery-package-sha256",
  "x-nico-certified-package-sha256", "x-nico-authorization-mode",
  "x-nico-human-reviewed", "x-nico-accepted-edition-sha256",
  "x-nico-delivery-certificate-sha256",
] as const;

function errorResponse(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
  return Response.json(
    {status: "blocked", detail: {code, message, ...extra}},
    {status, headers: {"Cache-Control": "no-store, private, max-age=0"}},
  );
}

function backendOrigin(): URL | null {
  const configured = [
    process.env.NICO_API_URL,
    process.env.NICO_BACKEND_URL,
    process.env.NEXT_PUBLIC_NICO_API_URL,
  ].map((value) => String(value || "").trim()).filter(Boolean);
  const origins = new Map<string, URL>();
  for (const value of configured) {
    try {
      const url = new URL(value.endsWith("/") ? value : `${value}/`);
      if (url.username || url.password || !["http:", "https:"].includes(url.protocol)) continue;
      if (process.env.NODE_ENV === "production" && url.protocol !== "https:") continue;
      origins.set(url.href, url);
    } catch {
      // Invalid origins are rejected through the bounded configuration response.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

function timeoutFor(method: string, path: string): number {
  if (method === "GET" && ARTIFACT_PATH.test(path)) return 240_000;
  if (method === "GET" && STATUS_PATH.test(path)) return 60_000;
  if (method === "POST" && CONTINUE_PATH.test(path)) return 240_000;
  return method === "GET" ? 30_000 : 240_000;
}

async function proxyAssessment(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return errorResponse(404, "nico_assessment_route_not_allowed", "The requested assessment route is unavailable.");
  }
  const path = `/assessment/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  if (!ALLOWED_PATH.test(path)) {
    return errorResponse(404, "nico_assessment_route_not_allowed", "Only bounded NICO Comprehensive lifecycle routes are available.");
  }

  const session = request.cookies.get(SESSION_COOKIE)?.value?.trim() || "";
  const rawOperatorToken = request.headers.get("x-nico-admin-token")?.trim() || "";
  if (!session && !rawOperatorToken) {
    return errorResponse(401, "specialist_authentication_required", "Sign in with an authorized NICO specialist account before accessing assessment data.");
  }

  const backend = backendOrigin();
  if (!backend) {
    return errorResponse(503, "assessment_backend_not_configured", "The canonical assessment backend is unavailable or has conflicting origins.");
  }

  const headers = new Headers({Accept: request.headers.get("accept") || "application/json"});
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const browserProjection = request.headers.get("x-nico-browser-projection");
  if (browserProjection) headers.set("X-NICO-Browser-Projection", browserProjection);
  if (session) headers.set("X-NICO-Operator-Session", session);
  if (rawOperatorToken) headers.set("X-NICO-Admin-Token", rawOperatorToken);
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  headers.set("X-Request-ID", requestId);
  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();
  const upstream = new URL(`${path}${request.nextUrl.search}`, backend);

  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutFor(request.method, path)),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "no-store, private, max-age=0",
      "X-Request-ID": requestId,
      "X-NICO-Proxy-Attempts": "1",
      "X-NICO-Specialist-Access": "required",
    });
    for (const name of RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return errorResponse(
      timedOut ? 504 : 502,
      timedOut ? "assessment_backend_timeout" : "assessment_backend_unreachable",
      "The authenticated assessment request did not complete. Recover the exact run status before repeating any mutation.",
      {request_id: requestId, retryable: request.method === "GET"},
    );
  }
}

export const GET = proxyAssessment;
export const POST = proxyAssessment;
