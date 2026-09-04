export const dynamic = "force-dynamic";
export const runtime = "nodejs";

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
      // Invalid or conflicting deployment origins fail closed below.
    }
  }
  return origins.size === 1 ? [...origins.values()][0] : null;
}

export async function GET() {
  const backend = backendOrigin();
  if (!backend) {
    return Response.json(
      {status: "blocked", code: "assessment_backend_not_configured"},
      {status: 503, headers: {"Cache-Control": "no-store"}},
    );
  }
  try {
    const response = await fetch(
      new URL("/diagnostics/nico-release-provenance", backend),
      {method: "GET", cache: "no-store", signal: AbortSignal.timeout(20_000)},
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      {status: "blocked", code: "assessment_backend_unreachable"},
      {status: 502, headers: {"Cache-Control": "no-store"}},
    );
  }
}
