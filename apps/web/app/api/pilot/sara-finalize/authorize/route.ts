import type {NextRequest} from "next/server";
import {
  PilotActionError,
  approvalRecorded,
  approvedDeliveryPackage,
  authorizeExactDelivery,
  deliveryAllowed,
  downloadResponse,
  errorResponse,
  operatorTokenFromForm,
  statusPayload,
} from "../_pilot";
import {
  assertCanonicalReportClear,
  assertDeliveryAuthorization,
  assertExactArtifactIdentity,
} from "../_truth-v2";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<Response> {
  try {
    const token = await operatorTokenFromForm(request, "confirm_approved_pdf");
    const current = await statusPayload(token);
    const {identity} = assertExactArtifactIdentity(current);
    await assertCanonicalReportClear();

    if (!approvalRecorded(current)) {
      throw new PilotActionError(
        "The exact report has not yet received its recorded human approval. Complete the approval step first.",
        409,
      );
    }

    if (!deliveryAllowed(current)) {
      const authorized = await authorizeExactDelivery(token, identity);
      assertDeliveryAuthorization(authorized);
    }

    const finalStatus = await statusPayload(token);
    assertExactArtifactIdentity(finalStatus);
    if (!approvalRecorded(finalStatus) || !deliveryAllowed(finalStatus)) {
      throw new PilotActionError(
        "NICO did not retain client-delivery authorization for the exact approved edition.",
        409,
      );
    }

    const archive = await approvedDeliveryPackage(token);
    return downloadResponse(
      archive.bytes,
      "application/zip",
      archive.filename,
      archive.sha256,
    );
  } catch (caught) {
    return errorResponse(caught);
  }
}
