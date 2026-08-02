"use client";

import {useEffect, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";

function savedRunId(): string {
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!raw) return "";
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return String(parsed.runId || "").trim();
  } catch {
    return "";
  }
}

function activeAssessmentVisible(): boolean {
  const panel = document.querySelector('[data-assessment-run-state="true"]');
  if (!panel) return false;
  const terminalAction = panel.querySelector('[data-assessment-terminal-actions="true"]');
  if (terminalAction) return false;
  return Boolean(savedRunId() || new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY));
}

function clearCurrentRun(): void {
  try {
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
  } catch {
    // URL replacement still provides a clean public assessment entry point.
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);
  url.searchParams.set("new_assessment", String(Date.now()));
  url.hash = "assessment";
  window.location.replace(`${url.pathname}${url.search}${url.hash}`);
}

export default function AssessmentActiveRunReset() {
  const [visible, setVisible] = useState(false);
  const [runId, setRunId] = useState("");

  useEffect(() => {
    const inspect = () => {
      setVisible(activeAssessmentVisible());
      setRunId(savedRunId());
    };
    const observer = new MutationObserver(inspect);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    const interval = window.setInterval(inspect, 1000);
    window.addEventListener("storage", inspect);
    inspect();
    return () => {
      observer.disconnect();
      window.clearInterval(interval);
      window.removeEventListener("storage", inspect);
    };
  }, []);

  if (!visible) return null;

  return <aside
    data-assessment-active-run-reset="true"
    aria-label="Current assessment controls"
    style={{
      position: "fixed",
      left: "max(12px, env(safe-area-inset-left))",
      right: "max(12px, env(safe-area-inset-right))",
      bottom: "max(12px, env(safe-area-inset-bottom))",
      zIndex: 9998,
      maxWidth: 760,
      marginInline: "auto",
      padding: 12,
      border: "1px solid #2d718a",
      borderRadius: 14,
      background: "rgba(7, 19, 36, .97)",
      color: "#eef8ff",
      boxShadow: "0 16px 50px rgba(0,0,0,.45)",
    }}
  >
    <strong style={{display: "block", marginBottom: 6}}>Current assessment</strong>
    {runId ? <code style={{display: "block", marginBottom: 10, overflowWrap: "anywhere"}}>Run: {runId}</code> : null}
    <button
      type="button"
      onClick={clearCurrentRun}
      data-assessment-clear-current-run="true"
    >Clear current run and start new assessment</button>
  </aside>;
}
