const RUN_ID = "comprun_2ba62f37f4ab4b7988c609f27398c63e";
const REPOSITORY = "BoneManTGRM/SARA";
const COMMIT_SHA = "d63f09d3d5d6e4a53860faec0ea5cb372a37c381";
const CUSTOMER_ID = "boneman-sara-client";
const PROJECT_ID = "sara-controlled-pilot-001";
const CLIENT_NAME = "SARA / BoneManTGRM";
const PROJECT_NAME = "SARA — First Controlled Production Pilot";
const CONTACT = "Cody Ryan Jenkins (GitHub: BoneManTGRM)";
const ACCESS_METHOD = "Authorized public GitHub repository using anonymous read-only access; no write permissions or provider credential supplied.";
const AUTHORIZED_SCOPE = `Read-only technical assessment of ${REPOSITORY} at exact commit ${COMMIT_SHA} only. No writes, deployments, account changes, outreach, or access outside this repository and SHA.`;
const METADATA_SHA256 = "c486348bd6b69e3406198c66383a635f3a3c2455b47ed77efb8cb17308f8af58";
const URL = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${RUN_ID}/report/json`;

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function exact(owner, key, expected, label) {
  if (String(owner[key] ?? "") !== expected) {
    throw new Error(`${label} mismatch`);
  }
}

function zero(owner, key, label) {
  const value = Number(owner[key]);
  if (!Number.isFinite(value) || value !== 0) {
    throw new Error(`${label}=${owner[key]}`);
  }
}

const response = await fetch(URL, {
  headers: {Accept: "application/json", "User-Agent": "NICO-SARA-Bridge-Preflight/2.0"},
  cache: "no-store",
});
if (!response.ok) throw new Error(`report read failed: HTTP ${response.status}`);
const report = record(await response.json());
const identity = record(report.identity);
const engagement = record(report.engagement_metadata);
const assessment = record(report.assessment);

for (const [key, expected, label] of [
  ["run_id", RUN_ID, "run ID"],
  ["repository", REPOSITORY, "repository"],
  ["commit_sha", COMMIT_SHA, "commit SHA"],
  ["customer_id", CUSTOMER_ID, "customer ID"],
  ["project_id", PROJECT_ID, "project ID"],
  ["customer_name", CLIENT_NAME, "client name"],
  ["project_name", PROJECT_NAME, "project name"],
  ["primary_technical_contact", CONTACT, "primary technical contact"],
  ["access_method", ACCESS_METHOD, "access method"],
  ["authorized_scope", AUTHORIZED_SCOPE, "authorized scope"],
  ["engagement_metadata_source", "client_supplied_intake", "metadata source"],
  ["engagement_metadata_sha256", METADATA_SHA256, "identity metadata digest"],
]) exact(identity, key, expected, label);

for (const [key, expected, label] of [
  ["client_name", CLIENT_NAME, "retained client name"],
  ["project_name", PROJECT_NAME, "retained project name"],
  ["primary_technical_contact", CONTACT, "retained contact"],
  ["access_method", ACCESS_METHOD, "retained access method"],
  ["authorized_scope", AUTHORIZED_SCOPE, "retained scope"],
  ["source", "client_supplied_intake", "retained metadata source"],
  ["sha256", METADATA_SHA256, "retained metadata digest"],
]) exact(engagement, key, expected, label);

zero(assessment, "canonical_finding_count", "canonical findings");
zero(assessment, "review_required_candidate_count", "review-required candidates");
if (!Array.isArray(report.findings) || report.findings.length !== 0) {
  throw new Error("top-level finding register is not empty");
}

const artifacts = Array.isArray(report.artifacts) ? report.artifacts.map(record) : [];
const pdf = artifacts.find((item) => String(item.artifact_type || "") === "comprehensive_pdf");
if (!pdf || !/^[0-9a-f]{64}$/i.test(String(pdf.sha256 || ""))) {
  throw new Error("retained PDF digest missing or invalid");
}

console.log(JSON.stringify({
  status: "passed",
  client_delivery_identity_verified: true,
  exact_artifact_ready: true,
  run_id: RUN_ID,
  repository: REPOSITORY,
  commit_sha: COMMIT_SHA,
  customer_id: CUSTOMER_ID,
  project_id: PROJECT_ID,
  client_name: CLIENT_NAME,
  project_name: PROJECT_NAME,
  score: assessment.score,
  review_required_candidates: 0,
  canonical_findings: 0,
  pdf_sha256: pdf.sha256,
  review_status: report.review_status,
  client_delivery_allowed: report.client_delivery_allowed,
}, null, 2));
