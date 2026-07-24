"use client";

import {useEffect} from "react";
import {ASSESSMENT_FAILURE_EVENT, type AssessmentFailureEvidence} from "./AssessmentApiTransportBridge";

const EXPRESS_ROUTE = /^\/api\/nico\/assessment\/express-run(?:\/[^/?#]+\/status)?$/;
const TERMINAL_FAILURES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);

function requestUrl(input: RequestInfo | URL): URL | null {
  try {
    if (typeof input === "string") return new URL(input, window.location.origin);
    if (input instanceof URL) return input;
    return new URL(input.url, window.location.origin);
  } catch {
    return null;
  }
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown, limit: number): string {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  return normalized.length <= limit ? normalized : `${normalized.slice(0, Math.max(0, limit - 3))}...`;
}

function progressRows(value: unknown): AssessmentFailureEvidence["progress"] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 16).flatMap((item) => {
    const row = record(item);
    if (!Object.keys(row).length) return [];
    return [{
      step: text(row.step, 80) || "unknown_step",
      status: text(row.status, 40) || "unknown",
      message: text(row.message, 240) || "No bounded stage message was returned.",
    }];
  });
}

function firstFailedStage(progress: unknown): string {
  if (!Array.isArray(progress)) return "";
  for (const item of progress) {
    const row = record(item);
    if (TERMINAL_FAILURES.has(text(row.status, 40).toLowerCase())) {
      return text(row.step, 80);
    }
  }
  return "";
}

async function normalizeTerminalFailure(response: Response, route: string): Promise<Response | null> {
  let payload: Record<string, unknown> = {};
  try {
    payload = record(await response.clone().json());
  } catch {
    return null;
  }

  const detail = record(payload.detail);
  const source = Object.keys(detail).length ? detail : payload;
  const status = text(source.status || payload.status, 40).toLowerCase();
  if (!TERMINAL_FAILURES.has(status)) return null;

  const progress = Array.isArray(source.progress) ? source.progress : Array.isArray(payload.progress) ? payload.progress : [];
  const runId = text(source.run_id || payload.run_id, 120);
  const failureStage = text(source.failure_stage || payload.failure_stage, 80) || firstFailedStage(progress);
  const code = text(source.failure_code || source.code || payload.code, 80) || `http_${response.status}`;
  const message = text(source.message || payload.message || payload.error, 320)
    || "The Express run stopped before every required stage completed.";

  const normalized = {
    ...payload,
    ...source,
    status,
    code,
    failure_code: code,
    failure_stage: failureStage,
    current_stage: failureStage || text(source.current_stage || payload.current_stage, 80),
    run_id: runId,
    progress,
    http_status: response.status,
    human_review_required: true,
    client_ready: false,
    client_delivery_allowed: false,
  };

  const evidence: AssessmentFailureEvidence = {
    http_status: response.status,
    route,
    status,
    code,
    message,
    run_id: runId,
    assessment_type: text(source.assessment_type || payload.assessment_type, 40) || "express",
    progress: progressRows(progress),
  };
  window.dispatchEvent(new CustomEvent(ASSESSMENT_FAILURE_EVENT, {detail: evidence}));

  return new Response(JSON.stringify(normalized), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, private",
      "X-NICO-Original-Status": String(response.status),
      "X-NICO-Terminal-Failure": "true",
    },
  });
}

export default function AssessmentFailureResponseBridge() {
  useEffect(() => {
    const previousFetch = window.fetch;
    const bridgedFetch: typeof window.fetch = async (input, init) => {
      const target = requestUrl(input);
      const response = await previousFetch(input, init);
      if (!target || target.origin !== window.location.origin || !EXPRESS_ROUTE.test(target.pathname) || response.ok) {
        return response;
      }
      return await normalizeTerminalFailure(response, target.pathname) || response;
    };

    window.fetch = bridgedFetch;
    return () => {
      if (window.fetch === bridgedFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
