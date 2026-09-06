import {NextRequest, NextResponse} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SESSION_COOKIE = "nico-specialist-session";

function sessionResponse(
  body: Record<string, unknown>,
  status = 200,
  headers: Record<string, string> = {},
): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: {...headers, "Cache-Control": "no-store, private, max-age=0"},
  });
}

function rateLimitedResponse(response: Response): NextResponse {
  return sessionResponse(
    {status: "blocked", code: "specialist_request_rate_limited", retryable: true},
    429,
    {"Retry-After": response.headers.get("Retry-After") || "60"},
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
      // Invalid values are rejected below.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return !origin || origin === request.nextUrl.origin;
}

function clearCookie(response: NextResponse): NextResponse {
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return sessionResponse({status: "blocked", code: "specialist_login_origin_rejected"}, 403);
  }
  const backend = backendOrigin();
  if (!backend) {
    return sessionResponse({status: "blocked", code: "assessment_backend_not_configured"}, 503);
  }
  const body = await request.json().catch(() => null) as {password?: unknown} | null;
  const password = String(body?.password || "").trim();
  if (!password || password.length > 4096) {
    return sessionResponse({status: "blocked", code: "specialist_operator_password_required"}, 422);
  }
  const response = await fetch(new URL("/assessment/comprehensive-operator/session", backend), {
    method: "POST",
    headers: {"X-NICO-Admin-Token": password, Accept: "application/json"},
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(20_000),
  }).catch(() => null);
  if (!response) {
    return sessionResponse({status: "blocked", code: "assessment_backend_unreachable"}, 502);
  }
  if (response.status === 429) return rateLimitedResponse(response);
  if (response.status === 401 || response.status === 403) {
    return clearCookie(sessionResponse(
      {status: "blocked", code: "specialist_operator_authentication_invalid"}, 403,
    ));
  }
  if (!response.ok) {
    return sessionResponse({status: "blocked", code: "specialist_session_unavailable"}, 503);
  }
  const payload = await response.json().catch(() => null) as {
    status?: unknown;
    session_token?: unknown;
    expires_in?: unknown;
  } | null;
  const session = String(payload?.session_token || "").trim();
  const expiresIn = Math.max(300, Math.min(43_200, Number(payload?.expires_in) || 14_400));
  if (payload?.status !== "authenticated" || !session) {
    return sessionResponse({status: "blocked", code: "specialist_session_unavailable"}, 503);
  }
  const result = sessionResponse({status: "authenticated", expires_in: expiresIn});
  result.cookies.set(SESSION_COOKIE, session, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: expiresIn,
  });
  return result;
}

export async function GET(request: NextRequest) {
  const backend = backendOrigin();
  const session = request.cookies.get(SESSION_COOKIE)?.value?.trim() || "";
  if (!session) {
    return clearCookie(sessionResponse({status: "unauthenticated"}, 401));
  }
  if (!backend) {
    return sessionResponse({status: "blocked", code: "assessment_backend_not_configured"}, 503);
  }
  const response = await fetch(new URL("/assessment/comprehensive-operator/session", backend), {
    method: "GET",
    headers: {"X-NICO-Operator-Session": session, Accept: "application/json"},
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(15_000),
  }).catch(() => null);
  if (!response) {
    return sessionResponse({status: "blocked", code: "assessment_backend_unreachable"}, 502);
  }
  if (response.status === 429) return rateLimitedResponse(response);
  // Only an explicit authentication denial invalidates the saved cookie. A
  // timeout or unavailable backend cannot establish whether the session expired.
  if (response.status === 401 || response.status === 403) {
    return clearCookie(sessionResponse({status: "unauthenticated"}, 401));
  }
  if (!response.ok) {
    return sessionResponse({status: "blocked", code: "specialist_session_unavailable"}, 503);
  }
  const payload = await response.json().catch(() => null) as {status?: unknown} | null;
  if (payload?.status !== "authenticated") {
    return sessionResponse({status: "blocked", code: "specialist_session_unavailable"}, 503);
  }
  return sessionResponse({status: "authenticated"});
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) {
    return sessionResponse({status: "blocked"}, 403);
  }
  return clearCookie(sessionResponse({status: "signed_out"}));
}
