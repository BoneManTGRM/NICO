import type {NextRequest} from "next/server";
import {
  PilotActionError,
  approvalRecorded,
  approveExactReport,
  approvedPdf,
  assertExactRun,
  downloadResponse,
  errorResponse,
  operatorTokenFromForm,
  statusPayload,
} from "../_lib";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<Response> {
  try {
    const token = await operatorTokenFromForm(request, "confirm_exact_report");
    const current = await statusPayload(token);
    const {identity} = assertExactRun(current);

    const approved = approvalRecorded(current)
      ? current
      : await approveExactReport(token, identity);

    assertExactRun(approved);
    if (!approvalRecorded(approved)) {
      throw new PilotActionError(
        "NICO did not record an approved human-review decision for the exact edition.",
        409,
      );
    }

    const pdf = approvedPdf(approved);
    return downloadResponse(
      pdf.bytes,
      "application/pdf",
      pdf.filename,
      pdf.sha256,
    );
  } catch (caught) {
    return errorResponse(caught);
  }
}
