import {createHash} from "node:crypto";
import type {NextRequest} from "next/server";

export const NICO_RUN_ID = "comprun_0094b14ba0691ae027e8e52ffd3a1e58";
export const SARA_COMMIT_SHA = "d63f09d3d5d6e4a53860faec0ea5cb372a37c381";
export const REVIEWER = "Cody Jenkins";
export const REVIEWER_ROLE = "Security reviewer";
export const HELPER_PATH = "/operations/sara-pilot-finalize";

const NICO_PROXY_ORIGIN = "https://app.nicoaudit.com";
const STATUS_PATH = `/assessment/comprehensive-run/${NICO_RUN_ID}`;
const REVIEW_PATH = `${STATUS_PATH}/review`;
const AUTHORIZE_PATH = `${STATUS_PATH}/authorize-delivery`;
const DELIVERY_PATH = `${STATUS_PATH}/approved-delivery-package`;
const REQUEST_TIMEOUT_MS = 240_000;

export type JsonRecord = Record<string, unknown>;

export class PilotActionError extends Error {
  readonly status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.name = "PilotActionError";
    this.status = status;
  }
}

export function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function normalizedKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

function collectMatchingValues(
  value: unknown,
  predicate: (key: string) => boolean,
  depth = 0,
): unknown[] {
  if (depth > 14 || value === null || value === undefined) return [];
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectMatchingValues(item, predicate, depth + 1));
  }
  if (typeof value !== "object") return [];

  const output: unknown[] = [];
  for (const [key, child] of Object.entries(value as JsonRecord)) {
    if (predicate(normalizedKey(key))) output.push(child);
    output.push(...collectMatchingValues(child, predicate, depth + 1));
  }
  return output;
}

function stringValues(
  value: unknown,
  predicate: (key: string) => boolean,
): string[] {
  return collectMatchingValues(value, predicate)
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function finiteNumberValues(value: unknown, key: string): number[] {
  return collectMatchingValues(value, (candidate) => candidate === key)
    .map((item) => typeof item === "number" ? item : Number(item))
    .filter((item) => Number.isFinite(item));
}

function booleanValues(value: unknown, key: string): boolean[] {
  return collectMatchingValues(value, (candidate) => candidate === key)
    .filter((item): item is boolean => typeof item === "boolean");
}

function artifactIdentity(payload: JsonRecord): JsonRecord {
  return asRecord(payload.review_artifact_identity);
}

function pdfDigestFromIdentity(identity: JsonRecord): string {
  return String(
    asRecord(asRecord(identity.artifact_digests).pdf).sha256 || "",
  ).trim().toLowerCase();
}

export type ExactRunEvidence = {
  identity: JsonRecord;
  pdfSha256: string;
};

export function assertExactRun(payload: JsonRecord): ExactRunEvidence {
  const runIds = stringValues(
    payload,
    (key) => key === "run_id" || key === "comprehensive_run_id",
  );
  if (!runIds.includes(NICO_RUN_ID)) {
    throw new PilotActionError("The server response was not bound to the retained SARA Comprehensive run.", 409);
  }

  const commitShas = stringValues(
    payload,
    (key) => key.includes("sha") && (key.includes("commit") || key.includes("revision")),
  ).map((item) => item.toLowerCase());
  if (!commitShas.includes(SARA_COMMIT_SHA)) {
    throw new PilotActionError("The retained run no longer resolves to the authorized immutable SARA commit.", 409);
  }

  const identity = artifactIdentity(payload);
  if (!Object.keys(identity).length) {
    throw new PilotActionError("NICO did not return the exact review artifact identity. Approval remains blocked.", 409);
  }

  const pdfSha256 = pdfDigestFromIdentity(identity);
  if (!/^[0-9a-f]{64}$/.test(pdfSha256)) {
    throw new PilotActionError("NICO did not return a valid SHA-256 identity for the exact PDF.", 409);
  }

  const unresolved = finiteNumberValues(payload, "total_unresolved_human_review_work_units");
  if (!unresolved.length || unresolved.some((count) => count !== 0)) {
    throw new PilotActionError("The combined human-review workload is absent or not zero. Approval remains blocked.", 409);
  }

  const operatorAttention = booleanValues(payload, "operator_attention_required");
  if (operatorAttention.some(Boolean)) {
    throw new PilotActionError("NICO still reports unresolved operator attention. Approval remains blocked.", 409);
  }

  return {identity, pdfSha256};
}

function acceptedEdition(payload: JsonRecord): JsonRecord {
  return asRecord(payload.accepted_edition || payload.review_decision);
}

function reviewCertificate(payload: JsonRecord): JsonRecord {
  const edition = acceptedEdition(payload);
  return asRecord(edition.review || payload.review);
}

export function approvalRecorded(payload: JsonRecord): boolean {
  const approval = asRecord(payload.approval);
  const certificate = reviewCertificate(payload);
  const statuses = [
    payload.review_status,
    payload.status,
    approval.status,
    certificate.decision,
  ].map((item) => String(item || "").trim().toLowerCase());
  return statuses.includes("approved") || payload.human_review_completed === true;
}

export function deliveryAllowed(payload: JsonRecord): boolean {
  const acceptance = asRecord(payload.acceptance);
  const approvedDelivery = asRecord(
    payload.approved_delivery
      || asRecord(payload.review).approved_delivery
      || acceptance.approved_delivery,
  );
  const approvedPackage = asRecord(payload.approved_delivery_package);
  return payload.client_delivery_allowed === true
    || acceptance.client_delivery_allowed === true
    || approvedDelivery.client_delivery_allowed === true
    || approvedPackage.client_delivery_allowed === true;
}

function requestHeaders(token: string, json: boolean): Headers {
  const headers = new Headers({
    Accept: "application/json",
    "X-NICO-Admin-Token": token,
  });
  if (json) headers.set("Content-Type", "application/json");
  return headers;
}

async function upstreamFailure(response: Response): Promise<PilotActionError> {
  const raw = await response.text().catch(() => "");
  let message = "NICO rejected or could not complete the protected request.";
  try {
    const payload = JSON.parse(raw) as JsonRecord;
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) message = detail.trim();
    if (detail && typeof detail === "object") {
      const detailRecord = asRecord(detail);
      const candidate = detailRecord.message || detailRecord.reason || detailRecord.code;
      if (typeof candidate === "string" && candidate.trim()) message = candidate.trim();
    }
    const candidate = payload.message || payload.error;
    if (typeof candidate === "string" && candidate.trim()) message = candidate.trim();
  } catch {
    if (raw.trim() && raw.length < 500) message = raw.trim();
  }
  if (response.status === 403) {
    message = "The NICO operator password was rejected. Confirm the deployed Railway NICO_ADMIN_TOKEN value.";
  }
  return new PilotActionError(`${message} (HTTP ${response.status})`, response.status || 502);
}

