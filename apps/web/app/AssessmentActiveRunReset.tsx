"use client";

import {useEffect, useRef, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const MOBILE_ACTIVE_RUN_QUERY = "(max-width: 760px), (pointer: coarse)";
const ACTIVE_RUN_CLEARANCE_ATTRIBUTE =
  "data-assessment-active-run-reset-visible";
const ACTIVE_RUN_CLEARANCE_PROPERTY = "--nico-active-run-reset-clearance";

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
  const terminalAction = panel.querySelector(
    '[data-assessment-terminal-actions="true"]',
  );
  if (terminalAction) return false;
  return Boolean(
    savedRunId() ||
      new URL(window.location.href).searchParams.get(ACTIVE_RUN_QUERY_KEY),
  );
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

function clearReservedViewportSpace(): void {
  const root = document.documentElement;
  root.removeAttribute(ACTIVE_RUN_CLEARANCE_ATTRIBUTE);
  root.style.removeProperty(ACTIVE_RUN_CLEARANCE_PROPERTY);
}

export default function AssessmentActiveRunReset() {
  const [visible, setVisible] = useState(false);
  const [runId, setRunId] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const panelRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const inspect = () => {
      setVisible(activeAssessmentVisible());
      setRunId(savedRunId());
    };
    const observer = new MutationObserver(inspect);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    const interval = window.setInterval(inspect, 1000);
    window.addEventListener("storage", inspect);
    inspect();
    return () => {
      observer.disconnect();
      window.clearInterval(interval);
      window.removeEventListener("storage", inspect);
    };
  }, []);

  useEffect(() => {
    if (window.matchMedia?.(MOBILE_ACTIVE_RUN_QUERY).matches) {
      setCollapsed(true);
    }
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
      root.setAttribute(ACTIVE_RUN_CLEARANCE_ATTRIBUTE, "true");
      root.style.setProperty(ACTIVE_RUN_CLEARANCE_PROPERTY, `${height}px`);
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
  }, [collapsed, runId, visible]);

  if (!visible) return null;

  return (
    <aside
      ref={panelRef}
      data-assessment-active-run-reset="true"
      data-assessment-active-run-reset-collapsed={collapsed ? "true" : "false"}
      aria-label="Current assessment controls"
      style={{
        position: "fixed",
        left: "max(12px, env(safe-area-inset-left))",
        right: "max(12px, env(safe-area-inset-right))",
        bottom: "max(12px, env(safe-area-inset-bottom))",
        zIndex: 9998,
        maxWidth: 760,
        maxHeight: collapsed ? 68 : "min(44dvh, 340px)",
        marginInline: "auto",
        padding: collapsed ? "10px 12px" : 12,
        overflowY: collapsed ? "hidden" : "auto",
        overscrollBehavior: "contain",
        touchAction: "pan-y",
        border: "1px solid #2d718a",
        borderRadius: 14,
        background: "rgba(7, 19, 36, .97)",
        color: "#eef8ff",
        boxShadow: "0 16px 50px rgba(0,0,0,.45)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <strong style={{display: "block", minWidth: 0}}>
          Current assessment
        </strong>
        <button
          type="button"
          data-assessment-active-run-toggle="true"
          aria-controls="nico-current-assessment-controls"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
          style={{
            flex: "0 0 auto",
            minHeight: 36,
            border: "1px solid rgba(125, 211, 252, .5)",
            borderRadius: 999,
            padding: "6px 12px",
            background: "#082f49",
            color: "#cffafe",
            font: "inherit",
            fontWeight: 800,
          }}
        >
          {collapsed ? "Show" : "Hide"}
        </button>
      </div>

      {!collapsed ? (
        <div id="nico-current-assessment-controls">
          {runId ? (
            <code
              style={{
                display: "block",
                marginTop: 8,
                marginBottom: 10,
                overflowWrap: "anywhere",
              }}
            >
              Run: {runId}
            </code>
          ) : null}
          <button
            type="button"
            onClick={clearCurrentRun}
            data-assessment-clear-current-run="true"
            style={{width: "100%", minHeight: 42}}
          >
            Clear current run and start new assessment
          </button>
        </div>
      ) : null}
    </aside>
  );
}
