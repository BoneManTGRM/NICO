export type ApprovalRequirement =
  | "secureAccess"
  | "reviewer"
  | "reviewerRole"
  | "report"
  | "download"
  | "confirmation"
  | "locked";

export type ApprovalRequirementInput = {
  operatorReady: boolean;
  reviewer: string;
  reviewerRole: string;
  pdfDigest: string;
  downloadedDigest: string;
  confirmed: boolean;
  reviewStatus: string;
};

/** UI guidance only. The server remains authoritative for approval readiness. */
export function unmetApprovalRequirements(input: ApprovalRequirementInput): ApprovalRequirement[] {
  const status = input.reviewStatus.trim().toLowerCase();
  if (status === "rejected" || status === "request_more_evidence") return ["locked"];

  const missing: ApprovalRequirement[] = [];
  if (!input.operatorReady) missing.push("secureAccess");
  if (!input.reviewer.trim()) missing.push("reviewer");
  if (!input.reviewerRole.trim()) missing.push("reviewerRole");
  if (!/^[0-9a-f]{64}$/i.test(input.pdfDigest)) {
    missing.push("report");
  } else if (input.downloadedDigest !== input.pdfDigest.toLowerCase()) {
    missing.push("download");
  }
  if (!input.confirmed) missing.push("confirmation");
  return missing;
}
