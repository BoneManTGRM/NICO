import type {NextRequest} from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

const CAPABILITIES = "/providers/capabilities";
const PREFLIGHT = "/providers/onboarding/preflight";
const TIMEOUT_MS = 20_000;

type BackendResolution = {
  backend: URL | null;
  configuredCount: number;
  conflict: boolean;
};

function jsonError(status: number, code: string, message: string) {
  return Response.json(
    {
      status: "error",
      detail: {
        code,
        message,
        credential_detail_exposed: false,
        human_review_required: true,
        client_delivery_allowed: false,
      },
    },
    {status, headers: {"Cache-Control": "no-store"}},
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
      // Invalid deployment values are ignored and fail closed below.
    }
  }
  const values = [...seen.values()];
  return {
    backend: values.length === 1 ? values[0] : null,
    configuredCount: values.length,
    conflict: values.length > 1,
  };
}

function allowed(method: string, path: string): boolean {
  return (method === "GET" && path === CAPABILITIES)
    || (method === "POST" && path === PREFLIGHT);
}

async function proxyProviderOnboarding(
  request: NextRequest,
  context: {params: Promise<{path: string[]}>},
) {
  const segments = (await context.params).path || [];
  if (!segments.length || segments.some((segment) => !segment || segment === "." || segment === "..")) {
    return jsonError(404, "provider_onboarding_proxy_route_not_allowed", "The requested provider-onboarding route is not available through this proxy.");
  }

  const path = `/providers/${segments.map((segment) => encodeURIComponent(segment)).join("/")}`;
  if (!allowed(request.method, path)) {
    return jsonError(404, "provider_onboarding_proxy_route_not_allowed", "Only provider capability truth and ordinary onboarding preflight are available to the browser. Provider rollout administration is server-only.");
  }

  const resolution = configuredBackend();
  if (resolution.conflict) {
    return jsonError(503, "provider_backend_configuration_conflict", "Multiple different NICO backend origins are configured.");
  }
  if (!resolution.backend) {
    return jsonError(503, "provider_backend_not_configured", "The canonical NICO backend URL is unavailable or unsafe for this deployment.");
  }

  const headers = new Headers({Accept: "application/json"});
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  // Deliberately do not forward x-nico-admin-token or any provider credential header.
  const requestId = request.headers.get("x-request-id") || crypto.randomUUID();
  headers.set("X-Request-ID", requestId);
  const body = request.method === "GET" ? undefined : await request.arrayBuffer();
  const upstream = new URL(`${path}${request.nextUrl.search}`, resolution.backend);

  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Request-ID": requestId,
    });
    const responseType = response.headers.get("content-type");
    if (responseType) responseHeaders.set("Content-Type", responseType);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch {
    return jsonError(502, "provider_backend_unreachable", "The canonical provider-onboarding backend could not be reached within the bounded request window.");
  }
}

export const GET = proxyProviderOnboarding;
export const POST = proxyProviderOnboarding;
