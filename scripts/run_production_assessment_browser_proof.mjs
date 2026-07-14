import {createHash} from "node:crypto";
import {mkdir, readFile, readdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {chromium} from "playwright";

const FRONTEND_URL = String(process.env.FRONTEND_URL || "https://app.nicoaudit.com").replace(/\/$/, "");
const EXPECTED_COMMIT = String(process.env.EXPECTED_COMMIT || "").trim().toLowerCase();
const AUTHORIZED_REPOSITORY = String(process.env.AUTHORIZED_REPOSITORY || "BoneManTGRM/NICO").trim();
const AUTHORIZATION_SCOPE = String(
  process.env.AUTHORIZATION_SCOPE
    || "Owner-authorized defensive production assessment of BoneManTGRM/NICO for Phase 1 evidence only.",
).trim();
const OUTPUT_DIR = path.resolve(process.env.PROOF_OUTPUT_DIR || "artifacts/production-assessment-proof");
const FULL_SHA = /^[0-9a-f]{40}$/;
const TIERS = ["express", "mid", "full"];
const START_PATHS = {
  express: "/assessment/github",
  mid: "/assessment/mid-run",
  full: "/assessment/full-run",
};
const FORBIDDEN_MUTATION_PATHS = [
  "/approval/request",
  "/approved",
  "/delivery/access",
  "/delivery/redeem",
  "/delivery/acknowledg",
];

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

function bounded(value, limit = 320) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, limit - 3)}...`;
}

function canonicalAssessmentPath(rawUrl) {
  const pathname = new URL(rawUrl).pathname;
  return pathname.startsWith("/api/nico/") ? pathname.slice("/api/nico".length) : pathname;
}

function sanitizeProgress(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 40).map((item) => ({
    step: bounded(item?.step, 100),
    status: bounded(item?.status, 40),
    message: bounded(item?.message, 260),
  }));
}

function sanitizeAssessmentPayload(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const document = source.assessment && typeof source.assessment === "object" ? source.assessment : source;
  const reports = source.reports && typeof source.reports === "object" ? source.reports : {};
  const midReport = source.mid_report && typeof source.mid_report === "object" ? source.mid_report : {};
  const approvalRequest = source.approval_request && typeof source.approval_request === "object" ? source.approval_request : {};
  const approval = source.approval && typeof source.approval === "object" ? source.approval : {};
  const scanner = source.scanner && typeof source.scanner === "object" ? source.scanner : {};
  const scannerEvidence = source.scanner_evidence && typeof source.scanner_evidence === "object" ? source.scanner_evidence : {};
  const snapshot = source.repository_snapshot && typeof source.repository_snapshot === "object" ? source.repository_snapshot : {};
  const repositoryEvidence = source.repository_evidence && typeof source.repository_evidence === "object" ? source.repository_evidence : {};
  const maturity = document.maturity_signal && typeof document.maturity_signal === "object" ? document.maturity_signal : {};
  const persistence = source.persistence && typeof source.persistence === "object" ? source.persistence : {};

  return {
    status: bounded(source.status, 50),
    run_id: bounded(source.run_id, 140),
    repository: bounded(source.repository, 180),
    customer_id: bounded(source.customer_id, 120),
    project_id: bounded(source.project_id, 120),
    generated_at: bounded(source.generated_at, 80),
    repository_snapshot: {
      snapshot_id: bounded(snapshot.snapshot_id, 140),
      commit_sha: bounded(snapshot.commit_sha || repositoryEvidence.snapshot_commit_sha, 80),
      evidence_id: bounded(repositoryEvidence.evidence_id, 140),
      status: bounded(repositoryEvidence.status, 50),
    },
    scanner: {
      scan_id: bounded(scanner.scan_id || scannerEvidence.scan_id, 140),
      status: bounded(scanner.status || scannerEvidence.scanner_status || scannerEvidence.status, 50),
    },
    report: {
      has_markdown: Boolean(reports.markdown),
      has_pdf: Boolean(reports.pdf_base64),
      report_id: bounded(reports.report_id || midReport.report_id, 140),
      report_status: bounded(source.report_generation_status || midReport.status, 50),
      pdf_sha256: bounded(reports.pdf_sha256 || midReport.pdf_sha256, 80),
      pdf_error: bounded(reports.pdf_error || source.report_generation_error, 260),
    },
    review: {
      approval_id: bounded(approvalRequest.approval_id || approval.approval_id, 140),
      status: bounded(approvalRequest.status || source.approval_request_status || approval.status, 50),
      report_id: bounded(approvalRequest.draft_report_id || approval.report_id, 140),
    },
    maturity: {
      level: bounded(maturity.level, 50),
      score: Number.isFinite(Number(maturity.score)) ? Number(maturity.score) : null,
      evidence_readiness_score: Number.isFinite(Number(maturity.evidence_readiness_score))
        ? Number(maturity.evidence_readiness_score)
        : null,
    },
    persistence: {
      recorded: persistence.recorded === true,
      durable: persistence.durable === true,
      adapter: bounded(persistence.adapter, 80),
    },
    human_review_required: document.human_review_required === true || source.human_review_required === true,
    client_ready: document.client_ready === true || source.client_ready === true,
    unavailable_note_count: Array.isArray(document.unavailable_data_notes) ? document.unavailable_data_notes.length : 0,
    progress: sanitizeProgress(source.progress),
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(30_000),
    ...options,
    headers: {Accept: "application/json", ...(options.headers || {})},
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error(`${url} returned invalid JSON (${response.status}).`);
  }
  return {response, payload};
}

async function waitForExactDeployment() {
  requireCondition(FULL_SHA.test(EXPECTED_COMMIT), "EXPECTED_COMMIT must be an exact 40-character commit SHA.");
  requireCondition(AUTHORIZED_REPOSITORY === "BoneManTGRM/NICO", "This proof is bounded to the explicitly authorized BoneManTGRM/NICO repository.");
  requireCondition(AUTHORIZATION_SCOPE.toLowerCase().includes("owner-authorized"), "The production proof requires an explicit owner-authorized scope.");

  let lastObservation = {};
  for (let attempt = 1; attempt <= 90; attempt += 1) {
    try {
      const frontendResult = await fetchJson(`${FRONTEND_URL}/api/deployment`);
      const frontend = frontendResult.payload;
      const backendOrigin = String(frontend.backend_origin || "").replace(/\/$/, "");
      const frontendCommit = String(frontend.frontend_commit || "").toLowerCase();
      let backendHealth = null;
      let readiness = null;
      let backendCommit = "unavailable";

      if (backendOrigin.startsWith("https://")) {
        const healthResponse = await fetch(`${backendOrigin}/health`, {
          cache: "no-store",
          redirect: "error",
          signal: AbortSignal.timeout(30_000),
          headers: {Accept: "application/json"},
        });
        backendHealth = {status: healthResponse.status, ok: healthResponse.ok};

        const readinessResult = await fetchJson(`${backendOrigin}/operations/readiness`);
        readiness = readinessResult.payload;
        backendCommit = String(
          readiness?.deployment?.deployed_commit
            || readiness?.deployment?.commit_sha
            || readiness?.deployed_commit
            || "unavailable",
        ).toLowerCase();
      }

      lastObservation = {
        attempt,
        frontend_status: frontendResult.response.status,
        frontend_commit: frontendCommit,
        backend_origin: backendOrigin || "unavailable",
        backend_health: backendHealth,
        backend_commit: backendCommit,
        backend_readiness_status: bounded(readiness?.status, 50),
        backend_operational_ready: readiness?.operational_ready === true,
      };

      if (
        frontendResult.response.ok
        && frontendCommit === EXPECTED_COMMIT
        && backendHealth?.ok
        && backendCommit === EXPECTED_COMMIT
      ) {
        return lastObservation;
      }
    } catch (error) {
      lastObservation = {attempt, error: bounded(error instanceof Error ? error.message : error, 500)};
    }
    await new Promise((resolve) => setTimeout(resolve, 10_000));
  }
  throw new Error(`Exact deployed frontend/backend release alignment was not observed: ${JSON.stringify(lastObservation)}`);
}

function terminalStateFromBody(tier, text) {
  if (text.includes("Run failed or blocked")) return "failed";
  if (text.includes("Continuation timed out")) return "timed_out";
  if (tier === "express" && text.includes("Express completed and returned its evidence-bound draft report.")) return "complete";
  if (tier !== "express" && text.includes("completed its automated stages and stopped at the required human-review gate.")) return "review_required";
  return "";
}

function validateTierResult(tier, responseRecord, terminalText, startCount) {
  requireCondition(startCount === 1, `${tier} issued ${startCount} start requests; exactly one is required.`);
  requireCondition(responseRecord, `${tier} did not return a captured assessment response.`);
  requireCondition(responseRecord.http_status >= 200 && responseRecord.http_status < 300, `${tier} returned HTTP ${responseRecord.http_status}.`);
  const result = responseRecord.payload;
  requireCondition(result.repository === AUTHORIZED_REPOSITORY, `${tier} response repository did not match the authorized target.`);
  requireCondition(result.human_review_required === true, `${tier} did not preserve the human-review requirement.`);
  requireCondition(result.client_ready === false, `${tier} incorrectly reported the draft as client-ready.`);
  requireCondition(!terminalText.includes("Run failed or blocked"), `${tier} reached a failed or blocked browser state.`);
  requireCondition(!terminalText.includes("Continuation timed out"), `${tier} reached the bounded browser continuation timeout.`);
  requireCondition(result.report.has_markdown === true, `${tier} did not return a bounded draft Markdown report.`);

  if (tier === "express") {
    requireCondition(result.report.has_pdf === true || Boolean(result.report.pdf_sha256), "Express did not return a PDF artifact or retained PDF hash.");
    return;
  }

  requireCondition(Boolean(result.run_id), `${tier} did not preserve an exact run ID.`);
  requireCondition(Boolean(result.repository_snapshot.commit_sha), `${tier} did not preserve an exact repository snapshot commit.`);
  requireCondition(Boolean(result.scanner.scan_id), `${tier} did not preserve a scanner run identity.`);
  requireCondition(Boolean(result.report.report_id), `${tier} did not preserve a report identity.`);
  requireCondition(Boolean(result.review.approval_id), `${tier} did not preserve a human-review request identity.`);
  requireCondition(!["approved", "accepted", "delivered"].includes(result.review.status.toLowerCase()), `${tier} crossed the human-review boundary automatically.`);
  requireCondition(result.persistence.recorded === true, `${tier} exact-run state was not recorded.`);
  requireCondition(result.persistence.durable === true, `${tier} exact-run state was not proven durable in production.`);
}

async function sha256File(filePath) {
  const bytes = await readFile(filePath);
  return createHash("sha256").update(bytes).digest("hex");
}

async function writeEvidence(summary) {
  await mkdir(OUTPUT_DIR, {recursive: true});
  const files = await readdir(OUTPUT_DIR).catch(() => []);
  const screenshots = [];
  for (const file of files.filter((name) => name.endsWith(".png")).sort()) {
    screenshots.push({file, sha256: await sha256File(path.join(OUTPUT_DIR, file))});
  }
  summary.screenshots = screenshots;
  await writeFile(path.join(OUTPUT_DIR, "summary.json"), `${JSON.stringify(summary, null, 2)}\n`, "utf8");

  const lines = [
    "# NICO production assessment proof",
    "",
    `- Status: **${summary.status}**`,
    `- Expected commit: \`${summary.expected_commit}\``,
    `- Frontend: ${summary.frontend_url}`,
    `- Backend: ${summary.release?.backend_origin || "unavailable"}`,
    `- Authorized repository: \`${summary.authorized_repository}\``,
    `- Started: ${summary.started_at}`,
    `- Finished: ${summary.finished_at}`,
    "- Human review remained required; approval and delivery mutations were prohibited.",
    "",
    "## Tier results",
    "",
  ];
  for (const tier of TIERS) {
    const item = summary.tiers[tier] || {};
    lines.push(`### ${tier[0].toUpperCase()}${tier.slice(1)}`);
    lines.push("");
    lines.push(`- Browser terminal state: \`${item.terminal_state || "not reached"}\``);
    lines.push(`- Start requests: ${item.start_request_count ?? 0}`);
    lines.push(`- Run ID: \`${item.response?.payload?.run_id || "not returned"}\``);
    lines.push(`- Snapshot commit: \`${item.response?.payload?.repository_snapshot?.commit_sha || "not returned"}\``);
    lines.push(`- Scanner ID: \`${item.response?.payload?.scanner?.scan_id || "not returned"}\``);
    lines.push(`- Report ID: \`${item.response?.payload?.report?.report_id || "not returned"}\``);
    lines.push(`- Review request ID: \`${item.response?.payload?.review?.approval_id || "not returned"}\``);
    lines.push(`- Human review required: ${item.response?.payload?.human_review_required === true}`);
    lines.push(`- Client ready: ${item.response?.payload?.client_ready === true}`);
    lines.push("");
  }
  if (summary.failure) {
    lines.push("## Failure");
    lines.push("");
    lines.push(`- ${bounded(summary.failure.message, 1000)}`);
    lines.push("");
  }
  lines.push("## Truth boundary");
  lines.push("");
  lines.push("This artifact records a defensive production smoke assessment only. It does not approve findings, certify security, authorize production changes, or permit client delivery.");
  lines.push("");
  await writeFile(path.join(OUTPUT_DIR, "summary.md"), `${lines.join("\n")}\n`, "utf8");
}

