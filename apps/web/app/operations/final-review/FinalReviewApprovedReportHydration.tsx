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
 * Review POSTs can persist approval successfully before their mutation response carries
 * the fully re-hydrated report body. Final Review already has a canonical exact-run GET
 * endpoint, so after a successful decision we return that exact current representation
 * to the existing workspace. The workspace then performs its existing PDF/hash checks
 * and the existing desktop/iOS handoff presents those verified bytes.
 */
export default function FinalReviewApprovedReportHydration() {
  useEffect(() => {
    const originalFetch = window.fetch;

    const hydratedFetch: typeof window.fetch = async (input, init) => {
      const reviewUrl = reviewDecisionUrl(input, init);
      if (!reviewUrl) return originalFetch.call(window, input, init);

      const mutationResponse = await originalFetch.call(window, input, init);
      if (!mutationResponse.ok) return mutationResponse;

      const statusUrl = new URL(reviewUrl.href);
      statusUrl.pathname = statusUrl.pathname.replace(/\/review$/, "");
      const requireApprovedPdf = approvalRequested(init);

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
          if (!requireApprovedPdf || await containsApprovedPdf(currentResponse)) {
            return currentResponse;
          }
        } catch {
          // Preserve the successful mutation response if exact-run re-hydration is unavailable.
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
