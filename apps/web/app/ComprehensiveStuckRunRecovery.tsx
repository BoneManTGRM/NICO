"use client";

import {useEffect, useMemo, useRef, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const ACTIVE_RUN_MAX_AGE_MS = 2 * 60 * 60_000;
const RECOVERY_CONTROL_DELAY_MS = 15_000;
const SHORT_REQUEST_TIMEOUT_MS = 45_000;
const LONG_REQUEST_TIMEOUT_MS = 300_000;
const LIFECYCLE_PATH = /^\/api\/nico\/(?:diagnostics\/comprehensive-runtime|assessment\/comprehensive-(?:intake|run\/[^/?#]+(?:\/continue)?))(?:[?#]|$)/;
const RUNNING_COPY = /checking readiness|verifying assessment service readiness|awaiting scanner completion|persistence verification pending|preparing report|running scanner/i;

const activeControllers = new Set<AbortController>();

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return new URL(input, window.location.origin).pathname;
  if (input instanceof URL) return input.pathname;
  return new URL(input.url, window.location.origin).pathname;
}

function requestTimeout(path: string, method: string): number {
  if (method === "GET" || path.includes("/diagnostics/comprehensive-runtime")) return SHORT_REQUEST_TIMEOUT_MS;
  return LONG_REQUEST_TIMEOUT_MS;
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
    window.dispatchEvent(new CustomEvent("nico:comprehensive-request-timeout", {detail: {path, method}}));
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
  const mountedAt = useRef(0);

  useEffect(() => {
    mountedAt.current = Date.now();
    const originalFetch = window.fetch.bind(window);
    const boundedFetch: typeof window.fetch = (input, init) => combinedRequest(originalFetch, input, init);
    window.fetch = boundedFetch;

    const inspect = () => {
      if (!window.location.pathname.includes("assessment")) {
        setVisible(false);
        return;
      }
      const stored = readStoredRun();
      const urlRunId = new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim() || "";
      if (stored && Date.now() - stored.startedAt > ACTIVE_RUN_MAX_AGE_MS) {
        setReason("The saved assessment is older than the recovery limit.");
        setVisible(true);
        return;
      }
      const text = document.body?.innerText || "";
      const runningCopy = RUNNING_COPY.test(text);
      const delayed = Date.now() - mountedAt.current >= RECOVERY_CONTROL_DELAY_MS;
      setVisible(Boolean((stored || urlRunId) && runningCopy && delayed));
      if ((stored || urlRunId) && runningCopy && delayed) {
        setReason("This assessment is still waiting. You can retry it or clear the saved browser state and start a new assessment.");
      }
    };

    const timeoutListener = () => {
      setReason("The assessment service did not respond before the bounded request timeout.");
      setVisible(true);
    };
    const observer = new MutationObserver(inspect);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    const interval = window.setInterval(inspect, 1_000);
    window.addEventListener("nico:comprehensive-request-timeout", timeoutListener);
    inspect();

    return () => {
      observer.disconnect();
      window.clearInterval(interval);
      window.removeEventListener("nico:comprehensive-request-timeout", timeoutListener);
      if (window.fetch === boundedFetch) window.fetch = originalFetch;
      activeControllers.forEach((controller) => controller.abort());
      activeControllers.clear();
    };
  }, []);

  const runId = useMemo(() => {
    if (typeof window === "undefined") return "";
    return readStoredRun()?.runId || new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY) || "";
  }, [visible]);

  if (!visible) return null;

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
      <button type="button" onClick={() => window.location.reload()}>Retry saved run</button>
      <button type="button" onClick={clearRunIdentity} data-clear-stuck-comprehensive-run="true">Clear stuck run and start new</button>
      <button type="button" onClick={() => setVisible(false)}>Keep waiting</button>
    </div>
  </aside>;
}
