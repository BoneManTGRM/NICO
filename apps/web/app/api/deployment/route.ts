import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SCHEMA = "nico.frontend_deployment.v1";
const FULL_SHA = /^[0-9a-f]{40}$/i;

function safeOrigin(value: string | undefined): string {
  const candidate = (value ?? "").trim();
  if (!candidate) return "";
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password) return "";
    return parsed.origin;
  } catch {
    return "";
  }
}

function deploymentCommit(): string {
  const candidates = [
    process.env.VERCEL_GIT_COMMIT_SHA,
    process.env.NICO_FRONTEND_RELEASE_SHA,
    process.env.NEXT_PUBLIC_NICO_RELEASE_SHA,
    process.env.GIT_COMMIT_SHA,
    process.env.COMMIT_SHA,
  ];
  const commit = candidates.find((value) => FULL_SHA.test((value ?? "").trim()));
  return commit?.trim().toLowerCase() ?? "unavailable";
}

export async function GET() {
  const frontendCommit = deploymentCommit();
  const backendOrigin = safeOrigin(process.env.NEXT_PUBLIC_NICO_API_URL);
  const provider = process.env.VERCEL === "1" ? "vercel" : "unknown";
  const status = frontendCommit === "unavailable" ? "blocked" : "ok";

  return NextResponse.json(
    {
      artifact_schema: SCHEMA,
      status,
      provider,
      frontend_commit: frontendCommit,
      git_ref: (process.env.VERCEL_GIT_COMMIT_REF ?? "unavailable").slice(0, 160),
      deployment_environment: (process.env.VERCEL_ENV ?? process.env.NODE_ENV ?? "unknown").slice(0, 40),
      backend_origin: backendOrigin || "unavailable",
      commit_identity_available: frontendCommit !== "unavailable",
      human_review_required: true,
      client_delivery_allowed: false,
      guardrail:
        "This endpoint exposes deployment identity only. It does not authorize assessments, score changes, or client delivery.",
    },
    {
      status: status === "ok" ? 200 : 503,
      headers: {
        "Cache-Control": "no-store, private, max-age=0",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}
