"use client";

import {useEffect} from "react";

const SHA_PATTERN = /^[0-9a-f]{40}$/;
const START_PATHS = new Set([
  "/api/nico/assessment/express-run",
  "/api/nico/assessment/comprehensive-intake",
]);

function expectedCommit(): string {
  const value = new URL(window.location.href).searchParams.get("expected_commit_sha")?.trim().toLowerCase() || "";
  return SHA_PATTERN.test(value) ? value : "";
}

function withCommitMarker(value: unknown, commitSha: string): string {
  const base = String(value || "public_assessment_requester")
    .replace(/(?:^|[;\s])expected_commit_sha=[0-9a-f]{40}(?=$|[;\s])/gi, "")
    .replace(/;;+/g, ";")
    .replace(/^;+|;+$/g, "")
    .trim();
  return `${base || "public_assessment_requester"};expected_commit_sha=${commitSha}`;
}

export default function AssessmentExactCommitTransport() {
  useEffect(() => {
    const previous = window.fetch.bind(window);

    const exactCommitFetch: typeof window.fetch = async (input, init) => {
      const commitSha = expectedCommit();
      if (!commitSha) return previous(input, init);

      const requestUrl = typeof input === "string"
        ? new URL(input, window.location.origin)
        : input instanceof URL
          ? new URL(input.href)
          : new URL(input.url, window.location.origin);
      const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
      if (requestUrl.origin !== window.location.origin || method !== "POST" || !START_PATHS.has(requestUrl.pathname)) {
        return previous(input, init);
      }

      const rawBody = init?.body;
      if (typeof rawBody !== "string") return previous(input, init);
      try {
        const payload = JSON.parse(rawBody) as Record<string, unknown>;
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) return previous(input, init);
        payload.expected_commit_sha = commitSha;
        payload.authorized_by = withCommitMarker(payload.authorized_by, commitSha);
        return previous(input, {...init, body: JSON.stringify(payload)});
      } catch {
        return previous(input, init);
      }
    };

    window.fetch = exactCommitFetch;
    return () => {
      if (window.fetch === exactCommitFetch) window.fetch = previous;
    };
  }, []);

  return null;
}
