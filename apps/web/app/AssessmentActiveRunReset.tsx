"use client";

import {useEffect, useRef, useState} from "react";

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const MOBILE_ACTIVE_RUN_QUERY = "(max-width: 760px), (pointer: coarse)";
const ACTIVE_RUN_CLEARANCE_ATTRIBUTE =
  "data-assessment-active-run-reset-visible";
const ACTIVE_RUN_CLEARANCE_PROPERTY = "--nico-active-run-reset-clearance";
const STUCK_RECOVERY_ATTRIBUTE =
  "data-comprehensive-stuck-run-recovery-visible";

type Copy = {
  ariaLabel: string;
  title: string;
  show: string;
  hide: string;
  run: string;
  clear: string;
  confirmClear: string;
};

const COPY: Record<"en" | "es", Copy> = {
  en: {
    ariaLabel: "Current assessment controls",
    title: "Current assessment",
    show: "Show",
    hide: "Hide",
    run: "Run",
    clear: "Clear current run and start new assessment",
    confirmClear:
      "Clear the current run and start a new assessment? The preserved run will no longer be the active browser run.",
  },
  es: {
    ariaLabel: "Controles de la evaluación actual",
    title: "Evaluación actual",
    show: "Mostrar",
    hide: "Ocultar",
    run: "Ejecución",
    clear: "Borrar la ejecución actual e iniciar una evaluación nueva",
    confirmClear:
      "¿Borrar la ejecución actual e iniciar una evaluación nueva? La ejecución conservada dejará de ser la ejecución activa del navegador.",
  },
};

function isSpanishRoute(): boolean {
  const path = window.location.pathname.toLowerCase();
  return path === "/es" || path.startsWith("/es/") || path === "/es-mx" || path.startsWith("/es-mx/");
}

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

function stuckRecoveryVisible(): boolean {
  return (
    document.documentElement.getAttribute(STUCK_RECOVERY_ATTRIBUTE) === "true" ||
    Boolean(document.querySelector('[data-comprehensive-stuck-run-recovery="true"]'))
  );
}

function activeAssessmentVisible(): boolean {
  if (stuckRecoveryVisible()) return false;
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
  const [spanish, setSpanish] = useState(false);
  const panelRef = useRef<HTMLElement | null>(null);
  const copy = COPY[spanish ? "es" : "en"];

  useEffect(() => {
    const inspect = () => {
      setVisible(activeAssessmentVisible());
      setRunId(savedRunId());
      setSpanish(isSpanishRoute());
    };
    const observer = new MutationObserver(inspect);
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: [STUCK_RECOVERY_ATTRIBUTE],
    });
    const interval = window.setInterval(inspect, 1000);
    window.addEventListener("storage", inspect);
    window.addEventListener("popstate", inspect);
    inspect();
    return () => {
      observer.disconnect();
      window.clearInterval(interval);
      window.removeEventListener("storage", inspect);
      window.removeEventListener("popstate", inspect);
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

  const confirmAndClear = () => {
    if (window.confirm(copy.confirmClear)) clearCurrentRun();
  };

  return (
    <aside
      ref={panelRef}
      data-assessment-active-run-reset="true"
      data-assessment-active-run-reset-collapsed={collapsed ? "true" : "false"}
      aria-label={copy.ariaLabel}
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
        <strong style={{display: "block", minWidth: 0}}>{copy.title}</strong>
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
          {collapsed ? copy.show : copy.hide}
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
              {copy.run}: {runId}
            </code>
          ) : null}
          <button
            type="button"
            onClick={confirmAndClear}
            data-assessment-clear-current-run="true"
            style={{width: "100%", minHeight: 42}}
          >
            {copy.clear}
          </button>
        </div>
      ) : null}
    </aside>
  );
}
