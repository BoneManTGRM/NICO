import {
  ACCESS_METHOD,
  AUTHORIZED_SCOPE,
  CLIENT_NAME,
  CUSTOMER_ID,
  ENGAGEMENT_METADATA_SHA256,
  NICO_RUN_ID,
  PRIMARY_TECHNICAL_CONTACT,
  PROJECT_ID,
  PROJECT_NAME,
  PilotActionError,
  SARA_COMMIT_SHA,
  SARA_REPOSITORY,
  approvalRecorded,
  asRecord,
  deliveryAllowed,
  type JsonRecord,
} from "./_pilot";

const REPORT_JSON_URL = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${NICO_RUN_ID}/report/json`;
const TIMEOUT_MS = 240_000;
const SHA256 = /^[0-9a-f]{64}$/;

export type PilotPreflight = {
  ready: true;
  client_delivery_identity_verified: true;
  exact_artifact_ready: true;
  run_id: string;
  repository: string;
  commit_sha: string;
  customer_id: string;
  project_id: string;
  client_name: string;
  project_name: string;
  primary_technical_contact: string;
  access_method: string;
  authorized_scope: string;
  engagement_metadata_sha256: string;
  score: number;
  canonical_finding_count: number;
  review_required_candidate_count: number;
  review_status: string;
  client_delivery_allowed: boolean;
  pdf_filename: string;
  pdf_sha256: string;
};

function text(value: unknown): string {
  return String(value || "").trim();
}

function lower(value: unknown): string {
  return text(value).toLowerCase();
}

function requireEqual(actual: unknown, expected: string, label: string): void {
  if (text(actual) !== expected) {
    throw new PilotActionError(`${label} does not match the authorized SARA pilot.`, 409);
  }
}

function requireSha(value: unknown, label: string): string {
  const digest = lower(value);
  if (!SHA256.test(digest)) {
    throw new PilotActionError(`${label} is not a valid SHA-256 digest.`, 409);
  }
  return digest;
}

function requireZero(value: unknown, label: string): number {
  const count = Number(value);
  if (!Number.isFinite(count) || count !== 0) {
    throw new PilotActionError(`${label} is not zero.`, 409);
  }
  return count;
}

function collectStrings(
  value: unknown,
  acceptedKeys: Set<string>,
  depth = 0,
): string[] {
  if (depth > 14 || value === null || value === undefined) return [];
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectStrings(item, acceptedKeys, depth + 1));
  }
  if (typeof value !== "object") return [];
  const values: string[] = [];
  for (const [key, child] of Object.entries(value as JsonRecord)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]+/g, "_");
    if (acceptedKeys.has(normalized) && typeof child === "string" && child.trim()) {
      values.push(child.trim());
    }
    values.push(...collectStrings(child, acceptedKeys, depth + 1));
  }
  return values;
}

export function assertResponseIdentity(payload: JsonRecord): void {
  const runIds = collectStrings(
    payload,
    new Set(["run_id", "comprehensive_run_id"]),
  );
  if (!runIds.includes(NICO_RUN_ID)) {
    throw new PilotActionError(
      "NICO's protected response was not bound to the exact SARA pilot run.",
      409,
    );
  }

  const commitShas = collectStrings(
    payload,
    new Set(["commit_sha", "expected_commit_sha", "target_commit_sha"]),
  ).map((item) => item.toLowerCase());
  if (!commitShas.includes(SARA_COMMIT_SHA)) {
    throw new PilotActionError(
      "NICO's protected response was not bound to the immutable SARA commit.",
      409,
    );
  }
}

export function assertExactArtifactIdentity(
  payload: JsonRecord,
): {identity: JsonRecord; pdfSha256: string} {
  requireEqual(payload.run_id, NICO_RUN_ID, "Run ID");
  if (lower(payload.commit_sha) !== SARA_COMMIT_SHA) {
    throw new PilotActionError(
      "The run no longer resolves to the authorized immutable SARA commit.",
      409,
    );
  }
  requireEqual(payload.repository, SARA_REPOSITORY, "Repository identity");
  requireEqual(payload.customer_id, CUSTOMER_ID, "Canonical customer ID");
  requireEqual(payload.project_id, PROJECT_ID, "Canonical project ID");

  const identity = asRecord(payload.review_artifact_identity);
  requireEqual(identity.run_id, NICO_RUN_ID, "Review-artifact run ID");
  if (lower(identity.commit_sha) !== SARA_COMMIT_SHA) {
    throw new PilotActionError(
      "The review artifact is not bound to the immutable SARA commit.",
      409,
    );
  }
  if (text(identity.identity_version) !== "nico.comprehensive.review_artifact_identity.v1") {
    throw new PilotActionError(
      "NICO returned an unsupported review-artifact identity version.",
      409,
    );
  }

  const pdfSha256 = requireSha(identity.pdf_sha256, "Review PDF identity");
  requireSha(identity.html_sha256, "Review HTML identity");
  requireSha(identity.json_sha256, "Review JSON identity");
  requireSha(identity.artifact_set_sha256, "Review artifact-set identity");
  return {identity, pdfSha256};
}

function comprehensivePdf(report: JsonRecord): JsonRecord {
  const artifacts = report.artifacts;
  if (Array.isArray(artifacts)) {
    return artifacts
      .map((item) => asRecord(item))
      .find((item) => text(item.artifact_type) === "comprehensive_pdf") || {};
  }
  return asRecord(asRecord(artifacts).comprehensive_pdf);
}

async function canonicalReport(): Promise<JsonRecord> {
  const response = await fetch(REPORT_JSON_URL, {
    method: "GET",
    headers: {Accept: "application/json"},
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new PilotActionError(
      `The canonical report JSON could not be read (HTTP ${response.status}).`,
      response.status || 502,
    );
  }
  try {
    return asRecord(await response.json());
  } catch {
    throw new PilotActionError("The canonical report JSON was invalid.", 502);
  }
}

export async function assertCanonicalReportClear(
  expectedDraftPdfSha256 = "",
): Promise<PilotPreflight> {
  const report = await canonicalReport();
  const identity = asRecord(report.identity);
  const engagement = asRecord(report.engagement_metadata);
  const assessment = asRecord(report.assessment);
  const approval = asRecord(report.approval);
  const lifecycle = asRecord(report.lifecycle);

  requireEqual(identity.run_id, NICO_RUN_ID, "Canonical report run ID");
  requireEqual(identity.repository, SARA_REPOSITORY, "Canonical repository");
  if (lower(identity.commit_sha) !== SARA_COMMIT_SHA) {
    throw new PilotActionError(
      "The canonical report is not bound to the authorized immutable SARA commit.",
      409,
    );
  }
  requireEqual(identity.customer_id, CUSTOMER_ID, "Canonical customer ID");
  requireEqual(identity.project_id, PROJECT_ID, "Canonical project ID");
  requireEqual(identity.customer_name, CLIENT_NAME, "Client name");
  requireEqual(identity.project_name, PROJECT_NAME, "Project name");
  requireEqual(
    identity.primary_technical_contact,
    PRIMARY_TECHNICAL_CONTACT,
    "Primary technical contact",
  );
  requireEqual(identity.access_method, ACCESS_METHOD, "Access method");
  requireEqual(identity.authorized_scope, AUTHORIZED_SCOPE, "Authorized scope");
  if (lower(identity.engagement_metadata_sha256) !== ENGAGEMENT_METADATA_SHA256) {
    throw new PilotActionError("The canonical identity metadata digest changed.", 409);
  }

  requireEqual(engagement.client_name, CLIENT_NAME, "Retained client name");
  requireEqual(engagement.project_name, PROJECT_NAME, "Retained project name");
  requireEqual(
    engagement.primary_technical_contact,
    PRIMARY_TECHNICAL_CONTACT,
    "Retained primary technical contact",
  );
  requireEqual(engagement.access_method, ACCESS_METHOD, "Retained access method");
  requireEqual(engagement.authorized_scope, AUTHORIZED_SCOPE, "Retained authorized scope");
  requireEqual(engagement.source, "client_supplied_intake", "Retained metadata source");
  if (lower(engagement.engagement_metadata_sha256) !== ENGAGEMENT_METADATA_SHA256) {
    throw new PilotActionError("The retained engagement metadata digest changed.", 409);
  }

  const canonicalFindingCount = requireZero(
    assessment.canonical_finding_count,
    "Canonical finding count",
  );
  const reviewRequiredCandidateCount = requireZero(
    assessment.review_required_candidate_count,
    "Review-required candidate count",
  );
  if (!Array.isArray(report.findings) || report.findings.length !== 0) {
    throw new PilotActionError("The canonical finding register is not empty.", 409);
  }

  const artifact = comprehensivePdf(report);
  const pdfSha256 = requireSha(artifact.sha256, "Canonical draft PDF");
  if (expectedDraftPdfSha256 && pdfSha256 !== expectedDraftPdfSha256.toLowerCase()) {
    throw new PilotActionError(
      "The canonical draft PDF does not match the exact review-artifact identity.",
      409,
    );
  }
  const pdfFilename = text(artifact.filename);
  if (!pdfFilename) {
    throw new PilotActionError("The canonical draft PDF filename is absent.", 409);
  }

  const score = Number(assessment.score);
  if (!Number.isFinite(score)) {
    throw new PilotActionError("The canonical assessment score is absent.", 409);
  }

  const reviewStatus = text(
    approval.decision
      || lifecycle.human_review_status
      || report.approval_status
      || "pending",
  );

  return {
    ready: true,
    client_delivery_identity_verified: true,
    exact_artifact_ready: true,
    run_id: NICO_RUN_ID,
    repository: SARA_REPOSITORY,
    commit_sha: SARA_COMMIT_SHA,
    customer_id: CUSTOMER_ID,
    project_id: PROJECT_ID,
    client_name: CLIENT_NAME,
    project_name: PROJECT_NAME,
    primary_technical_contact: PRIMARY_TECHNICAL_CONTACT,
    access_method: ACCESS_METHOD,
    authorized_scope: AUTHORIZED_SCOPE,
    engagement_metadata_sha256: ENGAGEMENT_METADATA_SHA256,
    score,
    canonical_finding_count: canonicalFindingCount,
    review_required_candidate_count: reviewRequiredCandidateCount,
    review_status: reviewStatus,
    client_delivery_allowed: deliveryAllowed(report),
    pdf_filename: pdfFilename,
    pdf_sha256: pdfSha256,
  };
}

export function assertApprovalDecision(payload: JsonRecord): void {
  assertResponseIdentity(payload);
  if (!approvalRecorded(payload)) {
    throw new PilotActionError(
      "NICO did not record an approved human-review decision for the exact edition.",
      409,
    );
  }
  if (deliveryAllowed(payload)) {
    throw new PilotActionError(
      "NICO combined approval with delivery authorization instead of preserving the separate gate.",
      409,
    );
  }
}

export function assertDeliveryAuthorization(payload: JsonRecord): void {
  assertResponseIdentity(payload);
  if (!approvalRecorded(payload) || !deliveryAllowed(payload)) {
    throw new PilotActionError(
      "NICO did not record client-delivery authorization for the exact approved edition.",
      409,
    );
  }
}
