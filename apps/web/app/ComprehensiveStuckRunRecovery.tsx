"use client";

import {useEffect, useRef, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const ACTIVE_RUN_MAX_AGE_MS = 2 * 60 * 60_000;
const STALE_CHECK_INTERVAL_MS = 30_000;
const SHORT_REQUEST_TIMEOUT_MS = 45_000;
const LONG_REQUEST_TIMEOUT_MS = 300_000;
const LIFECYCLE_PATH = /^\/api\/nico\/(?:diagnostics\/comprehensive-runtime|assessment\/comprehensive-(?:intake|run\/[^/?#]+(?:\/continue)?))(?:[?#]|$)/;
const RUN_PATH = /\/assessment\/comprehensive-run\/([^/?#]+)/;

const activeControllers = new Set<AbortController>();

type TimeoutDetail = {
  path?: string;
  method?: string;
};

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return new URL(input, window.location.origin).pathname;
  if (input instanceof URL) return input.pathname;
  return new URL(input.url, window.location.origin).pathname;
}

function requestTimeout(path: string, method: string): number {
  if (method === "GET" || path.includes("/diagnostics/comprehensive-runtime")) return SHORT_REQUEST_TIMEOUT_MS;
  return LONG_REQUEST_TIMEOUT_MS;
}

function runIdFromLifecyclePath(path: string): string {
  const match = String(path || "").match(RUN_PATH);
  if (!match?.[1]) return "";
  try {
    return decodeURIComponent(match[1]).trim();
  } catch {
    return match[1].trim();
  }
}

function combinedRequest(
  originalFetch: typeof window.fetch,
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  let path = "";
  try {
    path = requestPath(input);
  } catch {
    return originalFetch(input, init);
  }
  if (!LIFECYCLE_PATH.test(path)) return originalFetch(input, init);

  const controller = new AbortController();
  activeControllers.add(controller);
  const callerSignal = init?.signal;
  const abortFromCaller = () => controller.abort(callerSignal?.reason);
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort(callerSignal.reason);
    else callerSignal.addEventListener("abort", abortFromCaller, {once: true});
  }

  const method = String(init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
  const timeout = window.setTimeout(() => {
    controller.abort(new DOMException("NICO assessment request timed out.", "TimeoutError"));
    window.dispatchEvent(new CustomEvent<TimeoutDetail>("nico:comprehensive-request-timeout", {
      detail: {path, method},
    }));
  }, requestTimeout(path, method));

  const boundedInit: RequestInit = {...init, signal: controller.signal, cache: "no-store"};
  let requestPromise: Promise<Response>;
  if (input instanceof Request) {
    // The proxy bridge already constructed the exact request body. Passing the same
    // init object to fetch a second time is tolerated by Chromium but can consume or
    // reject the body in WebKit before the intake response is returned. Construct one
    // bounded Request and dispatch it without a second init/body application.
    const boundedRequest = new Request(input, boundedInit);
    requestPromise = originalFetch(boundedRequest);
  } else {
    requestPromise = originalFetch(input, boundedInit);
  }

  return requestPromise.finally(() => {
    window.clearTimeout(timeout);
    if (callerSignal) callerSignal.removeEventListener("abort", abortFromCaller);
    activeControllers.delete(controller);
  });
}

function readStoredRun(): {runId: string; startedAt: number} | null {
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Record<string, unknown>;
    const runId = String(value.runId || "").trim();
    const startedAt = Number(value.startedAt);
    if (!runId) return null;
    return {runId, startedAt: Number.isFinite(startedAt) && startedAt > 0 ? startedAt : Date.now()};
  } catch {
    return null;
  }
}

function currentRunId(): string {
  return readStoredRun()?.runId
    || new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim()
    || "";
}

function retainExactRunIdentity(runId: string): void {
  const exactRunId = String(runId || "").trim();
  if (!exactRunId) return;
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    const existing = raw ? JSON.parse(raw) as Record<string, unknown> : {};
    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, JSON.stringify({
      ...existing,
      version: 1,
      runId: exactRunId,
      startedAt: Number(existing.startedAt) > 0 ? Number(existing.startedAt) : Date.now(),
    }));
  } catch {
    // The URL remains the exact-run recovery source when storage is unavailable.
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.set(ACTIVE_RUN_QUERY_KEY, exactRunId);
  url.hash = "assessment";
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function clearRunIdentity(): void {
  activeControllers.forEach((controller) => controller.abort(new DOMException("Assessment recovery canceled.", "AbortError")));
  activeControllers.clear();
  try {
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
  } catch {
    // URL cleanup remains the browser-visible recovery boundary.
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);
  url.hash = "assessment";
  window.location.replace(`${url.pathname}${url.search}${url.hash}`);
}

export default function ComprehensiveStuckRunRecovery() {
  const [visible, setVisible] = useState(false);
  const [reason, setReason] = useState("");
  const [recoveryRunId, setRecoveryRunId] = useState("");
  const timedOutRunId = useRef("");
  const dismissedRunId = useRef("");

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const boundedFetch: typeof window.fetch = (input, init) => combinedRequest(originalFetch, input, init);
    window.fetch = boundedFetch;

    const inspect = () => {
      if (!window.location.pathname.includes("assessment")) {
        setVisible(false);
        return;
      }

      const stored = readStoredRun();
      const runId = stored?.runId
        || new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim()
        || recoveryRunId
        || "";
      if (dismissedRunId.current && dismissedRunId.current !== runId) {
        dismissedRunId.current = "";
      }
      if (timedOutRunId.current && timedOutRunId.current !== runId) {
        timedOutRunId.current = "";
      }

      const stale = Boolean(stored && Date.now() - stored.startedAt > ACTIVE_RUN_MAX_AGE_MS);
      const timedOut = Boolean(timedOutRunId.current && timedOutRunId.current === runId);
      const dismissed = Boolean(runId && dismissedRunId.current === runId);

      if (dismissed || (!stale && !timedOut)) {
        setVisible(false);
        return;
      }
      if (stale) {
        setRecoveryRunId(runId);
        setReason("The saved assessment is older than the recovery limit.");
        setVisible(true);
        return;
      }
      if (timedOut) {
        setRecoveryRunId(runId);
        setVisible(true);
      }
    };

    const timeoutListener = (event: Event) => {
      const detail = (event as CustomEvent<TimeoutDetail>).detail || {};
      const path = String(detail.path || "");
      const timeoutRunId = currentRunId() || runIdFromLifecyclePath(path);

      // A readiness request without an accepted exact run belongs in the normal
      // assessment error UI. Recovery controls are shown only when NICO can retain
      // and retry a concrete run identity.
      if (!timeoutRunId) {
        timedOutRunId.current = "";
        setRecoveryRunId("");
        setVisible(false);
        return;
      }

      retainExactRunIdentity(timeoutRunId);
      timedOutRunId.current = timeoutRunId;
      dismissedRunId.current = "";
      setRecoveryRunId(timeoutRunId);
      setReason(
        path.endsWith("/continue")
          ? "The current assessment stage exceeded the bounded response time. The exact run was retained and can be retried."
          : "The exact saved run did not respond before the bounded status timeout. Its identity was retained for recovery.",
      );
      setVisible(true);
    };
    const interval = window.setInterval(inspect, STALE_CHECK_INTERVAL_MS);
    window.addEventListener("nico:comprehensive-request-timeout", timeoutListener);
    inspect();

    return () => {
      window.clearInterval(interval);
      window.removeEventListener("nico:comprehensive-request-timeout", timeoutListener);
      if (window.fetch === boundedFetch) window.fetch = originalFetch;
      activeControllers.forEach((controller) => controller.abort());
      activeControllers.clear();
    };
  }, [recoveryRunId]);

  if (!visible) return null;

  const runId = recoveryRunId || currentRunId();
  const keepWaiting = () => {
    dismissedRunId.current = runId;
    timedOutRunId.current = "";
    setVisible(false);
  };
  const retryExactRun = () => {
    retainExactRunIdentity(runId);
    window.location.reload();
  };

  return <aside
    role="alert"
    aria-live="assertive"
    data-comprehensive-stuck-run-recovery="true"
    style={{
      position: "fixed",
      left: "max(12px, env(safe-area-inset-left))",
      right: "max(12px, env(safe-area-inset-right))",
      bottom: "max(12px, env(safe-area-inset-bottom))",
      zIndex: 10000,
      border: "1px solid #2d718a",
      borderRadius: 16,
      background: "#071324",
      color: "#eef8ff",
      boxShadow: "0 18px 60px rgba(0,0,0,.55)",
      padding: 16,
      maxWidth: 760,
      marginInline: "auto",
    }}
  >
    <strong style={{display: "block", fontSize: 18}}>Assessment recovery available</strong>
    <p style={{margin: "8px 0 12px", color: "#b9c9dc"}}>{reason}</p>
    {runId ? <code style={{display: "block", marginBottom: 12, overflowWrap: "anywhere"}}>Run: {runId}</code> : null}
    <div style={{display: "flex", gap: 10, flexWrap: "wrap"}}>
      <button type="button" onClick={retryExactRun} disabled={!runId}>Retry exact run</button>
      <button type="button" onClick={clearRunIdentity} data-clear-stuck-comprehensive-run="true">Clear stuck run and start new</button>
      <button type="button" onClick={keepWaiting}>Keep waiting</button>
    </div>
  </aside>;
}
