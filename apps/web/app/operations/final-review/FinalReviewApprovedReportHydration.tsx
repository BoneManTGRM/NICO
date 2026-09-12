"use client";

import {useEffect} from "react";

const REVIEW_DECISION_PATH = /^\/api\/nico\/assessment\/comprehensive-run\/[^/]+(?:\/localized-editions\/[^/]+)?\/review$/;
const APPROVED_REPORT_RETRY_DELAYS_MS = [0, 150, 350, 700] as const;

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return String(init.method).toUpperCase();
  if (input instanceof Request) return String(input.method || "GET").toUpperCase();
  return "GET";
}

function reviewDecisionUrl(input: RequestInfo | URL, init?: RequestInit): URL | null {
  if (requestMethod(input, init) !== "POST") return null;
  try {
    const url = new URL(requestUrl(input), window.location.href);
    if (url.origin !== window.location.origin || !REVIEW_DECISION_PATH.test(url.pathname)) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function approvalRequested(init?: RequestInit): boolean {
  if (typeof init?.body !== "string") return false;
  try {
    const payload = JSON.parse(init.body) as {decision?: unknown};
    return String(payload.decision || "").trim().toLowerCase() === "approved";
  } catch {
    return false;
  }
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

async function containsApprovedPdf(response: Response): Promise<boolean> {
  try {
    const payload = await response.clone().json() as Record<string, unknown>;
    const operatorEdition = objectRecord(payload.operator_approved_edition);
    const operatorReview = objectRecord(operatorEdition.review);
    if (payload.operator_approval_status === "approved"
      && operatorReview.approval_basis === "operator_report"
      && operatorReview.decision === "approved"
      && /^[0-9a-f]{64}$/i.test(String(operatorReview.approval_certificate_sha256 || ""))) {
      return Boolean(String(objectRecord(operatorEdition.reports).pdf_base64 || ""));
    }
    const reports = objectRecord(payload.reports);
    if (!String(reports.pdf_base64 || "")) return false;
    const accepted = objectRecord(payload.accepted_edition);
    const review = objectRecord(accepted.review);
    const certificate = objectRecord(payload.review_certificate);
    const decision = String(
      review.decision
        || certificate.decision
        || payload.review_status
        || objectRecord(payload.approval).status
        || payload.status
        || "",
    ).trim().toLowerCase();
    return decision === "approved";
  } catch {
    return false;
  }
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

/**
 * Approval can persist before its mutation response carries the fully hydrated
 * approved report. Re-read only that same exact run/edition after a successful
 * approval; all non-approval review decisions retain their existing response path.
 * The workspace then performs its existing PDF/hash checks before the one-tap
 * desktop/iOS handoff presents those verified bytes.
 */
export default function FinalReviewApprovedReportHydration() {
  useEffect(() => {
    const originalFetch = window.fetch;

    const hydratedFetch: typeof window.fetch = async (input, init) => {
      const reviewUrl = reviewDecisionUrl(input, init);
      if (!reviewUrl || !approvalRequested(init)) {
        return originalFetch.call(window, input, init);
      }

      const mutationResponse = await originalFetch.call(window, input, init);
      if (!mutationResponse.ok) return mutationResponse;
      if (await containsApprovedPdf(mutationResponse)) return mutationResponse;

      const statusUrl = new URL(reviewUrl.href);
      statusUrl.pathname = statusUrl.pathname.replace(/\/review$/, "");

      for (const delay of APPROVED_REPORT_RETRY_DELAYS_MS) {
        if (delay) await sleep(delay);
        try {
          const currentResponse = await originalFetch.call(window, statusUrl.href, {
            method: "GET",
            headers: init?.headers,
            cache: "no-store",
            credentials: init?.credentials,
          });
          if (!currentResponse.ok) continue;
          if (await containsApprovedPdf(currentResponse)) return currentResponse;
        } catch {
          // Preserve the successful approval response if exact-run re-hydration is unavailable.
        }
      }

      return mutationResponse;
    };

    window.fetch = hydratedFetch;
    return () => {
      if (window.fetch === hydratedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