const summary = {
  artifact_schema: "nico.production_assessment_proof.v1",
  status: "running",
  started_at: new Date().toISOString(),
  finished_at: null,
  expected_commit: EXPECTED_COMMIT,
  frontend_url: FRONTEND_URL,
  authorized_repository: AUTHORIZED_REPOSITORY,
  authorization_scope: AUTHORIZATION_SCOPE,
  human_review_required: true,
  client_delivery_allowed: false,
  automatic_production_changes_allowed: false,
  release: null,
  tiers: {},
  forbidden_mutation_requests: [],
  browser_console_errors: [],
};

let browser = null;
let page = null;
let exitCode = 0;

try {
  await mkdir(OUTPUT_DIR, {recursive: true});
  summary.release = await waitForExactDeployment();

  browser = await chromium.launch({headless: true});
  const context = await browser.newContext({
    viewport: {width: 430, height: 932},
    isMobile: true,
    deviceScaleFactor: 1,
    locale: "en-US",
  });
  page = await context.newPage();
  const startCounts = {express: 0, mid: 0, full: 0};
  const capturedResponses = [];
  const responseTasks = [];

  page.on("console", (message) => {
    if (message.type() === "error") summary.browser_console_errors.push(bounded(message.text(), 500));
  });
  page.on("pageerror", (error) => summary.browser_console_errors.push(bounded(error.message, 500)));
  page.on("request", (request) => {
    const assessmentPath = canonicalAssessmentPath(request.url());
    if (request.method() === "POST") {
      for (const tier of TIERS) {
        if (assessmentPath === START_PATHS[tier]) startCounts[tier] += 1;
      }
      if (FORBIDDEN_MUTATION_PATHS.some((fragment) => assessmentPath.includes(fragment))) {
        summary.forbidden_mutation_requests.push({method: request.method(), path: assessmentPath});
      }
    }
  });
  page.on("response", (response) => {
    const task = (async () => {
      const assessmentPath = canonicalAssessmentPath(response.url());
      if (!assessmentPath.startsWith("/assessment/")) return;
      if (!["POST", "GET"].includes(response.request().method())) return;
      let payload = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }
      const tier = assessmentPath.includes("/mid-run")
        ? "mid"
        : assessmentPath.includes("/full-run")
          ? "full"
          : assessmentPath === "/assessment/github"
            ? "express"
            : "unknown";
      capturedResponses.push({
        tier,
        path: assessmentPath,
        method: response.request().method(),
        http_status: response.status(),
        payload: sanitizeAssessmentPayload(payload),
      });
    })();
    responseTasks.push(task);
  });

  for (const tier of TIERS) {
    const clientName = "NICO Production Proof";
    const projectName = `Phase 1 ${tier} ${EXPECTED_COMMIT.slice(0, 8)}`;
    const startCountBefore = startCounts[tier];
    const responseIndexBefore = capturedResponses.length;

    await page.goto(`${FRONTEND_URL}/assessment?tier=${tier}#assessment`, {waitUntil: "networkidle", timeout: 120_000});
    await page.getByLabel("Repository owner/name or GitHub URL").fill(AUTHORIZED_REPOSITORY);
    await page.getByLabel("Client name, optional").fill(clientName);
    await page.getByLabel("Project name, optional").fill(projectName);
    await page.getByLabel("I confirm I own this target or have explicit permission to assess it.").check();
    await page.getByRole("button", {name: `Run ${tier[0].toUpperCase()}${tier.slice(1)} assessment`, exact: true}).click();

    const timeout = tier === "express" ? 1_500_000 : 1_200_000;
    const terminalHandle = await page.waitForFunction(
      (selectedTier) => {
        const text = document.body.innerText;
        if (text.includes("Run failed or blocked")) return "failed";
        if (text.includes("Continuation timed out")) return "timed_out";
        if (selectedTier === "express" && text.includes("Express completed and returned its evidence-bound draft report.")) return "complete";
        if (selectedTier !== "express" && text.includes("completed its automated stages and stopped at the required human-review gate.")) return "review_required";
        return "";
      },
      tier,
      {timeout, polling: 1000},
    );
    const terminalState = await terminalHandle.jsonValue();
    const stateSection = page.locator("section").filter({hasText: "AUTOMATED RUN STATE"}).first();
    await stateSection.scrollIntoViewIfNeeded();
    await page.screenshot({path: path.join(OUTPUT_DIR, `${tier}-browser-state.png`), fullPage: false});
    const terminalText = bounded(await stateSection.innerText(), 4000);

    await Promise.allSettled(responseTasks.splice(0));
    const tierResponses = capturedResponses.slice(responseIndexBefore).filter((item) => item.tier === tier);
    const successfulResponses = tierResponses.filter((item) => item.http_status >= 200 && item.http_status < 300);
    const finalResponse = successfulResponses.at(-1) || tierResponses.at(-1) || null;
    const startRequestCount = startCounts[tier] - startCountBefore;

    summary.tiers[tier] = {
      terminal_state: terminalState,
      start_request_count: startRequestCount,
      status_request_count: tierResponses.filter((item) => item.path.includes("/status")).length,
      browser_state_text: terminalText,
      response: finalResponse,
    };

    requireCondition(["complete", "review_required"].includes(terminalState), `${tier} reached terminal state ${terminalState}. ${terminalText}`);
    validateTierResult(tier, finalResponse, terminalText, startRequestCount);
  }

  requireCondition(summary.forbidden_mutation_requests.length === 0, "The browser attempted a forbidden approval or delivery mutation.");
  summary.status = "passed";
} catch (error) {
  exitCode = 1;
  summary.status = "failed";
  summary.failure = {
    name: bounded(error instanceof Error ? error.name : "Error", 100),
    message: bounded(error instanceof Error ? error.message : error, 2000),
  };
  if (page) {
    try {
      await page.screenshot({path: path.join(OUTPUT_DIR, "failure-browser-state.png"), fullPage: false});
    } catch {
      // The bounded JSON/Markdown artifact remains authoritative when screenshot capture is unavailable.
    }
  }
} finally {
  summary.finished_at = new Date().toISOString();
  if (browser) await browser.close().catch(() => {});
  await writeEvidence(summary);
}

process.exitCode = exitCode;
