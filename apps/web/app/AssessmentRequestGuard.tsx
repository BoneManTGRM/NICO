"use client";

import {useEffect} from "react";

const ASSESSMENT_REQUEST_TIMEOUT_MS = 120_000;
const GUARDED_PATHS = [
  "/assessment/github",
  "/assessment/mid-run",
];

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function isGuardedAssessmentRequest(input: RequestInfo | URL): boolean {
  try {
    const parsed = new URL(requestUrl(input), window.location.origin);
    return GUARDED_PATHS.some((path) => parsed.pathname === path || parsed.pathname.startsWith(`${path}/`));
  } catch {
    return false;
  }
}

export default function AssessmentRequestGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!isGuardedAssessmentRequest(input) || init?.signal) {
        return originalFetch(input, init);
      }

      const controller = new AbortController();
      const timeout = window.setTimeout(() => {
        controller.abort(new Error("Assessment request exceeded two minutes. NICO stopped waiting instead of leaving the Run button spinning. Check backend status and retry."));
      }, ASSESSMENT_REQUEST_TIMEOUT_MS);

      try {
        return await originalFetch(input, {...init, signal: controller.signal});
      } finally {
        window.clearTimeout(timeout);
      }
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  return null;
}

export {ASSESSMENT_REQUEST_TIMEOUT_MS, GUARDED_PATHS};
