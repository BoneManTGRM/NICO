export type ReviewAction =
  | "assign"
  | "disposition_candidate"
  | "disposition_group"
  | "quality_control"
  | "request_evidence"
  | "resolve_evidence_request"
  | "stakeholder_evidence"
  | "start_session"
  | "stop_session"
  | "complete_empirical_study";

export type ReviewActionFields = {
  reviewer: string;
  reviewerRole: string;
  targetId: string;
  disposition: string;
  rationale: string;
  residualRisk: string;
  residualRiskOwner: string;
  escalationResolution: string;
  escalationOwner: string;
  assignee: string;
  specialistRole: string;
  qcOutcome: string;
  qcNote: string;
  requestText: string;
  requestOwner: string;
  resolutionNote: string;
  evidenceReferences: string;
  stakeholderStatement: string;
  sourceRole: string;
  evidenceReference: string;
};

/** Build transport data only; UI validation and request lifecycle remain with the caller. */
export function buildReviewActionPayload(action: ReviewAction, fields: ReviewActionFields): Record<string, unknown> {
  const {
    reviewer, reviewerRole, targetId, disposition,
    rationale, residualRisk, residualRiskOwner, escalationResolution,
    escalationOwner, assignee, specialistRole, qcOutcome,
    qcNote, requestText, requestOwner, resolutionNote,
    evidenceReferences, stakeholderStatement, sourceRole, evidenceReference,
  } = fields;
  const common: Record<string, unknown> = {
    action,
    reviewer: reviewer.trim(),
    reviewer_role: reviewerRole.trim(),
    review_authorized: true,
    authorization_confirmed: true,
  };
  if (action === "assign") return {...common, target_id: targetId.trim(), assignee: assignee.trim(), specialist_role: specialistRole.trim()};
  if (action === "disposition_candidate" || action === "disposition_group") {
    return {
      ...common,
      ...(action === "disposition_candidate" ? {candidate_id: targetId.trim()} : {cluster_id: targetId.trim()}),
      disposition,
      rationale: rationale.trim(),
      residual_risk: residualRisk.trim(),
      residual_risk_owner: residualRiskOwner.trim(),
      escalation_resolution: escalationResolution.trim(),
      escalation_owner: escalationOwner.trim(),
    };
  }
  if (action === "quality_control") return {...common, candidate_id: targetId.trim(), qc_outcome: qcOutcome, qc_note: qcNote.trim()};
  if (action === "request_evidence") return {...common, candidate_id: targetId.trim(), request_text: requestText.trim(), owner: requestOwner.trim()};
  if (action === "resolve_evidence_request") return {...common, request_id: targetId.trim(), resolution_note: resolutionNote.trim(), evidence_references: evidenceReferences.split("\n").map((item) => item.trim()).filter(Boolean)};
  if (action === "stakeholder_evidence") return {...common, statement: stakeholderStatement.trim(), source_role: sourceRole.trim(), evidence_reference: evidenceReference.trim()};
  return common;
}
