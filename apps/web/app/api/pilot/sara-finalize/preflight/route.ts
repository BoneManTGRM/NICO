import {errorResponse} from "../_pilot";
import {assertCanonicalReportClear} from "../_truth-v2";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(): Promise<Response> {
  try {
    const preflight = await assertCanonicalReportClear();
    return Response.json(preflight, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, max-age=0",
        Pragma: "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
      },
    });
  } catch (caught) {
    return errorResponse(caught);
  }
}