async function nicoRequest(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  for (const [name, value] of requestHeaders(token, Boolean(init.body)).entries()) {
    if (!headers.has(name)) headers.set(name, value);
  }
  return fetch(`${NICO_PROXY_ORIGIN}/api/nico${path}`, {
    ...init,
    headers,
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
}

export async function statusPayload(token: string): Promise<JsonRecord> {
  const response = await nicoRequest(STATUS_PATH, token, {method: "GET"});
  if (!response.ok) throw await upstreamFailure(response);
  try {
    return asRecord(await response.json());
  } catch {
    throw new PilotActionError("NICO returned an invalid status payload.", 502);
  }
}

export async function approveExactReport(
  token: string,
  identity: JsonRecord,
): Promise<JsonRecord> {
  const response = await nicoRequest(REVIEW_PATH, token, {
    method: "POST",
    body: JSON.stringify({
      review_authorized: true,
      authorization_confirmed: true,
      reviewer: REVIEWER,
      reviewer_role: REVIEWER_ROLE,
      decision: "approved",
      decision_reason: "Owner-controlled SARA pilot: the authorized reviewer confirmed the exact immutable report, scorecard, disclosed evidence limitations, artifact identity, zero unresolved technical-review workload, and delivery boundary.",
      expected_artifact_identity: identity,
    }),
  });
  if (!response.ok) throw await upstreamFailure(response);
  try {
    return asRecord(await response.json());
  } catch {
    throw new PilotActionError("NICO returned an invalid approval payload.", 502);
  }
}

export async function authorizeExactDelivery(
  token: string,
  identity: JsonRecord,
): Promise<JsonRecord> {
  const response = await nicoRequest(AUTHORIZE_PATH, token, {
    method: "POST",
    body: JSON.stringify({
      delivery_authorized: true,
      authorization_confirmed: true,
      authorizer: REVIEWER,
      authorizer_role: REVIEWER_ROLE,
      authorization_reason: "The authorized reviewer reviewed the downloaded APPROVED FINAL PDF and explicitly authorized client delivery of that exact edition and its immutable certified package.",
      expected_artifact_identity: identity,
    }),
  });
  if (!response.ok) throw await upstreamFailure(response);
  try {
    return asRecord(await response.json());
  } catch {
    throw new PilotActionError("NICO returned an invalid delivery-authorization payload.", 502);
  }
}

function safeFilename(value: unknown, fallback: string): string {
  const normalized = String(value || "")
    .replace(/[\r\n]/g, "")
    .replace(/[\\/:*?"<>|]/g, "-")
    .trim();
  return normalized || fallback;
}

function expectedApprovedPdfDigest(payload: JsonRecord): string {
  const currentIdentity = artifactIdentity(payload);
  const edition = acceptedEdition(payload);
  return String(
    asRecord(asRecord(currentIdentity.artifact_digests).pdf).sha256
      || asRecord(asRecord(edition.artifact_digests).pdf).sha256
      || "",
  ).trim().toLowerCase();
}

export function approvedPdf(payload: JsonRecord): {bytes: Uint8Array; filename: string; sha256: string} {
  const reports = asRecord(payload.reports);
  const encoded = String(reports.pdf_base64 || "");
  if (!encoded) {
    throw new PilotActionError("The approved response did not contain the exact final PDF.", 502);
  }
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const buffer = Buffer.from(clean, "base64");
  if (buffer.length < 4 || buffer.subarray(0, 4).toString("ascii") !== "%PDF") {
    throw new PilotActionError("The approved PDF failed its file-signature check.", 502);
  }
  const sha256 = createHash("sha256").update(buffer).digest("hex");
  const expected = expectedApprovedPdfDigest(payload);
  if (!/^[0-9a-f]{64}$/.test(expected) || sha256 !== expected) {
    throw new PilotActionError("The approved PDF did not match NICO's exact SHA-256 artifact identity.", 502);
  }
  return {
    bytes: new Uint8Array(buffer),
    filename: safeFilename(
      reports.pdf_filename,
      `nico-comprehensive-${NICO_RUN_ID}-APPROVED-FINAL.pdf`,
    ),
    sha256,
  };
}

export async function approvedDeliveryPackage(
  token: string,
): Promise<{bytes: Uint8Array; filename: string; sha256: string}> {
  const response = await nicoRequest(DELIVERY_PATH, token, {
    method: "GET",
    headers: {Accept: "application/zip"},
  });
  if (!response.ok) throw await upstreamFailure(response);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length < 2 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
    throw new PilotActionError("The approved delivery package failed its ZIP signature check.", 502);
  }
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const expected = String(response.headers.get("x-nico-delivery-package-sha256") || "")
    .trim()
    .toLowerCase();
  if (expected && (!/^[0-9a-f]{64}$/.test(expected) || expected !== sha256)) {
    throw new PilotActionError("The delivery package did not match NICO's certified SHA-256 digest.", 502);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const candidate = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    || disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]
    || "";
  let decoded = candidate;
  try { decoded = decodeURIComponent(candidate); } catch { /* Keep original. */ }
  return {
    bytes,
    filename: safeFilename(decoded, `nico-sara-pilot-${NICO_RUN_ID}-APPROVED.zip`),
    sha256,
  };
}

export async function operatorTokenFromForm(
  request: NextRequest,
  confirmationName: string,
): Promise<string> {
  const form = await request.formData();
  const token = String(form.get("operator_password") || "").trim();
  if (!token) throw new PilotActionError("Enter the deployed NICO operator password.");
  if (String(form.get(confirmationName) || "") !== "yes") {
    throw new PilotActionError("The required exact-artifact review confirmation was not checked.");
  }
  return token;
}

export function downloadResponse(
  bytes: Uint8Array,
  contentType: string,
  filename: string,
  sha256: string,
): Response {
  return new Response(bytes, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${safeFilename(filename, "nico-artifact")}"`,
      "Content-Length": String(bytes.byteLength),
      "Cache-Control": "no-store, max-age=0",
      Pragma: "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "X-NICO-Pilot-Artifact-SHA256": sha256,
    },
  });
}

export function errorResponse(caught: unknown): Response {
  const error = caught instanceof PilotActionError
    ? caught
    : new PilotActionError(
      caught instanceof Error ? caught.message : "The protected NICO action failed closed.",
      500,
    );
  const message = [
    "NICO SARA pilot action stopped safely.",
    "",
    error.message,
    "",
    `Return to ${HELPER_PATH}. No operator password was stored.`,
  ].join("\n");
  return new Response(message, {
    status: error.status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      Pragma: "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    },
  });
}
