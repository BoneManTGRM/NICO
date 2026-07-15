"use client";

import {useEffect, useMemo, useState} from "react";
import {createPortal} from "react-dom";

export const ASSESSMENT_PROGRESS_EVENT = "nico:assessment-progress";

type ProgressItem = {
  step?: string;
  status?: string;
  message?: string;
  progress_percent?: number;
};

type ProgressPayload = {
  status?: string;
  run_id?: string;
  assessment_type?: string;
  service_tier?: string;
  progress?: ProgressItem[];
  progress_percent?: number;
  active_step?: string;
  updated_at?: string;
};

type LiveProgress = {
  runId: string;
  tier: string;
  status: string;
  activeStep: string;
  message: string;
  percent: number | null;
  completed: number;
  total: number;
  pollCount: number;
  startedAt: number;
  updatedAt: number;
  terminal: boolean;
};

const TERMINAL = new Set(["complete", "completed", "blocked", "failed", "error", "interrupted", "rejected"]);
const COMPLETE = new Set(["complete", "completed", "attached", "verified", "ready", "requested"]);
const ACTIVE = new Set(["queued", "running", "pending", "planned", "starting"]);

function responsePath(input: RequestInfo | URL): string {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return new URL(raw, window.location.origin).pathname;
  } catch {
    return "";
  }
}

function isAssessmentLifecyclePath(path: string) {
  return /\/assessment\/(?:express-run|mid-run|full-run)(?:\/[^/]+\/status)?$/.test(path)
    || path.endsWith("/assessment/github");
}

function boundedPercent(value: unknown): number | null {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Math.max(0, Math.min(100, Math.round(number)));
}

function progressSummary(payload: ProgressPayload) {
  const items = Array.isArray(payload.progress) ? payload.progress : [];
  const completed = items.filter((item) => COMPLETE.has(String(item.status || "").toLowerCase())).length;
  const active = items.find((item) => ACTIVE.has(String(item.status || "").toLowerCase()));
  const total = items.length;
  const itemPercent = active ? boundedPercent(active.progress_percent) : null;
  const payloadPercent = boundedPercent(payload.progress_percent);
  // One generic Express running record is not a defensible percentage. Keep the
  // bar animated until the backend returns a real percent or multiple stages.
  const derivedPercent = total > 1 || completed > 0
    ? Math.round((completed / Math.max(1, total)) * 100)
    : null;
  return {
    completed,
    total,
    activeStep: String(payload.active_step || active?.step || "assessment").replaceAll("_", " "),
    message: String(active?.message || "Assessment work is continuing on the backend."),
    percent: payloadPercent ?? itemPercent ?? derivedPercent,
  };
}

function dispatchProgress(payload: ProgressPayload) {
  window.dispatchEvent(new CustomEvent(ASSESSMENT_PROGRESS_EVENT, {detail: payload}));
}

function findRunPanel(): HTMLElement | null {
  for (const eyebrow of Array.from(document.querySelectorAll<HTMLElement>(".eyebrow"))) {
    if (eyebrow.textContent?.trim().toUpperCase() === "AUTOMATED RUN STATE") {
      return eyebrow.closest("section");
    }
  }
  return null;
}

function statusLabel(status: string) {
  if (["complete", "completed"].includes(status)) return "Complete";
  if (["failed", "blocked", "error", "interrupted", "rejected"].includes(status)) return "Stopped";
  if (status === "queued") return "Accepted";
  return "Running";
}

