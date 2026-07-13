"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const ACTIVE_RUN_KEY = "nico.mid.active_run";
const MID_RUN_EVENT = "nico:mid-run-selected";

export type MidStage = "start" | "review" | "report" | "approval" | "delivery";

type MidWorkspaceValue = {
  runId: string;
  setRunId: (value: string) => void;
  customerId: string;
  setCustomerId: (value: string) => void;
  projectId: string;
  setProjectId: (value: string) => void;
  adminToken: string;
  setAdminToken: (value: string) => void;
  reviewer: string;
  setReviewer: (value: string) => void;
  buildHref: (path: string) => string;
  identityReady: boolean;
};

const MidWorkspaceContext = createContext<MidWorkspaceValue | null>(null);

function safeSessionRunId(): string {
  try {
    const value = window.sessionStorage.getItem(ACTIVE_RUN_KEY) || "";
    return value.startsWith("midrun_") ? value : "";
  } catch {
    return "";
  }
}

function queryValue(name: string): string {
  try {
    return new URLSearchParams(window.location.search).get(name)?.trim() || "";
  } catch {
    return "";
  }
}

export function MidWorkspaceProvider({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const [runId, setRunIdState] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [adminToken, setAdminToken] = useState("");
  const [reviewer, setReviewer] = useState("");

  const setRunId = useCallback((value: string) => {
    const normalized = value.trim();
    setRunIdState(normalized);
    if (!normalized.startsWith("midrun_")) return;
    try {
      window.sessionStorage.setItem(ACTIVE_RUN_KEY, normalized);
    } catch {
      // Run identity remains available in React memory when session storage is unavailable.
    }
  }, []);

  useEffect(() => {
    const requestedRun = queryValue("run_id");
    const requestedCustomer = queryValue("customer_id");
    const requestedProject = queryValue("project_id");

    if (requestedRun.startsWith("midrun_")) setRunId(requestedRun);
    else if (!runId) {
      const retained = safeSessionRunId();
      if (retained) setRunIdState(retained);
    }
    if (requestedCustomer) setCustomerId(requestedCustomer);
    if (requestedProject) setProjectId(requestedProject);
  }, [pathname, runId, setRunId]);

  useEffect(() => {
    if (pathname !== "/" && pathname !== "/assessment") return;
    const synchronizeActiveRun = () => {
      const retained = safeSessionRunId();
      if (retained && retained !== runId) setRunIdState(retained);
    };
    synchronizeActiveRun();
    const timer = window.setInterval(synchronizeActiveRun, 500);
    return () => window.clearInterval(timer);
  }, [pathname, runId]);

  useEffect(() => {
    const onSelected = (event: Event) => {
      const detail = (event as CustomEvent<{run_id?: string}>).detail;
      const nextRunId = String(detail?.run_id || "").trim();
      if (nextRunId.startsWith("midrun_")) setRunId(nextRunId);
    };
    window.addEventListener(MID_RUN_EVENT, onSelected as EventListener);
    return () => window.removeEventListener(MID_RUN_EVENT, onSelected as EventListener);
  }, [setRunId]);

  const buildHref = useCallback((path: string) => {
    const params = new URLSearchParams();
    if (runId.trim()) params.set("run_id", runId.trim());
    if (customerId.trim()) params.set("customer_id", customerId.trim());
    if (projectId.trim()) params.set("project_id", projectId.trim());
    const query = params.toString();
    return query ? `${path}?${query}` : path;
  }, [runId, customerId, projectId]);

  const value = useMemo<MidWorkspaceValue>(() => ({
    runId,
    setRunId,
    customerId,
    setCustomerId,
    projectId,
    setProjectId,
    adminToken,
    setAdminToken,
    reviewer,
    setReviewer,
    buildHref,
    identityReady: runId.startsWith("midrun_") && Boolean(customerId.trim()) && Boolean(projectId.trim()),
  }), [runId, setRunId, customerId, projectId, adminToken, reviewer, buildHref]);

  return <MidWorkspaceContext.Provider value={value}>{children}</MidWorkspaceContext.Provider>;
}

export function useMidWorkspace(): MidWorkspaceValue {
  const value = useContext(MidWorkspaceContext);
  if (!value) throw new Error("useMidWorkspace must be used inside MidWorkspaceProvider");
  return value;
}

export function MidIdentityPanel({title = "Exact Mid workspace identity"}: {title?: string}) {
  const {
    runId,
    setRunId,
    customerId,
    setCustomerId,
    projectId,
    setProjectId,
    adminToken,
    setAdminToken,
    reviewer,
    setReviewer,
    identityReady,
  } = useMidWorkspace();

  return <section className="section panel mid-identity-panel">
    <div className="section-head">
      <div><p className="eyebrow">Shared workspace access</p><h2>{title}</h2></div>
      <span className={identityReady ? "status green" : "status gray"}>{identityReady ? "run selected" : "run required"}</span>
    </div>
    <p className="warning-box">Run and scope identity are shared across Mid stages. The NICO admin token and reviewer identity remain only in live React memory and are never written to the URL or browser storage.</p>
    <div className="form-grid">
      <label>Mid run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="midrun_..." /></label>
      <label>Customer ID<input value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
      <label>Project ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
      <label>Reviewer or operator<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Name or role" /></label>
      <label>NICO admin token<input type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
    </div>
  </section>;
}

const STAGES: Array<{key: MidStage; label: string; description: string; path: string}> = [
  {key: "start", label: "1. Start", description: "Create or continue the exact Mid run.", path: "/assessment?tier=mid#assessment"},
  {key: "review", label: "2. Review", description: "Inspect exceptions and missing evidence.", path: "/mid-review"},
  {key: "report", label: "3. Report", description: "Generate the bound draft artifact.", path: "/mid-report"},
  {key: "approval", label: "4. Approval", description: "Record item decisions and approve exact state.", path: "/mid-approval"},
  {key: "delivery", label: "5. Delivery", description: "Create controlled access after approval.", path: "/mid-delivery-admin"},
];

export function MidStageNavigation({current}: {current: MidStage}) {
  const {buildHref, identityReady} = useMidWorkspace();
  return <section className="section panel mid-stage-shell" aria-label="Mid Assessment workflow stages">
    <div className="section-head">
      <div><p className="eyebrow">Mid Assessment workspace</p><h2>Start → Review → Report → Approval → Delivery</h2></div>
      <Link className="secondary-link" href={buildHref("/mid-assessment")}>Workspace overview</Link>
    </div>
    <div className="mid-stage-links">
      {STAGES.map((stage) => {
        const active = current === stage.key;
        const href = stage.key === "start" ? stage.path : buildHref(stage.path);
        return <Link
          href={href}
          key={stage.key}
          className={`mid-stage-link${active ? " active" : ""}`}
          aria-current={active ? "step" : undefined}
          data-stage={stage.key}
        >
          <b>{stage.label}</b>
          <span>{stage.description}</span>
          {stage.key !== "start" && !identityReady ? <small>Run identity required</small> : null}
        </Link>;
      })}
    </div>
  </section>;
}

export const MID_STAGE_DEFINITIONS = STAGES;
export const MID_RUN_SELECTED_EVENT = MID_RUN_EVENT;
