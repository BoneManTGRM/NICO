export type Service = "express" | "comprehensive";
export type Decision = "needs_more_evidence" | "rejected";
export type JsonRecord = Record<string, unknown>;

export type ReviewResponse = {
  status?: string;
  service?: Service;
  review_status?: string;
  acceptance_status?: string;
  approval_id?: string;
  client_delivery_allowed?: boolean;
  approval?: JsonRecord;
  review?: JsonRecord;
  acceptance?: JsonRecord;
  approved_delivery?: JsonRecord;
  approvals?: JsonRecord[];
};

export function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

export function approvedDeliveryFrom(value: ReviewResponse | null | undefined): JsonRecord {
  if (!value) return {};
  return asRecord(
    value.approved_delivery
      || asRecord(value.review).approved_delivery
      || asRecord(value.acceptance).approved_delivery,
  );
}

export function approvalIdFrom(value: ReviewResponse | null | undefined): string {
  if (!value) return "";
  const direct = String(value.approval_id || "");
  if (direct) return direct;
  const approval = asRecord(value.approval);
  if (approval.approval_id) return String(approval.approval_id);
  const first = Array.isArray(value.approvals) ? asRecord(value.approvals[0]) : {};
  return String(first.approval_id || "");
}

export function mergeReviewResponses(latest: ReviewResponse, mutation: ReviewResponse): ReviewResponse {
  const mutationDelivery = approvedDeliveryFrom(mutation);
  const latestDelivery = approvedDeliveryFrom(latest);
  const merged: ReviewResponse = {...mutation, ...latest};
  if (Object.keys(mutationDelivery).length) merged.approved_delivery = {...latestDelivery, ...mutationDelivery};
  return merged;
}

export function serviceFromRunId(value: string): Service | null {
  const normalized = value.trim().toLowerCase();
  if (normalized.startsWith("comprun_")) return "comprehensive";
  if (normalized.startsWith("express_run_")) return "express";
  return null;
}

export function compactRunId(value: string): string {
  const normalized = value.trim();
  if (normalized.length <= 34) return normalized;
  return `${normalized.slice(0, 20)}…${normalized.slice(-10)}`;
}

export function humanStatus(value: string): string {
  if (!value) return "Pending review";
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function safeFilename(value: string, fallback: string): string {
  const normalized = value.replace(/[\r\n]/g, "").replace(/[\\/:*?\"<>|]/g, "-").trim();
  return normalized || fallback;
}

export function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  const candidate = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    || disposition.match(/filename="([^"]+)"/i)?.[1]
    || disposition.match(/filename=([^;]+)/i)?.[1]
    || "";
  try {
    return safeFilename(decodeURIComponent(candidate), fallback);
  } catch {
    return safeFilename(candidate, fallback);
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadBase64Pdf(encoded: string, filename: string): void {
  const clean = encoded.includes(",") ? encoded.slice(encoded.indexOf(",") + 1) : encoded;
  const binary = window.atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
    throw new Error("Approved PDF signature is invalid.");
  }
  downloadBlob(new Blob([bytes], {type: "application/pdf"}), filename);
}

export async function responseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => ({})) as {
    detail?: string | {message?: string}; message?: string; error?: string;
  };
  const detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
  return new Error(detail || payload.message || payload.error || `${fallback} (${response.status}).`);
}
