import {
  NICO_RUN_ID,
  SARA_COMMIT_SHA,
  errorResponse,
} from "../_lib";
import {assertCanonicalReportClear} from "../_truth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(): Promise<Response> {
  try {
    await assertCanonicalReportClear();
    return Response.json(
      {
        status: "ready",
        run_id: NICO_RUN_ID,
        commit_sha: SARA_COMMIT_SHA,
        canonical_workload_verified_clear: true,
      },
      {
        status: 200,
        headers: {
          "Cache-Control": "no-store, max-age=0",
          "X-Content-Type-Options": "nosniff",
          "Referrer-Policy": "no-referrer",
        },
      },
    );
  } catch (caught) {
    return errorResponse(caught);
  }
}
