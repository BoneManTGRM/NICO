import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const ALLOWED_ASSESSMENT_PATH = /^\/assessment\/(?:mid-run|full-run)(?:\/[^/?#]+\/status)?$/;

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
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    if (process.env.NODE_ENV === "production" && url.protocol !== "https:") return null;
    return url;
  } catch {
    return null;
  }
}

async function proxyAssessment(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return jsonError(404, "assessment_proxy_route_not_allowed", "The requested assessment route is not available through this proxy.");
  }

  const apiPath = `/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  if (!ALLOWED_ASSESSMENT_PATH.test(apiPath)) {
    return jsonError(404, "assessment_proxy_route_not_allowed", "Only canonical Mid and Full lifecycle routes are available through this proxy.");
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
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(285_000),
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

export const GET = proxyAssessment;
export const POST = proxyAssessment;
