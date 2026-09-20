export const dynamic = "force-dynamic";

const UI_CONTRACT = "expert-engagement-v2";

function releaseSha(): string {
  const value = String(
    process.env.VERCEL_GIT_COMMIT_SHA
      || process.env.NICO_RELEASE_SHA
      || process.env.GITHUB_SHA
      || "unknown",
  ).trim();
  return /^[0-9a-f]{40}$/i.test(value) ? value.toLowerCase() : "unknown";
}

export async function GET(): Promise<Response> {
  return Response.json(
    {
      status: "ok",
      release_sha: releaseSha(),
      release_sha_source: process.env.VERCEL_GIT_COMMIT_SHA ? "VERCEL_GIT_COMMIT_SHA"
        : process.env.NICO_RELEASE_SHA ? "NICO_RELEASE_SHA"
          : process.env.GITHUB_SHA ? "GITHUB_SHA" : "unavailable",
      deployment_id: String(process.env.VERCEL_DEPLOYMENT_ID || "unavailable").trim(),
      deployment_id_source: process.env.VERCEL_DEPLOYMENT_ID ? "VERCEL_DEPLOYMENT_ID" : "unavailable",
      ui_contract: UI_CONTRACT,
      git_ref: String(process.env.VERCEL_GIT_COMMIT_REF || "").trim(),
      deployment_environment: String(process.env.VERCEL_ENV || process.env.NODE_ENV || "unknown").trim(),
    },
    {
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "CDN-Cache-Control": "no-store",
        "Vercel-CDN-Cache-Control": "no-store",
      },
    },
  );
}
