import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 30;

const BACKEND_PATH = "/assessment/github-actions-production-proof/session";

function errorResponse(status: number, code: string, message: string) {
  return Response.json(
    {status: "blocked", detail: {code, message, retryable: false}},
    {status, headers: {"Cache-Control": "no-store, private, max-age=0"}},
  );
}

function backendOrigin(): URL | null {
  const values = [
    process.env.NICO_API_URL,
    process.env.NICO_BACKEND_URL,
    process.env.NEXT_PUBLIC_NICO_API_URL,
  ].map((value) => String(value || "").trim()).filter(Boolean);
  const origins = new Map<string, URL>();
  for (const value of values) {
    try {
      const url = new URL(value.endsWith("/") ? value : `${value}/`);
      if (url.username || url.password || !["http:", "https:"].includes(url.protocol)) continue;
      if (process.env.NODE_ENV === "production" && url.protocol !== "https:") continue;
      origins.set(url.href, url);
    } catch {
      // Invalid origins are rejected through the bounded response below.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

export async function POST(request: NextRequest) {
  const authorization = request.headers.get("authorization")?.trim() || "";
  if (!authorization.toLowerCase().startsWith("bearer ")) {
    return errorResponse(
      401,
      "github_actions_oidc_bearer_required",
      "A GitHub Actions OIDC bearer token is required.",
    );
  }
  const backend = backendOrigin();
  if (!backend) {
    return errorResponse(
      503,
      "assessment_backend_not_configured",
      "The canonical NICO backend is unavailable or has conflicting origins.",
    );
  }
  try {
    const upstream = await fetch(new URL(BACKEND_PATH, backend), {
      method: "POST",
      headers: {
        Authorization: authorization,
        Accept: "application/json",
        "X-Request-ID": request.headers.get("x-request-id") || crypto.randomUUID(),
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(25_000),
    });
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store, private, max-age=0",
      },
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return errorResponse(
      timedOut ? 504 : 502,
      timedOut ? "github_actions_session_timeout" : "github_actions_session_unavailable",
      "The production-proof session exchange did not complete.",
    );
  }
}
