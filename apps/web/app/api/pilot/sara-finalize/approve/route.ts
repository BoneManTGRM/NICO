import type {NextRequest} from "next/server";
import {
  PilotActionError,
  approvalRecorded,
  approveExactReport,
  approvedPdf,
  downloadResponse,
  errorResponse,
  operatorTokenFromForm,
  statusPayload,
} from "../_lib";
import {
  assertCanonicalReportClear,
  assertExactArtifactIdentity,
} from "../_truth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<Response> {
  try {
    const token = await operatorTokenFromForm(request, "confirm_exact_report");
    const current = await statusPayload(token);
    const {identity, pdfSha256} = assertExactArtifactIdentity(current);
    await assertCanonicalReportClear(pdfSha256);

    const approved = approvalRecorded(current)
      ? current
      : await approveExactReport(token, identity);

    assertExactArtifactIdentity(approved);
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
