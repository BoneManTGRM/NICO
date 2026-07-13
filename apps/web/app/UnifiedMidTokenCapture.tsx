"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const RUN_KEY = "nico.mid.active_run";
const TOKEN_PREFIX = "nico.mid.evidence_token.";

function responsePath(input: RequestInfo | URL): string {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return new URL(raw, window.location.origin).pathname.replace(/\/$/, "") || "/";
  } catch {
    return "";
  }
}

function isMidStatusPath(path: string) {
  return /^\/assessment\/mid-run\/midrun_[^/]+\/status$/.test(path);
}

export default function UnifiedMidTokenCapture() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname !== "/assessment") return;

    const originalFetch = window.fetch.bind(window);
    const wrappedFetch: typeof window.fetch = async (input, init) => {
      const response = await originalFetch(input, init);
      const path = responsePath(input);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      const targeted = method === "POST" && (path === "/assessment/mid-run" || isMidStatusPath(path));
      if (!targeted || !response.ok) return response;

      try {
        const data = await response.clone().json() as Record<string, unknown>;
        const runId = String(data.run_id || "");
        if (!runId.startsWith("midrun_")) return response;
        const submission = data.optional_evidence_submission as {token?: unknown} | undefined;
        const token = String(submission?.token || "");
        sessionStorage.setItem(RUN_KEY, runId);
        if (token) sessionStorage.setItem(TOKEN_PREFIX + runId, token);
      } catch {
        // The assessment response remains usable when browser-session retention is unavailable.
      }
      return response;
    };

    window.fetch = wrappedFetch;
    return () => {
      if (window.fetch === wrappedFetch) window.fetch = originalFetch;
    };
  }, [pathname]);

  return null;
}
