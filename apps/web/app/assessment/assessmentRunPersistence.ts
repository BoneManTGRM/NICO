import type {Locale} from "./assessmentTypes";

export type PersistedRun = {
  version: 1;
  runId: string;
  repository: string;
  client: string;
  project: string;
  customerId: string;
  projectId: string;
  startedAt: number;
  locale: Locale;
};

const ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1";
const ACTIVE_RUN_QUERY_KEY = "run_id";

function normalizePersistedRun(value: unknown): PersistedRun | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const runId = String(record.runId || "").trim();
  if (!runId) {
    return null;
  }
  const startedAt = Number(record.startedAt);
  return {
    version: 1,
    runId,
    repository: String(record.repository || ""),
    client: String(record.client || ""),
    project: String(record.project || ""),
    customerId: String(record.customerId || "default_customer"),
    projectId: String(record.projectId || "default_project"),
    startedAt:
      Number.isFinite(startedAt) && startedAt > 0 ? startedAt : Date.now(),
    locale: record.locale === "es-MX" ? "es-MX" : "en",
  };
}

export function readStoredRun(): PersistedRun | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    return raw ? normalizePersistedRun(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

export function readPersistedRun(): PersistedRun | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = readStoredRun();
  const urlRunId =
    new URL(window.location.href).searchParams
      .get(ACTIVE_RUN_QUERY_KEY)
      ?.trim() || "";
  if (!urlRunId) {
    return stored;
  }
  if (stored?.runId === urlRunId) {
    return stored;
  }
  return {
    version: 1,
    runId: urlRunId,
    repository: stored?.repository || "",
    client: stored?.client || "",
    project: stored?.project || "",
    customerId: stored?.customerId || "default_customer",
    projectId: stored?.projectId || "default_project",
    startedAt: stored?.startedAt || Date.now(),
    locale: stored?.locale || "en",
  };
}

export function clearPersistedRun(preserveExplicitUrl = false): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
  } catch {
    // URL cleanup remains the authoritative escape from a stale active job.
  }
  if (preserveExplicitUrl) {
    return;
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.delete(ACTIVE_RUN_QUERY_KEY);
  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

export function writePersistedRun(value: PersistedRun): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      ACTIVE_RUN_STORAGE_KEY,
      JSON.stringify(value),
    );
  } catch {
    // The URL remains the recovery source when browser storage is unavailable.
  }
  const url = new URL(window.location.href);
  url.searchParams.set("tier", "comprehensive");
  url.searchParams.set(ACTIVE_RUN_QUERY_KEY, value.runId);
  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}
