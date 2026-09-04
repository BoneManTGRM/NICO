import {NextRequest, NextResponse} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SESSION_COOKIE = "nico-specialist-session";

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
    return NextResponse.json({status: "blocked", code: "specialist_login_origin_rejected"}, {status: 403});
  }
  const backend = backendOrigin();
  if (!backend) {
    return NextResponse.json({status: "blocked", code: "assessment_backend_not_configured"}, {status: 503});
  }
  const body = await request.json().catch(() => null) as {password?: unknown} | null;
  const password = String(body?.password || "").trim();
  if (!password || password.length > 4096) {
    return NextResponse.json({status: "blocked", code: "specialist_operator_password_required"}, {status: 422});
  }
  const response = await fetch(new URL("/assessment/comprehensive-operator/session", backend), {
    method: "POST",
    headers: {"X-NICO-Admin-Token": password, Accept: "application/json"},
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  }).catch(() => null);
  if (!response) {
    return NextResponse.json({status: "blocked", code: "assessment_backend_unreachable"}, {status: 502});
  }
  const payload = await response.json().catch(() => null) as {
    status?: unknown;
    session_token?: unknown;
    expires_in?: unknown;
  } | null;
  const session = String(payload?.session_token || "").trim();
  const expiresIn = Math.max(300, Math.min(43_200, Number(payload?.expires_in) || 14_400));
  if (!response.ok || payload?.status !== "authenticated" || !session) {
    return clearCookie(NextResponse.json(
      {status: "blocked", code: response.status === 403 ? "specialist_operator_authentication_invalid" : "specialist_session_unavailable"},
      {status: response.status === 403 ? 403 : 503},
    ));
  }
  const result = NextResponse.json({status: "authenticated", expires_in: expiresIn});
  result.cookies.set(SESSION_COOKIE, session, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: expiresIn,
  });
  result.headers.set("Cache-Control", "no-store, private, max-age=0");
  return result;
}

export async function GET(request: NextRequest) {
  const backend = backendOrigin();
  const session = request.cookies.get(SESSION_COOKIE)?.value?.trim() || "";
  if (!backend || !session) {
    return clearCookie(NextResponse.json({status: "unauthenticated"}, {status: 401}));
  }
  const response = await fetch(new URL("/assessment/comprehensive-operator/session", backend), {
    method: "GET",
    headers: {"X-NICO-Operator-Session": session, Accept: "application/json"},
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  }).catch(() => null);
  if (!response?.ok) {
    return clearCookie(NextResponse.json({status: "unauthenticated"}, {status: 401}));
  }
  return NextResponse.json({status: "authenticated"}, {headers: {"Cache-Control": "no-store, private, max-age=0"}});
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) {
    return NextResponse.json({status: "blocked"}, {status: 403});
  }
  return clearCookie(NextResponse.json({status: "signed_out"}));
}
