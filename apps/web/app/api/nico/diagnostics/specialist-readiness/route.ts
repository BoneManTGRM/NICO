export const dynamic = "force-dynamic";
export const runtime = "nodejs";

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
      // Invalid origins are excluded and reported through the bounded response below.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

function blocked(status: number, code: string, message: string): Response {
  return Response.json(
    {
      status: "blocked",
      artifact_schema: "nico.specialist_ship_readiness_proxy.v1",
      code,
      message,
      secrets_exposed: false,
      client_delivery_allowed: false,
    },
    {
      status,
      headers: {"Cache-Control": "no-store, private, max-age=0"},
    },
  );
}

export async function GET(): Promise<Response> {
  const backend = backendOrigin();
  if (!backend) {
    return blocked(
      503,
      "assessment_backend_not_configured",
      "The canonical assessment backend is unavailable or has conflicting origins.",
    );
  }
  try {
    const response = await fetch(new URL("/diagnostics/specialist-readiness", backend), {
      method: "GET",
      headers: {Accept: "application/json"},
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(20_000),
    });
    const contentType = response.headers.get("content-type") || "application/json";
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        "Cache-Control": "no-store, private, max-age=0",
        "Content-Type": contentType,
        "X-NICO-Specialist-Readiness": response.ok ? "available" : "blocked",
      },
    });
  } catch {
    return blocked(
      502,
      "assessment_backend_unreachable",
      "The specialist readiness diagnostic could not reach the canonical backend.",
    );
  }
}
