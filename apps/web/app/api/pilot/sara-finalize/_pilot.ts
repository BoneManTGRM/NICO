import {createHash} from "node:crypto";
import type {NextRequest} from "next/server";

export const NICO_RUN_ID = "comprun_2ba62f37f4ab4b7988c609f27398c63e";
export const SARA_COMMIT_SHA = "d63f09d3d5d6e4a53860faec0ea5cb372a37c381";
export const SARA_REPOSITORY = "BoneManTGRM/SARA";
export const CUSTOMER_ID = "boneman-sara-client";
export const PROJECT_ID = "sara-controlled-pilot-001";
export const CLIENT_NAME = "SARA / BoneManTGRM";
export const PROJECT_NAME = "SARA — First Controlled Production Pilot";
export const PRIMARY_TECHNICAL_CONTACT = "Cody Ryan Jenkins (GitHub: BoneManTGRM)";
export const ACCESS_METHOD = "Authorized public GitHub repository using anonymous read-only access; no write permissions or provider credential supplied.";
export const AUTHORIZED_SCOPE = `Read-only technical assessment of ${SARA_REPOSITORY} at exact commit ${SARA_COMMIT_SHA} only. No writes, deployments, account changes, outreach, or access outside this repository and SHA.`;
export const ENGAGEMENT_METADATA_SHA256 = "c486348bd6b69e3406198c66383a635f3a3c2455b47ed77efb8cb17308f8af58";
export const REVIEWER = "Cody Ryan Jenkins";
export const REVIEWER_ROLE = "Owner and authorized reviewer";
export const HELPER_PATH = "/operations/sara-pilot-finalize";

const ORIGIN = "https://app.nicoaudit.com";
const RUN_PATH = `/assessment/comprehensive-run/${NICO_RUN_ID}`;
const TIMEOUT_MS = 240_000;

export type JsonRecord = Record<string, unknown>;

export class PilotActionError extends Error {
  constructor(message: string, readonly status = 400) {
    super(message);
    this.name = "PilotActionError";
  }
}

export function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function artifactIdentity(payload: JsonRecord): JsonRecord {
  return asRecord(payload.review_artifact_identity);
}

function acceptedEdition(payload: JsonRecord): JsonRecord {
  return asRecord(payload.accepted_edition || payload.review_decision);
}

function reviewCertificate(payload: JsonRecord): JsonRecord {
  const edition = acceptedEdition(payload);
  return asRecord(edition.review || payload.review);
}

