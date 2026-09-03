const RUN_ID = "comprun_0094b14ba0691ae027e8e52ffd3a1e58";
const COMMIT_SHA = "d63f09d3d5d6e4a53860faec0ea5cb372a37c381";
const URL = `https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/${RUN_ID}/report/json`;

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function norm(key) {
  return key.toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

function collect(value, key, depth = 0) {
  if (depth > 14 || value == null) return [];
  if (Array.isArray(value)) return value.flatMap((item) => collect(item, key, depth + 1));
  if (typeof value !== "object") return [];
  const found = [];
  for (const [candidate, child] of Object.entries(value)) {
    if (norm(candidate) === key) found.push(child);
    found.push(...collect(child, key, depth + 1));
  }
  return found;
}

function zero(owner, key, label) {
  if (!(key in owner)) throw new Error(`${label} absent`);
  const value = Number(owner[key]);
  if (!Number.isFinite(value) || value !== 0) throw new Error(`${label}=${owner[key]}`);
}

function empty(owner, key, label) {
  if (!Array.isArray(owner[key])) throw new Error(`${label} absent`);
  if (owner[key].length !== 0) throw new Error(`${label}=${owner[key].length}`);
}

const response = await fetch(URL, {headers: {Accept: "application/json"}, cache: "no-store"});
if (!response.ok) throw new Error(`report read failed: HTTP ${response.status}`);
const report = record(await response.json());
const identity = record(report.identity);
const assessment = record(report.assessment);
if (String(identity.run_id || "") !== RUN_ID || String(assessment.run_id || "") !== RUN_ID) {
  throw new Error("run identity mismatch");
}
if (String(identity.commit_sha || "").toLowerCase() !== COMMIT_SHA || String(assessment.commit_sha || "").toLowerCase() !== COMMIT_SHA) {
  throw new Error("commit identity mismatch");
}

const candidateSummary = record(assessment.review_candidate_summary);
const candidateDisposition = record(assessment.candidate_disposition);
const findingPopulation = record(assessment.finding_population);
const scannerRegister = record(assessment.canonical_scanner_finding_register);
const triage = record(scannerRegister.technical_triage);
const metrics = record(triage.workload_metrics);

zero(candidateSummary, "review_required_total", "review-required candidates");
zero(candidateDisposition, "review_required", "candidate disposition review-required");
zero(assessment, "review_required_candidate_count", "assessment review-required candidates");
zero(triage, "human_review_work_units", "scanner review work units");
zero(metrics, "human_review_work_units", "scanner workload metric");
zero(triage, "technical_triage_pending", "pending technical triage");
zero(findingPopulation, "exact_source_code_finding_count", "exact-source findings");
zero(findingPopulation, "operational_or_context_finding_count", "operational/context findings");
zero(findingPopulation, "canonical_finding_count", "canonical findings");
zero(assessment, "exact_source_finding_count", "assessment exact-source findings");
zero(assessment, "operational_context_finding_count", "assessment operational/context findings");
empty(report, "findings", "top-level findings");
empty(assessment, "review_candidate_register", "review-candidate register");
empty(assessment, "decision_grade_findings_register", "decision-grade register");

const registers = collect(report, "client_finding_remediation_register")
  .map(record)
  .filter((item) => Array.isArray(item.code_findings) && Array.isArray(item.operational_findings));
if (!registers.length) throw new Error("canonical client finding/remediation register absent");
for (const [index, register] of registers.entries()) {
  empty(register, "code_findings", `client code findings ${index + 1}`);
  empty(register, "operational_findings", `client operational findings ${index + 1}`);
  const summary = record(register.summary);
  for (const [key, label] of [
    ["exact_source_code_finding_count", "client exact-source findings"],
    ["operational_or_context_finding_count", "client operational/context findings"],
    ["canonical_finding_count", "client canonical findings"],
  ]) {
    if (key in summary) zero(summary, key, `${label} ${index + 1}`);
  }
}

const artifacts = Array.isArray(report.artifacts) ? report.artifacts.map(record) : [];
const pdf = artifacts.find((item) => String(item.artifact_type || "") === "comprehensive_pdf");
if (!pdf || !/^[0-9a-f]{64}$/i.test(String(pdf.sha256 || ""))) {
  throw new Error("retained PDF digest missing or invalid");
}

console.log(JSON.stringify({
  status: "passed",
  run_id: RUN_ID,
  commit_sha: COMMIT_SHA,
  register_projections_verified: registers.length,
  review_required_candidates: 0,
  scanner_review_work_units: 0,
  exact_source_findings: 0,
  operational_context_findings: 0,
  canonical_findings: 0,
  pdf_sha256: pdf.sha256,
}, null, 2));
