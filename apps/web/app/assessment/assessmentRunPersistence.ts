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
const EXACT_RUN_STORAGE_PREFIX = "nico.comprehensive.exact-run.v1.";
const ACTIVE_RUN_QUERY_KEY = "run_id";
const TERMINAL_URL_RUNS_IN_CURRENT_DOCUMENT = new Set<string>();

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

function exactRunStorageKey(runId: string): string {
  return `${EXACT_RUN_STORAGE_PREFIX}${encodeURIComponent(runId)}`;
}

function readStorageValue(key: string): PersistedRun | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? normalizePersistedRun(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

export function readStoredRun(): PersistedRun | null {
  return readStorageValue(ACTIVE_RUN_STORAGE_KEY);
}

function readExactStoredRun(runId: string): PersistedRun | null {
  const exact = readStorageValue(exactRunStorageKey(runId));
  if (exact?.runId === runId) {
    return exact;
  }
  const active = readStoredRun();
  return active?.runId === runId ? active : null;
}

export function readPersistedRun(): PersistedRun | null {
  if (typeof window === "undefined") {
    return null;
  }
  const urlRunId =
    new URL(window.location.href).searchParams
      .get(ACTIVE_RUN_QUERY_KEY)
      ?.trim() || "";
  if (!urlRunId) {
    return readStoredRun();
  }

  // A terminal exact run keeps its URL so a real reload can restore it. Within
  // the current document, however, pageshow/online events must not synthesize
  // that URL back into an active run and temporarily demote the terminal UI.
  if (TERMINAL_URL_RUNS_IN_CURRENT_DOCUMENT.has(urlRunId)) {
    return null;
  }

  const exact = readExactStoredRun(urlRunId);
  if (exact) {
    return exact;
  }

  // The URL is the exact-run authority. Never borrow repository, client,
  // project, or scope metadata from a different active run in another tab.
  return {
    version: 1,
    runId: urlRunId,
    repository: "",
    client: "",
    project: "",
    customerId: "default_customer",
    projectId: "default_project",
    startedAt: Date.now(),
    locale: "en",
  };
}

export function clearPersistedRun(preserveExplicitUrl = false): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  const urlRunId = url.searchParams.get(ACTIVE_RUN_QUERY_KEY)?.trim() || "";
  try {
    const active = readStoredRun();
    if (!urlRunId || !active || active.runId === urlRunId) {
      window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
    if (urlRunId) {
      window.localStorage.removeItem(exactRunStorageKey(urlRunId));
    }
  } catch {
    // URL cleanup remains the authoritative escape from a stale active job.
  }
  if (preserveExplicitUrl) {
    if (urlRunId) {
      TERMINAL_URL_RUNS_IN_CURRENT_DOCUMENT.add(urlRunId);
    }
    return;
  }
  if (urlRunId) {
    TERMINAL_URL_RUNS_IN_CURRENT_DOCUMENT.delete(urlRunId);
  }
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
  TERMINAL_URL_RUNS_IN_CURRENT_DOCUMENT.delete(value.runId);
  try {
    const encoded = JSON.stringify(value);
    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, encoded);
    window.localStorage.setItem(exactRunStorageKey(value.runId), encoded);
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