function elapsedLabel(startedAt: number, now: number) {
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${String(remainder).padStart(2, "0")}s` : `${remainder}s`;
}

export default function AssessmentLiveProgress() {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [live, setLive] = useState<LiveProgress | null>(null);
  const [clock, setClock] = useState(Date.now());

  useEffect(() => {
    let cancelled = false;
    const locate = () => {
      if (cancelled) return;
      const panel = findRunPanel();
      if (panel) setTarget(panel);
    };
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, {childList: true, subtree: true});
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const onProgress = (event: Event) => {
      const payload = (event as CustomEvent<ProgressPayload>).detail || {};
      const status = String(payload.status || "running").toLowerCase();
      const runId = String(payload.run_id || "");
      const summary = progressSummary(payload);
      setLive((current) => ({
        runId: runId || current?.runId || "pending run identity",
        tier: String(payload.assessment_type || payload.service_tier || current?.tier || "assessment"),
        status,
        activeStep: summary.activeStep,
        message: summary.message,
        percent: status === "complete" || status === "completed" ? 100 : summary.percent,
        completed: summary.completed,
        total: summary.total,
        pollCount: (current?.pollCount || 0) + 1,
        startedAt: current?.startedAt || Date.now(),
        updatedAt: Date.now(),
        terminal: TERMINAL.has(status),
      }));
    };
    window.addEventListener(ASSESSMENT_PROGRESS_EVENT, onProgress as EventListener);
    return () => window.removeEventListener(ASSESSMENT_PROGRESS_EVENT, onProgress as EventListener);
  }, []);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const observedFetch: typeof window.fetch = async (input, init) => {
      const response = await originalFetch(input, init);
      const path = responsePath(input);
      if (!isAssessmentLifecyclePath(path)) return response;
      try {
        const payload = await response.clone().json() as ProgressPayload;
        if (payload && typeof payload === "object") dispatchProgress(payload);
      } catch {
        // The original response remains untouched when bounded progress parsing is unavailable.
      }
      return response;
    };
    window.fetch = observedFetch;
    return () => {
      if (window.fetch === observedFetch) window.fetch = originalFetch;
    };
  }, []);

  useEffect(() => {
    if (!live || live.terminal) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live]);

  const percentLabel = useMemo(() => {
    if (!live) return "";
    if (live.percent === null || !Number.isFinite(live.percent)) return "Live";
    return `${live.percent}%`;
  }, [live]);

  if (!target || !live) return null;

  const progressClass = live.percent === null && !live.terminal ? "nico-live-progress-fill indeterminate" : "nico-live-progress-fill";
  const width = live.percent === null ? undefined : `${Math.max(live.terminal ? 0 : 4, live.percent)}%`;
  const evidenceText = live.total > 1
    ? `${live.completed} of ${live.total} recorded stages complete`
    : `${live.pollCount} live backend status update${live.pollCount === 1 ? "" : "s"}`;

  return createPortal(<>
    <style>{`
      [aria-label="Automatic continuation in progress"] { display: none !important; }
      .nico-live-progress { margin: 18px 0 4px; padding: 16px; border: 1px solid #334155; border-radius: 18px; background: #081426; }
      .nico-live-progress-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }
      .nico-live-progress-head b { display: block; color: #e2e8f0; font-size: 17px; text-transform: capitalize; }
      .nico-live-progress-head span { color: #7dd3fc; font-weight: 900; }
      .nico-live-progress p { margin: 7px 0; color: #cbd5e1; line-height: 1.45; }
      .nico-live-progress-meta { display: flex; flex-wrap: wrap; gap: 10px 18px; font-size: 13px; color: #94a3b8; }
      .nico-live-progress-track { height: 14px; margin: 13px 0 9px; overflow: hidden; border: 1px solid #334155; border-radius: 999px; background: #020617; }
      .nico-live-progress-fill { display: block; height: 100%; border-radius: inherit; background: #38bdf8; transition: width 320ms ease; }
      .nico-live-progress-fill.indeterminate { width: 36%; animation: nico-live-progress 1.25s ease-in-out infinite; }
      @keyframes nico-live-progress { 0% { transform: translateX(-110%); } 55% { transform: translateX(120%); } 100% { transform: translateX(300%); } }
      @media (max-width: 640px) { .nico-live-progress-head { align-items: center; } .nico-live-progress { padding: 14px; } }
    `}</style>
    <div className="nico-live-progress" role="status" aria-live="polite" data-testid="assessment-live-progress">
      <div className="nico-live-progress-head">
        <div><b>{live.activeStep}</b><p>{live.message}</p></div>
        <span>{percentLabel}</span>
      </div>
      <div className="nico-live-progress-track" aria-label="Live backend assessment progress">
        <span className={progressClass} style={{width}} />
      </div>
      <div className="nico-live-progress-meta">
        <span>Status: {statusLabel(live.status)}</span>
        <span>Elapsed: {elapsedLabel(live.startedAt, clock)}</span>
        <span>{evidenceText}</span>
        <span>Run: {live.runId}</span>
      </div>
    </div>
  </>, target);
}
