import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ALLOWED_ASSESSMENT_PATH = /^\/assessment\/(?:github|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;

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

async function redirectAssessment(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return jsonError(404, "assessment_proxy_route_not_allowed", "The requested assessment route is not available through this transport.");
  }

  const apiPath = `/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  if (!ALLOWED_ASSESSMENT_PATH.test(apiPath)) {
    return jsonError(404, "assessment_proxy_route_not_allowed", "Only canonical Express, Mid, and Full assessment routes are available through this transport.");
  }

  const backend = configuredBackend();
  if (!backend) {
    return jsonError(503, "assessment_backend_not_configured", "The assessment backend URL is unavailable or unsafe for this deployment.");
  }
  if (backend.origin === request.nextUrl.origin) {
    return jsonError(503, "assessment_backend_loop", "The assessment backend URL resolves to the frontend origin and cannot be used.");
  }

  const upstream = new URL(`${apiPath}${request.nextUrl.search}`, backend);
  return new Response(null, {
    status: 307,
    headers: {
      "Cache-Control": "no-store",
      Location: upstream.toString(),
    },
  });
}

export const GET = redirectAssessment;
export const POST = redirectAssessment;
