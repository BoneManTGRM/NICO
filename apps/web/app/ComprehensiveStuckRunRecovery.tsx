"use client";

import {useEffect, useRef, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const SHORT_REQUEST_TIMEOUT_MS = 45_000;
const LONG_REQUEST_TIMEOUT_MS = 300_000;
const LIFECYCLE_PATH = /^\/api\/nico\/(?:diagnostics\/comprehensive-runtime|assessment\/comprehensive-(?:intake|run\/[^/?#]+(?:\/continue)?))(?:[?#]|$)/;
const RUN_PATH = /\/assessment\/comprehensive-run\/([^/?#]+)/;
const RECOVERY_CLEARANCE_ATTRIBUTE =
  "data-comprehensive-stuck-run-recovery-visible";
const RECOVERY_CLEARANCE_PROPERTY =
  "--nico-stuck-run-recovery-clearance";

const activeControllers = new Set<AbortController>();

type TimeoutDetail = {
  path?: string;
  method?: string;
};

type RecoveryReason = "continue" | "status";

type Copy = {
  ariaLabel: string;
  title: string;
  run: string;
  retry: string;
  clear: string;
  wait: string;
  continueReason: string;
  statusReason: string;
  confirmClear: string;
};

const COPY: Record<"en" | "es", Copy> = {
  en: {
    ariaLabel: "Assessment recovery controls",
    title: "Assessment recovery available",
    run: "Run",
    retry: "Retry exact run",
    clear: "Clear stuck run and start new",
    wait: "Keep waiting",
    continueReason:
      "The current assessment stage exceeded the bounded response time. The exact run was retained and can be retried.",
    statusReason:
      "The exact saved run did not respond before the bounded status timeout. Its identity was retained for recovery.",
    confirmClear:
      "Clear the preserved run and start a new assessment? This abandons the browser recovery link for the exact run.",
  },
  es: {
    ariaLabel: "Controles de recuperación de la evaluación",
    title: "Recuperación de evaluación disponible",
    run: "Ejecución",
    retry: "Reintentar la ejecución exacta",
    clear: "Borrar la ejecución atascada e iniciar una nueva",
    wait: "Seguir esperando",
    continueReason:
      "La etapa actual de la evaluación superó el tiempo de respuesta limitado. Se conservó la ejecución exacta y puede reintentarse.",
    statusReason:
      "La ejecución exacta guardada no respondió antes del límite de espera del estado. Su identidad se conservó para la recuperación.",
    confirmClear:
      "¿Borrar la ejecución conservada e iniciar una evaluación nueva? Esto elimina del navegador el vínculo de recuperación de la ejecución exacta.",
  },
};

function isSpanishRoute(): boolean {
  const path = window.location.pathname.toLowerCase();
  return path === "/es" || path.startsWith("/es/") || path === "/es-mx" || path.startsWith("/es-mx/");
}

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

function readStoredRun(): {runId: string} | null {
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Record<string, unknown>;
    const runId = String(value.runId || "").trim();
    return runId ? {runId} : null;
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
  url.searchParams.set("new_assessment", String(Date.now()));
  url.hash = "assessment";
  window.location.replace(`${url.pathname}${url.search}${url.hash}`);
}

function clearReservedViewportSpace(): void {
  const root = document.documentElement;
  root.removeAttribute(RECOVERY_CLEARANCE_ATTRIBUTE);
  root.style.removeProperty(RECOVERY_CLEARANCE_PROPERTY);
}

export default function ComprehensiveStuckRunRecovery() {
  const [visible, setVisible] = useState(false);
  const [reason, setReason] = useState<RecoveryReason>("status");
  const [recoveryRunId, setRecoveryRunId] = useState("");
  const [spanish, setSpanish] = useState(false);
  const timedOutRunId = useRef("");
  const panelRef = useRef<HTMLElement | null>(null);
  const copy = COPY[spanish ? "es" : "en"];

  useEffect(() => {
    setSpanish(isSpanishRoute());
    const originalFetch = window.fetch.bind(window);
    const boundedFetch: typeof window.fetch = (input, init) => combinedRequest(originalFetch, input, init);
    window.fetch = boundedFetch;

    const timeoutListener = (event: Event) => {
      const detail = (event as CustomEvent<TimeoutDetail>).detail || {};
      const path = String(detail.path || "");
      const timeoutRunId = currentRunId() || runIdFromLifecyclePath(path);

      // Browser age is not evidence that a durable run is invalid or unrecoverable.
      // Recovery controls appear only after a bounded lifecycle request actually
      // times out, and the canonical controller then reads the exact backend run.
      if (!timeoutRunId) {
        timedOutRunId.current = "";
        setRecoveryRunId("");
        setVisible(false);
        return;
      }

      retainExactRunIdentity(timeoutRunId);
      timedOutRunId.current = timeoutRunId;
      setRecoveryRunId(timeoutRunId);
      setReason(path.endsWith("/continue") ? "continue" : "status");
      setSpanish(isSpanishRoute());
      setVisible(true);
    };

    window.addEventListener("nico:comprehensive-request-timeout", timeoutListener);

    return () => {
      window.removeEventListener("nico:comprehensive-request-timeout", timeoutListener);
      if (window.fetch === boundedFetch) window.fetch = originalFetch;
      activeControllers.forEach((controller) => controller.abort());
      activeControllers.clear();
      clearReservedViewportSpace();
    };
  }, []);

  useEffect(() => {
    const panel = panelRef.current;
    if (!visible || !panel) {
      clearReservedViewportSpace();
      return;
    }

    const reserveViewportSpace = () => {
      const height = Math.ceil(panel.getBoundingClientRect().height);
      if (height <= 0) return;
      const root = document.documentElement;
      root.setAttribute(RECOVERY_CLEARANCE_ATTRIBUTE, "true");
      root.style.setProperty(RECOVERY_CLEARANCE_PROPERTY, `${height}px`);
    };

    reserveViewportSpace();
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(reserveViewportSpace);
    resizeObserver?.observe(panel);
    window.addEventListener("resize", reserveViewportSpace);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", reserveViewportSpace);
      clearReservedViewportSpace();
    };
  }, [recoveryRunId, spanish, visible]);

  if (!visible) return null;

  const runId = recoveryRunId || currentRunId();
  const keepWaiting = () => {
    timedOutRunId.current = "";
    setVisible(false);
  };
  const retryExactRun = () => {
    retainExactRunIdentity(runId);
    const url = new URL(window.location.href);
    url.searchParams.set("tier", "comprehensive");
    url.searchParams.set(ACTIVE_RUN_QUERY_KEY, runId);
    url.searchParams.set("recovery_attempt", Date.now().toString());
    url.hash = "assessment";
    window.location.replace(`${url.pathname}${url.search}${url.hash}`);
  };
  const confirmAndClear = () => {
    if (window.confirm(copy.confirmClear)) clearRunIdentity();
  };
  const localizedReason = reason === "continue" ? copy.continueReason : copy.statusReason;

  return <aside
    ref={panelRef}
    role="alert"
    aria-live="assertive"
    aria-label={copy.ariaLabel}
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
      maxHeight: "min(60dvh, 440px)",
      overflowY: "auto",
      overscrollBehavior: "contain",
      touchAction: "pan-y",
      marginInline: "auto",
    }}
  >
    <strong style={{display: "block", fontSize: 18}}>{copy.title}</strong>
    <p style={{margin: "8px 0 12px", color: "#b9c9dc"}}>{localizedReason}</p>
    {runId ? <code style={{display: "block", marginBottom: 12, overflowWrap: "anywhere"}}>{copy.run}: {runId}</code> : null}
    <div style={{display: "flex", gap: 10, flexWrap: "wrap"}}>
      <button type="button" onClick={retryExactRun} disabled={!runId}>{copy.retry}</button>
      <button type="button" onClick={confirmAndClear} data-clear-stuck-comprehensive-run="true">{copy.clear}</button>
      <button type="button" onClick={keepWaiting}>{copy.wait}</button>
    </div>
  </aside>;
}