export function approvalRecorded(payload: JsonRecord): boolean {
  const statuses = [
    payload.review_status,
    payload.status,
    asRecord(payload.approval).status,
    reviewCertificate(payload).decision,
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

async function failure(response: Response): Promise<PilotActionError> {
  const raw = await response.text().catch(() => "");
  let message = "NICO rejected or could not complete the protected request.";
  try {
    const payload = asRecord(JSON.parse(raw));
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) message = detail.trim();
    if (detail && typeof detail === "object") {
      const record = asRecord(detail);
      const candidate = record.message || record.reason || record.code;
      if (typeof candidate === "string" && candidate.trim()) message = candidate.trim();
    }
    const candidate = payload.message || payload.error;
    if (typeof candidate === "string" && candidate.trim()) message = candidate.trim();
  } catch {
    if (raw.trim() && raw.length < 500) message = raw.trim();
  }
  if (response.status === 401 || response.status === 403) {
    message = "The NICO operator password was rejected. Confirm the deployed Railway NICO_ADMIN_TOKEN value.";
  }
  return new PilotActionError(`${message} (HTTP ${response.status})`, response.status || 502);
}

async function request(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-NICO-Admin-Token", token);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(`${ORIGIN}/api/nico${path}`, {
    ...init,
    headers,
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
}

async function jsonRequest(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<JsonRecord> {
  const response = await request(path, token, init);
  if (!response.ok) throw await failure(response);
  try {
    return asRecord(await response.json());
  } catch {
    throw new PilotActionError("NICO returned an invalid JSON payload.", 502);
  }
}

export function statusPayload(token: string): Promise<JsonRecord> {
  return jsonRequest(RUN_PATH, token, {method: "GET"});
}

export function approveExactReport(token: string, identity: JsonRecord): Promise<JsonRecord> {
  return jsonRequest(`${RUN_PATH}/review`, token, {
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
}

export function authorizeExactDelivery(token: string, identity: JsonRecord): Promise<JsonRecord> {
  return jsonRequest(`${RUN_PATH}/authorize-delivery`, token, {
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
}

function safeFilename(value: unknown, fallback: string): string {
  const filename = String(value || "")
    .replace(/[\r\n]/g, "")
    .replace(/[\\/:*?"<>|]/g, "-")
    .trim();
  return filename || fallback;
}

function approvedDigest(payload: JsonRecord): string {
  const edition = acceptedEdition(payload);
  return String(
    asRecord(asRecord(artifactIdentity(payload).artifact_digests).pdf).sha256
      || asRecord(asRecord(edition.artifact_digests).pdf).sha256
      || "",
  ).trim().toLowerCase();
}

export function approvedPdf(payload: JsonRecord): {
  bytes: Uint8Array;
  filename: string;
  sha256: string;
} {
  const reports = asRecord(payload.reports);
  const encoded = String(reports.pdf_base64 || "");
  if (!encoded) {
    throw new PilotActionError("The approved response did not contain the final PDF.", 502);
  }
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const buffer = Buffer.from(clean, "base64");
  if (buffer.length < 4 || buffer.subarray(0, 4).toString("ascii") !== "%PDF") {
    throw new PilotActionError("The approved PDF failed its file-signature check.", 502);
  }
  const sha256 = createHash("sha256").update(buffer).digest("hex");
  const expected = approvedDigest(payload);
  if (!/^[0-9a-f]{64}$/.test(expected) || expected !== sha256) {
    throw new PilotActionError("The approved PDF did not match NICO's exact SHA-256 identity.", 502);
  }
  return {
    bytes: Uint8Array.from(buffer),
    filename: safeFilename(
      reports.pdf_filename,
      `nico-comprehensive-${NICO_RUN_ID}-APPROVED-FINAL.pdf`,
    ),
    sha256,
  };
}

export async function approvedDeliveryPackage(token: string): Promise<{
  bytes: Uint8Array;
  filename: string;
  sha256: string;
}> {
  const response = await request(`${RUN_PATH}/approved-delivery-package`, token, {
    method: "GET",
    headers: {Accept: "application/zip"},
  });
  if (!response.ok) throw await failure(response);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length < 2 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
    throw new PilotActionError("The approved delivery package failed its ZIP signature check.", 502);
  }
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const expected = String(
    response.headers.get("x-nico-delivery-package-sha256")
      || response.headers.get("x-nico-package-sha256")
      || "",
  ).trim().toLowerCase();
  if (expected && (!/^[0-9a-f]{64}$/.test(expected) || expected !== sha256)) {
    throw new PilotActionError("The delivery package did not match NICO's certified SHA-256 digest.", 502);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const rawName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    || disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]
    || "";
  let decodedName = rawName;
  try {
    decodedName = decodeURIComponent(rawName);
  } catch {
    decodedName = rawName;
  }
  return {
    bytes,
    filename: safeFilename(decodedName, `nico-sara-pilot-${NICO_RUN_ID}-APPROVED.zip`),
    sha256,
  };
}

export async function operatorTokenFromForm(
  request: NextRequest,
  confirmation: string,
): Promise<string> {
  const form = await request.formData();
  const token = String(form.get("operator_password") || "").trim();
  if (!token) throw new PilotActionError("Enter the deployed NICO operator password.");
  if (String(form.get(confirmation) || "") !== "yes") {
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
  const body = new Uint8Array(bytes.byteLength);
  body.set(bytes);
  return new Response(body.buffer, {
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
      caught instanceof Error ? caught.message : "The protected action failed closed.",
      500,
    );
  return new Response([
    "NICO SARA pilot action stopped safely.",
    "",
    error.message,
    "",
    `Return to ${HELPER_PATH}. No operator password was stored.`,
  ].join("\n"), {
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
