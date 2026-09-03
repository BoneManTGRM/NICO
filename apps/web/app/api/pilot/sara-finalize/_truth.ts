import {
  NICO_RUN_ID,
  PilotActionError,
  SARA_COMMIT_SHA,
  asRecord,
  type JsonRecord,
} from "./_lib";

const REPORT_JSON_URL = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${NICO_RUN_ID}/report/json`;
const TIMEOUT_MS = 240_000;

function norm(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

function collect(
  value: unknown,
  test: (key: string) => boolean,
  depth = 0,
): unknown[] {
  if (depth > 14 || value === null || value === undefined) return [];
  if (Array.isArray(value)) {
    return value.flatMap((item) => collect(item, test, depth + 1));
  }
  if (typeof value !== "object") return [];
  const found: unknown[] = [];
  for (const [key, child] of Object.entries(value as JsonRecord)) {
    if (test(norm(key))) found.push(child);
    found.push(...collect(child, test, depth + 1));
  }
  return found;
}

function strings(value: unknown, test: (key: string) => boolean): string[] {
  return collect(value, test)
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function requireZero(record: JsonRecord, key: string, label: string): void {
  if (!(key in record)) {
    throw new PilotActionError(`${label} is absent from the canonical report.`, 409);
  }
  const value = Number(record[key]);
  if (!Number.isFinite(value) || value !== 0) {
    throw new PilotActionError(`${label} is not zero.`, 409);
  }
}

function requireEmptyArray(record: JsonRecord, key: string, label: string): void {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new PilotActionError(`${label} is absent from the canonical report.`, 409);
  }
  if (value.length !== 0) {
    throw new PilotActionError(`${label} is not empty.`, 409);
  }
}

function assertCanonicalSubject(payload: JsonRecord): void {
  const identity = asRecord(payload.identity);
  const runId = String(identity.run_id || "").trim();
  const commitSha = String(identity.commit_sha || "").trim().toLowerCase();
  if (runId !== NICO_RUN_ID) {
    throw new PilotActionError("The canonical report is not the retained SARA Comprehensive run.", 409);
  }
  if (commitSha !== SARA_COMMIT_SHA) {
    throw new PilotActionError("The canonical report is not bound to the authorized immutable SARA commit.", 409);
  }

  const assessment = asRecord(payload.assessment);
  if (String(assessment.run_id || "").trim() !== NICO_RUN_ID) {
    throw new PilotActionError("The assessment identity does not match the retained SARA run.", 409);
  }
  if (String(assessment.commit_sha || "").trim().toLowerCase() !== SARA_COMMIT_SHA) {
    throw new PilotActionError("The assessment commit does not match the authorized SARA commit.", 409);
  }
}

export function assertExactArtifactIdentity(
  payload: JsonRecord,
): {identity: JsonRecord; pdfSha256: string} {
  const runIds = strings(payload, (key) => key === "run_id" || key === "comprehensive_run_id");
  if (!runIds.includes(NICO_RUN_ID)) {
    throw new PilotActionError("The response was not bound to the retained SARA Comprehensive run.", 409);
  }

  const shas = strings(
    payload,
    (key) => key.includes("sha") && (key.includes("commit") || key.includes("revision")),
  ).map((item) => item.toLowerCase());
  if (!shas.includes(SARA_COMMIT_SHA)) {
    throw new PilotActionError("The run no longer resolves to the authorized immutable SARA commit.", 409);
  }

  const identity = asRecord(payload.review_artifact_identity);
  const pdfSha256 = String(
    asRecord(asRecord(identity.artifact_digests).pdf).sha256 || "",
  ).trim().toLowerCase();
  if (!Object.keys(identity).length || !/^[0-9a-f]{64}$/.test(pdfSha256)) {
    throw new PilotActionError("NICO did not return a valid exact PDF artifact identity.", 409);
  }

  return {identity, pdfSha256};
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
): Promise<void> {
  const report = await canonicalReport();
  assertCanonicalSubject(report);

  const assessment = asRecord(report.assessment);
  const candidateSummary = asRecord(assessment.review_candidate_summary);
  const candidateDisposition = asRecord(assessment.candidate_disposition);
  const findingPopulation = asRecord(assessment.finding_population);
  const scannerRegister = asRecord(assessment.canonical_scanner_finding_register);
  const technicalTriage = asRecord(scannerRegister.technical_triage);
  const technicalTriageMetrics = asRecord(technicalTriage.workload_metrics);
  const clientRegister = asRecord(assessment.client_finding_remediation_register);
  const clientRegisterSummary = asRecord(clientRegister.summary);

  requireZero(candidateSummary, "review_required_total", "Review-required candidate total");
  requireZero(candidateDisposition, "review_required", "Candidate disposition review-required total");
  requireZero(assessment, "review_required_candidate_count", "Assessment review-required candidate total");
  requireZero(technicalTriage, "human_review_work_units", "Scanner-candidate review work units");
  requireZero(technicalTriageMetrics, "human_review_work_units", "Scanner-candidate workload metric");
  requireZero(technicalTriage, "technical_triage_pending", "Pending technical-triage total");
  requireZero(findingPopulation, "exact_source_code_finding_count", "Exact-source finding total");
  requireZero(findingPopulation, "operational_or_context_finding_count", "Operational/context finding total");
  requireZero(findingPopulation, "canonical_finding_count", "Canonical finding total");
  requireZero(assessment, "exact_source_finding_count", "Assessment exact-source finding total");
  requireZero(assessment, "operational_context_finding_count", "Assessment operational/context finding total");
  requireZero(clientRegisterSummary, "exact_source_code_finding_count", "Client-register exact-source finding total");
  requireZero(clientRegisterSummary, "operational_or_context_finding_count", "Client-register operational/context finding total");

  requireEmptyArray(report, "findings", "Top-level finding register");
  requireEmptyArray(assessment, "review_candidate_register", "Review-candidate register");
  requireEmptyArray(assessment, "decision_grade_findings_register", "Decision-grade finding register");
  requireEmptyArray(clientRegister, "code_findings", "Client code-finding register");
  requireEmptyArray(clientRegister, "operational_findings", "Client operational-finding register");

  if (expectedDraftPdfSha256) {
    const artifacts = Array.isArray(report.artifacts) ? report.artifacts : [];
    const pdfArtifact = artifacts
      .map((item) => asRecord(item))
      .find((item) => String(item.artifact_type || "") === "comprehensive_pdf");
    const reportPdfSha256 = String(pdfArtifact?.sha256 || "").trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(reportPdfSha256)) {
      throw new PilotActionError("The canonical report did not retain a valid draft PDF digest.", 409);
    }
    if (reportPdfSha256 !== expectedDraftPdfSha256.toLowerCase()) {
      throw new PilotActionError("The canonical draft PDF does not match the exact review artifact identity.", 409);
    }
  }
}
