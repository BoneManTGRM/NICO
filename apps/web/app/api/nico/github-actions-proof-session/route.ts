import {NextRequest, NextResponse} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SESSION_COOKIE = "nico-specialist-session";
const MAX_TOKEN_LENGTH = 20_000;

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
      // Invalid origins are excluded and fail closed below.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

function sameOriginOrServer(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return !origin || origin === request.nextUrl.origin;
}

function blocked(status: number, code: string): NextResponse {
  const response = NextResponse.json(
    {
      status: "blocked",
      code,
      human_review_required: true,
      client_delivery_allowed: false,
    },
    {status},
  );
  response.headers.set("Cache-Control", "no-store, private, max-age=0");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!sameOriginOrServer(request)) return blocked(403, "github_actions_proof_origin_rejected");
  const backend = backendOrigin();
  if (!backend) return blocked(503, "assessment_backend_not_configured");

  const body = await request.json().catch(() => null) as {oidc_token?: unknown} | null;
  const oidcToken = String(body?.oidc_token || "").trim();
  if (oidcToken.length < 100 || oidcToken.length > MAX_TOKEN_LENGTH) {
    return blocked(422, "github_actions_proof_identity_required");
  }

  const upstream = await fetch(new URL("/assessment/github-actions-proof-session", backend), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
    body: JSON.stringify({oidc_token: oidcToken}),
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(30_000),
  }).catch(() => null);
  if (!upstream) return blocked(502, "assessment_backend_unreachable");

  const payload = await upstream.json().catch(() => null) as {
    status?: unknown;
    session_token?: unknown;
    expires_in?: unknown;
    authority?: unknown;
    release_sha?: unknown;
    workflow_file?: unknown;
    run_id?: unknown;
    run_attempt?: unknown;
  } | null;
  const sessionToken = String(payload?.session_token || "").trim();
  if (!upstream.ok || payload?.status !== "authenticated" || !sessionToken) {
    return blocked(upstream.status === 429 ? 429 : upstream.status === 409 ? 409 : 403, "github_actions_proof_identity_rejected");
  }

  const expiresIn = Math.max(300, Math.min(43_200, Number(payload.expires_in) || 14_400));
  const response = NextResponse.json({
    status: "authenticated",
    artifact_schema: "nico.github_actions_proof_session_proxy.v1",
    expires_in: expiresIn,
    authority: "github_actions_production_proof",
    release_sha: String(payload.release_sha || ""),
    workflow_file: String(payload.workflow_file || ""),
    run_id: String(payload.run_id || ""),
    run_attempt: String(payload.run_attempt || ""),
    human_review_required: true,
    client_delivery_allowed: false,
  });
  response.cookies.set(SESSION_COOKIE, sessionToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: expiresIn,
  });
  response.headers.set("Cache-Control", "no-store, private, max-age=0");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
