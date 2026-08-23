import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

const UPSTREAM_PATH = "/providers/operator/comprehensive-intake";
const WRITE_TIMEOUT_MS = 240_000;

function jsonError(status: number, code: string, message: string) {
  return Response.json(
    {status: "error", detail: {code, message, retryable: false}},
    {status, headers: {"Cache-Control": "no-store"}},
  );
}

function configuredBackend(): URL | null {
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
      // Invalid deployment values are rejected by returning no canonical backend below.
    }
  }
  return seen.size === 1 ? [...seen.values()][0] : null;
}

function sameOrigin(request: NextRequest): boolean {
  const origin = String(request.headers.get("origin") || "").trim();
  if (!origin) return true;
  try {
    return new URL(origin).origin === request.nextUrl.origin;
  } catch {
    return false;
  }
}

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) {
    return jsonError(403, "operator_provider_intake_cross_origin_blocked", "Operator provider intake requires a same-origin request.");
  }

  const adminToken = String(request.headers.get("x-nico-admin-token") || "").trim();
  if (!adminToken) {
    return jsonError(403, "authorized_nico_operator_required", "NICO operator authorization is required for this provider assessment.");
  }

  const backend = configuredBackend();
  if (!backend) {
    return jsonError(503, "assessment_backend_not_configured", "The canonical assessment backend is unavailable or ambiguously configured.");
  }

  const contentType = request.headers.get("content-type") || "application/json";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return jsonError(415, "operator_provider_intake_json_required", "Operator provider intake requires an application/json request.");
  }

  const body = await request.arrayBuffer();
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  const upstream = new URL(UPSTREAM_PATH, backend);
  try {
    const response = await fetch(upstream, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-NICO-Admin-Token": adminToken,
        "X-Request-ID": requestId,
      },
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(WRITE_TIMEOUT_MS),
    });

    if (response.status >= 300 && response.status < 400) {
      await response.arrayBuffer();
      return jsonError(502, "operator_provider_intake_redirect_blocked", "The canonical backend attempted an unexpected redirect.");
    }

    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Request-ID": requestId,
    });
    const responseContentType = response.headers.get("content-type");
    if (responseContentType) responseHeaders.set("Content-Type", responseContentType);
    const runId = response.headers.get("x-nico-run-id");
    if (runId) responseHeaders.set("X-NICO-Run-ID", runId);

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    return Response.json(
      {
        status: "error",
        detail: {
          code: timedOut ? "operator_provider_intake_timeout" : "assessment_backend_unreachable",
          message: timedOut
            ? "The operator provider intake did not complete within the bounded write window."
            : "The canonical assessment backend could not be reached.",
          retryable: false,
          request_id: requestId,
        },
      },
      {
        status: timedOut ? 504 : 502,
        headers: {"Cache-Control": "no-store", "X-Request-ID": requestId},
      },
    );
  }
}
