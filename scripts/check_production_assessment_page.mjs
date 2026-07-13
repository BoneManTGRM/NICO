import {writeFileSync, mkdirSync} from "node:fs";
import {dirname} from "node:path";
import process from "node:process";
import {chromium} from "playwright";

function argumentsMap(argv) {
  const result = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error("invalid_arguments");
    result.set(key.slice(2), value);
  }
  return result;
}

function csvValues(value) {
  return new Set(String(value || "").split(/[\n,]/).map((item) => item.trim().toLowerCase()).filter(Boolean));
}

function validatedOrigin(value, allowedHosts) {
  const parsed = new URL(value);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error("unsafe_frontend_url");
  if (parsed.pathname !== "/" && parsed.pathname !== "") throw new Error("unsafe_frontend_url");
  if (parsed.port && parsed.port !== "443") throw new Error("unsafe_frontend_url");
  if (!allowedHosts.has(parsed.hostname.toLowerCase())) throw new Error("frontend_host_not_allowlisted");
  return `https://${parsed.hostname.toLowerCase()}`;
}

function writeJson(path, payload) {
  mkdirSync(dirname(path), {recursive: true});
  writeFileSync(path, `${JSON.stringify(payload, null, 2)}\n`, {encoding: "utf8"});
}

const args = argumentsMap(process.argv.slice(2));
const output = args.get("output") || "audit-results/production-assessment-browser.json";
const frontendCommit = String(args.get("frontend-commit") || "").toLowerCase();
let browser;
try {
  if (!/^[0-9a-f]{40}$/.test(frontendCommit)) throw new Error("invalid_frontend_commit");
  const allowedHosts = csvValues(process.env.NICO_PRODUCTION_SMOKE_FRONTEND_HOSTS);
  if (!allowedHosts.size) throw new Error("frontend_allowlist_missing");
  const origin = validatedOrigin(args.get("frontend-url") || "", allowedHosts);
  const assessmentPosts = [];
  browser = await chromium.launch({headless: true});
  const page = await browser.newPage();
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.startsWith("/assessment/")) assessmentPosts.push(request.url());
  });
  const navigation = await page.goto(`${origin}/assessment?tier=express`, {waitUntil: "domcontentloaded", timeout: 60000});

  const checks = [];
  const record = (id, passed) => {
    if (!passed) throw new Error(`browser_check_failed_${id}`);
    checks.push({id, passed: true});
  };

  record("production_http_success", Boolean(navigation) && navigation.status() >= 200 && navigation.status() < 400);
  const finalUrl = new URL(page.url());
  record("production_origin_preserved", finalUrl.origin === origin && finalUrl.pathname === "/assessment");
  record("unified_heading", await page.getByRole("heading", {name: "One form. Three assessment depths."}).isVisible());
  record("authorization_warning", await page.getByText("Only assess repositories you own or are explicitly authorized to review.", {exact: false}).isVisible());
  record("three_tier_controls", await page.getByRole("button", {name: "Express", exact: true}).isVisible()
    && await page.getByRole("button", {name: "Mid", exact: true}).isVisible()
    && await page.getByRole("button", {name: "Full", exact: true}).isVisible());

  const authorization = page.getByRole("checkbox", {name: "I confirm I own this target or have explicit permission to assess it."});
  const expressRun = page.getByRole("button", {name: "Run Express assessment"});
  record("authorization_gate_initially_blocks_run", await expressRun.isDisabled());
  await authorization.check();
  record("configured_backend_allows_authorized_run", await expressRun.isEnabled());
  await authorization.uncheck();

  await page.getByRole("button", {name: "Mid", exact: true}).click();
  record("mid_selection", await page.getByRole("button", {name: "Mid", exact: true}).getAttribute("aria-pressed") === "true"
    && await page.getByRole("button", {name: "Run Mid assessment"}).isDisabled());
  await page.getByRole("button", {name: "Full", exact: true}).click();
  record("full_selection", await page.getByRole("button", {name: "Full", exact: true}).getAttribute("aria-pressed") === "true"
    && await page.getByRole("button", {name: "Run Full assessment"}).isDisabled());
  record("no_assessment_posted", assessmentPosts.length === 0);

  writeJson(output, {
    schema_version: 1,
    evidence_kind: "authorized_live_production_browser_check",
    live_claim: true,
    status: "passed",
    frontend_commit: frontendCommit,
    frontend_origin: origin,
    assessment_path: "/assessment",
    no_assessment_started: true,
    checks,
  });
  await browser.close();
  process.exit(0);
} catch (error) {
  if (browser) await browser.close().catch(() => {});
  const code = error instanceof Error ? error.message.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 120) : "browser_check_failed";
  writeJson(output, {
    schema_version: 1,
    evidence_kind: "authorized_live_production_browser_check",
    live_claim: true,
    status: "failed",
    frontend_commit: frontendCommit,
    no_assessment_started: true,
    error: {code},
    checks: [],
  });
  console.error(`Production assessment browser check failed: ${code}`);
  process.exit(1);
}
