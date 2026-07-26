export const dynamic = "force-dynamic";

const UI_CONTRACT = "expert-engagement-v2";

function releaseSha(): string {
  return String(
    process.env.VERCEL_GIT_COMMIT_SHA
      || process.env.NICO_RELEASE_SHA
      || process.env.GITHUB_SHA
      || "unknown",
  ).trim();
}

export async function GET(): Promise<Response> {
  return Response.json(
    {
      status: "ok",
      release_sha: releaseSha(),
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
