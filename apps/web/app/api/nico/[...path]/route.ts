import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const EXPRESS_START = "/assessment/express-run";
const EXPRESS_STATUS = /^\/assessment\/express-run\/[^/?#]+\/status$/;
const COMPREHENSIVE_INTAKE = "/assessment/comprehensive-intake";
const COMPREHENSIVE_STATUS = /^\/assessment\/comprehensive-run\/[^/?#]+$/;
const COMPREHENSIVE_CONTINUE = /^\/assessment\/comprehensive-run\/[^/?#]+\/continue$/;
const ALLOWED_DIAGNOSTIC_PATH = /^\/diagnostics\/(?:express-runtime|comprehensive-runtime)$/;

function jsonError(status: number, code: string, message: string) {
  return Response.json(
    {status: "error", detail: {code, message}},
    {status, headers: {"Cache-Control": "no-store"}},
  );
}

function configuredBackend(): URL | null {
  const configured = (process.env.NICO_API_URL || process.env.NEXT_PUBLIC_NICO_API_URL || "").trim();
  if (!configured) return null;

  try {
    const url = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    if (url.username || url.password) return null;
    if (!["http:", "https:"].includes(url.protocol)) return null;
    if (process.env.NODE_ENV === "production" && url.protocol !== "https:") return null;
    return url;
  } catch {
    return null;
  }
}

function assessmentRouteAllowed(method: string, path: string): boolean {
  if (method === "POST" && (path === EXPRESS_START || EXPRESS_STATUS.test(path))) return true;
  if (method === "POST" && path === COMPREHENSIVE_INTAKE) return true;
  if (method === "GET" && COMPREHENSIVE_STATUS.test(path)) return true;
  if (method === "POST" && COMPREHENSIVE_CONTINUE.test(path)) return true;
  return false;
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
    return jsonError(404, "nico_proxy_route_not_allowed", "Only native Express and Comprehensive lifecycle routes and bounded runtime diagnostics are available through this proxy.");
  }

  const backend = configuredBackend();
  if (!backend) {
    return jsonError(503, "assessment_backend_not_configured", "The assessment backend URL is unavailable or unsafe for this deployment.");
  }

  const upstream = new URL(`${apiPath}${request.nextUrl.search}`, backend);
  const headers = new Headers({Accept: "application/json"});
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  try {
    const shortRead = request.method === "GET" || ALLOWED_DIAGNOSTIC_PATH.test(apiPath);
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: shortRead ? AbortSignal.timeout(15_000) : AbortSignal.timeout(180_000),
    });

    const responseHeaders = new Headers({"Cache-Control": "no-store"});
    const responseContentType = response.headers.get("content-type");
    if (responseContentType) responseHeaders.set("Content-Type", responseContentType);

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return jsonError(502, "assessment_backend_unreachable", "The assessment backend could not be reached from the frontend deployment.");
  }
}

export const GET = proxyNico;
export const POST = proxyNico;
