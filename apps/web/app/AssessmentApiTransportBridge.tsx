"use client";

import {useEffect} from "react";

const CONFIGURED_API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const ASSESSMENT_PATH = /^\/assessment\/(?:github|mid-run|full-run)(?:\/[^/?#]+\/status)?$/;
const DIRECT_EXPRESS_PATH = "/assessment/github";

export const ASSESSMENT_FAILURE_EVENT = "nico:assessment-request-failed";

export type AssessmentFailureEvidence = {
  http_status: number;
  route: string;
  status: string;
  code: string;
  message: string;
  run_id: string;
  assessment_type: string;
  progress: Array<{step: string; status: string; message: string}>;
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function boundedText(value: unknown, limit = 320): string {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 3)}...`;
}

function boundedProgress(value: unknown): AssessmentFailureEvidence["progress"] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 16).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    return [{
      step: boundedText(record.step, 80) || "unknown_step",
      status: boundedText(record.status, 40) || "unknown",
      message: boundedText(record.message, 240) || "No bounded failure message was returned.",
    }];
  });
}

async function publishFailure(response: Response, route: string) {
  let payload: Record<string, unknown> = {};
  try {
    const parsed = await response.json();
    if (parsed && typeof parsed === "object") payload = parsed as Record<string, unknown>;
  } catch {
    // The HTTP status and route still provide bounded diagnostic evidence.
  }

  const detail = payload.detail && typeof payload.detail === "object"
    ? payload.detail as Record<string, unknown>
    : payload;
  const evidence: AssessmentFailureEvidence = {
    http_status: response.status,
    route,
    status: boundedText(detail.status || payload.status, 40) || "error",
    code: boundedText(detail.code || payload.code, 80) || `http_${response.status}`,
    message: boundedText(detail.message || payload.message || payload.error, 320)
      || `Assessment request failed with HTTP ${response.status}.`,
    run_id: boundedText(detail.run_id || payload.run_id, 120),
    assessment_type: boundedText(detail.assessment_type || payload.assessment_type, 40),
    progress: boundedProgress(detail.progress || payload.progress),
  };

  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: evidence}));
}

function clearFailure() {
  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: null}));
}

export default function AssessmentApiTransportBridge() {
  useEffect(() => {
    if (!CONFIGURED_API_URL) return;

    let configured: URL;
    try {
      configured = new URL(CONFIGURED_API_URL);
    } catch {
      return;
    }

    const configuredPath = configured.pathname.replace(/\/$/, "");
    const originalFetch = window.fetch.bind(window);

    const bridgedFetch: typeof window.fetch = async (input, init) => {
      let requested: URL;
      try {
        requested = new URL(requestUrl(input), window.location.href);
      } catch {
        return originalFetch(input, init);
      }

      if (requested.origin !== configured.origin) return originalFetch(input, init);
      if (configuredPath && !requested.pathname.startsWith(`${configuredPath}/`)) return originalFetch(input, init);

      const apiPath = configuredPath ? requested.pathname.slice(configuredPath.length) : requested.pathname;
      if (!ASSESSMENT_PATH.test(apiPath)) return originalFetch(input, init);

      clearFailure();

      if (apiPath === DIRECT_EXPRESS_PATH) {
        try {
          const response = await originalFetch(input, init);
          if (!response.ok) await publishFailure(response.clone(), apiPath);
          return response;
        } catch {
          throw new Error(
            "Express transport was interrupted before the Railway backend returned a response. Review backend availability and production CORS diagnostics before retrying.",
          );
        }
      }

      const proxyUrl = new URL(`/api/nico${apiPath}${requested.search}`, window.location.origin);
      const response = input instanceof Request
        ? await originalFetch(new Request(proxyUrl, input), init)
        : await originalFetch(proxyUrl, init);
      if (!response.ok) await publishFailure(response.clone(), apiPath);
      return response;
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
