"use client";

import {FormEvent, useMemo, useState} from "react";
import styles from "./operations.module.css";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const CORRELATION_HEADER = "X-NICO-Correlation-ID";
const SEVERITIES = ["", "p0", "p1", "p2", "p3", "info"] as const;

type JsonRecord = Record<string, unknown>;

type DeploymentIdentity = {
  artifact_schema?: string;
  status?: string;
  provider?: string;
  frontend_commit?: string;
  backend_origin?: string;
  deployment_environment?: string;
  commit_identity_available?: boolean;
};

type ReadinessCheck = {
  id?: string;
  label?: string;
  status?: string;
  passed?: boolean;
  required?: boolean;
  remediation?: string;
  observed?: unknown;
};

type Readiness = {
  status?: string;
  operational_ready?: boolean;
  blockers?: string[];
  warnings?: string[];
  checks?: ReadinessCheck[];
  deployment?: {deployed_commit?: string; matches_expected_build?: boolean; build_marker?: string};
  storage?: {persistence_available?: boolean; database_configured?: boolean; warnings?: string[]};
  next_action?: string;
};

type WorkloadSummary = {
  total?: number;
  active?: number;
  queued?: number;
  oldest_queue_age_seconds?: number;
  status_counts?: Record<string, number>;
};

type DurationSummary = {
  sample_count?: number;
  p50?: number | null;
  p95?: number | null;
  max?: number | null;
};

type Observability = {
  status?: string;
  generated_at?: string;
  events_observed?: number;
  request_metrics?: {
    request_count?: number;
    failure_count?: number;
    failure_rate?: number;
    timeout_count?: number;
    timeout_rate?: number;
    latency_ms?: {p50?: number | null; p95?: number | null; max?: number | null};
    severity_counts?: Record<string, number>;
  };
  workloads?: {
    assessment_runs?: WorkloadSummary;
    scanner_runs?: WorkloadSummary;
    scanner_duration_seconds?: DurationSummary;
    report_generation_seconds?: DurationSummary;
  };
  event_pipeline?: {
    status?: string;
    write_failures?: number;
    read_failures?: number;
    storage_adapter?: string;
    persistence_available?: boolean;
    durability?: string;
  };
  storage?: {adapter?: string; persistence_available?: boolean; database_configured?: boolean};
  deployment?: {status?: string; deployed_commit?: string; matches_expected_build?: boolean; build_marker?: string};
  semantic_readiness?: {status?: string; operational_ready?: boolean; blockers?: string[]; warnings?: string[]};
};

type OperationalEvent = {
  event_id?: string;
  correlation_id?: string;
  event_name?: string;
  severity?: string;
  outcome?: string;
  occurred_at?: string;
  metadata?: {
    method?: string;
    route?: string;
    status_code?: number;
    duration_ms?: number;
    identifiers?: string[];
    error_class?: string;
  };
};

type EventsResponse = {
  status?: string;
  count?: number;
  limit?: number;
  events?: OperationalEvent[];
  event_pipeline?: {status?: string; write_failures?: number; read_failures?: number};
};

type OperationalAlert = {
  alert_id?: string;
  code?: string;
  title?: string;
  severity?: string;
  category?: string;
  evidence_status?: string;
  observed?: unknown;
  threshold?: unknown;
  evidence?: JsonRecord;
  operator_action?: string;
  auto_remediation_eligible?: boolean;
};

type AlertsResponse = {
  status?: string;
  highest_severity?: string;
  alert_count?: number;
  alerts?: OperationalAlert[];
  alert_set_sha256?: string;
  source_observability_sha256?: string;
};

class OperatorRequestError extends Error {
  correlationId: string;

  constructor(message: string, correlationId = "") {
    super(message);
    this.name = "OperatorRequestError";
    this.correlationId = correlationId;
  }
}

function statusTone(value?: string | boolean) {
  const status = String(value ?? "unavailable").toLowerCase();
  if (["ready", "ok", "clear", "success", "passed", "true", "durable", "available"].includes(status)) return styles.good;
  if (["degraded", "warning", "p2", "p3", "pending", "false"].includes(status)) return styles.warn;
  if (["blocked", "failed", "error", "alerting", "p0", "p1", "unavailable"].includes(status)) return styles.bad;
  return styles.neutral;
}

function formatPercent(value?: number) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "Unavailable";
}

function formatNumber(value?: number | null, suffix = "") {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toLocaleString()}${suffix}` : "Unavailable";
}

function shortSha(value?: string) {
  if (!value || value === "unavailable") return "Unavailable";
  return value.length > 12 ? value.slice(0, 12) : value;
}

function sameRelease(frontend?: string, backend?: string) {
  return Boolean(frontend && backend && frontend !== "unavailable" && backend !== "unavailable" && frontend === backend);
}

function jsonText(value: unknown) {
  return JSON.stringify(value ?? "Unavailable", null, 2);
}

export default function OperationsPage() {
  const [adminToken, setAdminToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [lastLoadedAt, setLastLoadedAt] = useState("");
  const [deployment, setDeployment] = useState<DeploymentIdentity | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [observability, setObservability] = useState<Observability | null>(null);
  const [events, setEvents] = useState<EventsResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [severityFilter, setSeverityFilter] = useState<(typeof SEVERITIES)[number]>("");
  const [correlationFilter, setCorrelationFilter] = useState("");

  const backendConfigured = Boolean(API_URL);
  const frontendCommit = deployment?.frontend_commit || "";
  const backendCommit = observability?.deployment?.deployed_commit || readiness?.deployment?.deployed_commit || "";
  const releasesAligned = sameRelease(frontendCommit, backendCommit);
  const metrics = observability?.request_metrics;
  const workloads = observability?.workloads;
  const severityCounts = metrics?.severity_counts || {};
  const activeAlertCounts = useMemo(() => {
    const counts: Record<string, number> = {p0: 0, p1: 0, p2: 0, p3: 0, info: 0};
    for (const item of alerts?.alerts || []) {
      const key = item.severity || "info";
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [alerts]);

  async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(url, {cache: "no-store", ...options});
    const responseCorrelation = response.headers.get(CORRELATION_HEADER) || "";
    if (responseCorrelation) setCorrelationId(responseCorrelation);
    let data: unknown = {};
    try {
      data = await response.json();
    } catch {
      throw new OperatorRequestError(`Operator endpoint returned invalid JSON (${response.status}).`, responseCorrelation);
    }
    if (!response.ok) {
      const payload = data as {detail?: {message?: string; code?: string}; message?: string; error?: string};
      const message = payload?.detail?.message || payload?.message || payload?.error || `Operator request failed (${response.status}).`;
      throw new OperatorRequestError(message, responseCorrelation);
    }
    return data as T;
  }

  function operatorHeaders() {
    return {"X-NICO-Admin-Token": adminToken};
  }

  async function loadControlCenter(event?: FormEvent) {
    event?.preventDefault();
    if (!backendConfigured) {
      setError("NEXT_PUBLIC_NICO_API_URL is not configured for this Vercel deployment.");
      return;
    }
    if (!adminToken.trim()) {
      setError("Enter the operator admin token. It remains only in this page's memory and is not saved.");
      return;
    }
    setLoading(true);
    setError("");
    setCorrelationId("");
    try {
      const frontend = await fetchJson<DeploymentIdentity>("/api/deployment");
      const eventParams = new URLSearchParams({limit: "100"});
      if (severityFilter) eventParams.set("severity", severityFilter);
      if (correlationFilter.trim()) eventParams.set("correlation_id", correlationFilter.trim());
      const alertParams = new URLSearchParams({event_window: "500"});
      if (frontend.frontend_commit && frontend.frontend_commit !== "unavailable") {
        alertParams.set("frontend_commit", frontend.frontend_commit);
      }

      const [readinessPayload, observabilityPayload, eventsPayload, alertsPayload] = await Promise.all([
        fetchJson<Readiness>(`${API_URL}/operations/readiness`),
        fetchJson<Observability>(`${API_URL}/operations/observability?event_window=500`, {headers: operatorHeaders()}),
        fetchJson<EventsResponse>(`${API_URL}/operations/events?${eventParams.toString()}`, {headers: operatorHeaders()}),
        fetchJson<AlertsResponse>(`${API_URL}/operations/alerts?${alertParams.toString()}`, {headers: operatorHeaders()}),
      ]);

      setDeployment(frontend);
      setReadiness(readinessPayload);
      setObservability(observabilityPayload);
      setEvents(eventsPayload);
      setAlerts(alertsPayload);
      setLastLoadedAt(new Date().toISOString());
    } catch (requestError) {
      const normalized = requestError instanceof Error ? requestError : new Error("Operator control center request failed.");
      setError(normalized.message);
      if (normalized instanceof OperatorRequestError && normalized.correlationId) {
        setCorrelationId(normalized.correlationId);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.shell}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>NICO Operations</p>
          <h1>Operator Control Center</h1>
          <p className={styles.lead}>Current deployment, readiness, reliability, workload pressure, incident events, and deterministic alerts in one evidence-bound view.</p>
        </div>
        <div className={styles.heroState}>
          <span className={`${styles.pill} ${statusTone(readiness?.status)}`}>Readiness: {readiness?.status || "not loaded"}</span>
          <span className={`${styles.pill} ${statusTone(alerts?.highest_severity || "neutral")}`}>Highest alert: {alerts?.highest_severity || "not loaded"}</span>
        </div>
      </section>

      <section className={styles.securityPanel}>
        <div>
          <h2>Operator authentication</h2>
          <p>The admin token is held only in React memory for this open page. It is never placed in a URL, cookie, localStorage, sessionStorage, or build output.</p>
        </div>
        <form className={styles.authForm} onSubmit={loadControlCenter}>
          <label>
            Admin token
            <input
              type="password"
              value={adminToken}
              onChange={(event) => setAdminToken(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              placeholder="Enter NICO_ADMIN_TOKEN"
            />
          </label>
          <button type="submit" disabled={loading || !backendConfigured}>{loading ? "Loading evidence..." : "Load operations"}</button>
        </form>
        {!backendConfigured ? <div className={styles.error}>Backend URL is not configured in Vercel.</div> : null}
        {error ? <div className={styles.error}>{error}</div> : null}
        {correlationId ? <div className={styles.correlation}>Correlation ID: <code>{correlationId}</code></div> : null}
        {lastLoadedAt ? <p className={styles.timestamp}>Last loaded: {new Date(lastLoadedAt).toLocaleString()}</p> : null}
      </section>

      <section className={styles.gridFour} aria-label="Primary operations status">
        <article className={styles.metricCard}>
          <span>Semantic readiness</span>
          <strong className={statusTone(readiness?.status)}>{readiness?.status || "Unavailable"}</strong>
          <small>{readiness?.operational_ready === true ? "Required production checks passed" : "Trusted work remains blocked or unverified"}</small>
        </article>
        <article className={styles.metricCard}>
          <span>Release alignment</span>
          <strong className={releasesAligned ? styles.good : styles.bad}>{releasesAligned ? "Aligned" : "Unverified"}</strong>
          <small>Frontend {shortSha(frontendCommit)} · Backend {shortSha(backendCommit)}</small>
        </article>
        <article className={styles.metricCard}>
          <span>Durable storage</span>
          <strong className={statusTone(observability?.storage?.persistence_available)}>{observability?.storage?.persistence_available === true ? "Durable" : "Unavailable"}</strong>
          <small>{observability?.storage?.adapter || "Unknown adapter"}</small>
        </article>
        <article className={styles.metricCard}>
          <span>Alert state</span>
          <strong className={statusTone(alerts?.highest_severity)}>{alerts ? `${alerts.alert_count || 0} active` : "Unavailable"}</strong>
          <small>Highest severity: {alerts?.highest_severity || "unavailable"}</small>
        </article>
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Deployment identity</p><h2>Frontend and backend release</h2></div>
          <span className={`${styles.pill} ${releasesAligned ? styles.good : styles.bad}`}>{releasesAligned ? "same exact SHA" : "mismatch or unavailable"}</span>
        </div>
        <div className={styles.gridThree}>
          <article className={styles.detailCard}><span>Vercel frontend</span><b>{shortSha(frontendCommit)}</b><small>{deployment?.provider || "unknown provider"} · {deployment?.deployment_environment || "unknown environment"}</small></article>
          <article className={styles.detailCard}><span>Railway backend</span><b>{shortSha(backendCommit)}</b><small>{observability?.deployment?.status || "unavailable"} · build {observability?.deployment?.build_marker || "unavailable"}</small></article>
          <article className={styles.detailCard}><span>Expected build match</span><b className={statusTone(observability?.deployment?.matches_expected_build)}>{observability?.deployment?.matches_expected_build === true ? "Verified" : "Unavailable"}</b><small>HTTP reachability alone does not establish release integrity.</small></article>
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Reliability</p><h2>Request and event pipeline health</h2></div>
          <span className={`${styles.pill} ${statusTone(observability?.event_pipeline?.status)}`}>Pipeline: {observability?.event_pipeline?.status || "unavailable"}</span>
        </div>
        <div className={styles.gridFour}>
          <article className={styles.metricCard}><span>Requests</span><strong>{formatNumber(metrics?.request_count)}</strong><small>{formatNumber(observability?.events_observed)} events observed</small></article>
          <article className={styles.metricCard}><span>Failure rate</span><strong className={(metrics?.failure_rate || 0) >= 0.05 ? styles.bad : styles.good}>{formatPercent(metrics?.failure_rate)}</strong><small>{formatNumber(metrics?.failure_count)} server failures</small></article>
          <article className={styles.metricCard}><span>Timeout rate</span><strong className={(metrics?.timeout_rate || 0) >= 0.02 ? styles.warn : styles.good}>{formatPercent(metrics?.timeout_rate)}</strong><small>{formatNumber(metrics?.timeout_count)} timeouts</small></article>
          <article className={styles.metricCard}><span>P95 latency</span><strong>{formatNumber(metrics?.latency_ms?.p95, " ms")}</strong><small>P50 {formatNumber(metrics?.latency_ms?.p50, " ms")} · Max {formatNumber(metrics?.latency_ms?.max, " ms")}</small></article>
        </div>
        <div className={styles.gridThree}>
          <article className={styles.detailCard}><span>Event writes failed</span><b className={(observability?.event_pipeline?.write_failures || 0) > 0 ? styles.bad : styles.good}>{formatNumber(observability?.event_pipeline?.write_failures)}</b><small>Expected: 0</small></article>
          <article className={styles.detailCard}><span>Event reads failed</span><b className={(observability?.event_pipeline?.read_failures || 0) > 0 ? styles.warn : styles.good}>{formatNumber(observability?.event_pipeline?.read_failures)}</b><small>Expected: 0</small></article>
          <article className={styles.detailCard}><span>Event durability</span><b className={statusTone(observability?.event_pipeline?.durability)}>{observability?.event_pipeline?.durability || "Unavailable"}</b><small>{observability?.event_pipeline?.storage_adapter || "unknown adapter"}</small></article>
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Capacity</p><h2>Assessment and scanner workloads</h2></div>
          <span className={`${styles.pill} ${statusTone(observability?.status)}`}>Observability: {observability?.status || "unavailable"}</span>
        </div>
        <div className={styles.gridTwo}>
          <article className={styles.workloadCard}>
            <div className={styles.cardHead}><div><span>Assessment runs</span><b>{formatNumber(workloads?.assessment_runs?.total)} total</b></div><span className={styles.counter}>{formatNumber(workloads?.assessment_runs?.queued)} queued</span></div>
            <div className={styles.statRow}><span>Active</span><b>{formatNumber(workloads?.assessment_runs?.active)}</b></div>
            <div className={styles.statRow}><span>Oldest queue age</span><b>{formatNumber(workloads?.assessment_runs?.oldest_queue_age_seconds, " sec")}</b></div>
            <pre>{jsonText(workloads?.assessment_runs?.status_counts)}</pre>
          </article>
          <article className={styles.workloadCard}>
            <div className={styles.cardHead}><div><span>Scanner runs</span><b>{formatNumber(workloads?.scanner_runs?.total)} total</b></div><span className={styles.counter}>{formatNumber(workloads?.scanner_runs?.queued)} queued</span></div>
            <div className={styles.statRow}><span>Active</span><b>{formatNumber(workloads?.scanner_runs?.active)}</b></div>
            <div className={styles.statRow}><span>Oldest queue age</span><b>{formatNumber(workloads?.scanner_runs?.oldest_queue_age_seconds, " sec")}</b></div>
            <pre>{jsonText(workloads?.scanner_runs?.status_counts)}</pre>
          </article>
        </div>
        <div className={styles.gridTwo}>
          <article className={styles.detailCard}><span>Scanner duration</span><b>P50 {formatNumber(workloads?.scanner_duration_seconds?.p50, " sec")}</b><small>P95 {formatNumber(workloads?.scanner_duration_seconds?.p95, " sec")} · Max {formatNumber(workloads?.scanner_duration_seconds?.max, " sec")}</small></article>
          <article className={styles.detailCard}><span>Report generation</span><b>P50 {formatNumber(workloads?.report_generation_seconds?.p50, " sec")}</b><small>P95 {formatNumber(workloads?.report_generation_seconds?.p95, " sec")} · Max {formatNumber(workloads?.report_generation_seconds?.max, " sec")}</small></article>
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Deterministic alerts</p><h2>Active operator actions</h2></div>
          <span className={`${styles.pill} ${statusTone(alerts?.highest_severity)}`}>{alerts?.alert_count ?? "Unavailable"} alerts</span>
        </div>
        <div className={styles.severityStrip}>
          {(["p0", "p1", "p2", "p3"] as const).map((severity) => <div key={severity}><span>{severity.toUpperCase()}</span><b className={statusTone(severity)}>{activeAlertCounts[severity] || 0}</b><small>Events: {severityCounts[severity] || 0}</small></div>)}
        </div>
        {alerts?.alerts?.length ? <div className={styles.alertList}>{alerts.alerts.map((alert) => (
          <article className={styles.alertCard} key={alert.alert_id || alert.code}>
            <div className={styles.cardHead}><div><span>{alert.category || "operations"}</span><b>{alert.title || alert.code}</b></div><span className={`${styles.pill} ${statusTone(alert.severity)}`}>{alert.severity || "unknown"}</span></div>
            <p>{alert.operator_action}</p>
            <div className={styles.alertEvidence}><div><span>Observed</span><pre>{jsonText(alert.observed)}</pre></div><div><span>Threshold</span><pre>{jsonText(alert.threshold)}</pre></div></div>
            <small>Evidence: {alert.evidence_status || "unavailable"} · Automatic remediation: {alert.auto_remediation_eligible ? "eligible" : "not allowed"}</small>
          </article>
        ))}</div> : <div className={styles.emptyState}>{alerts ? "No deterministic alerts are active for the loaded evidence." : "Load operations to evaluate alerts."}</div>}
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Incident events</p><h2>Search by severity or correlation ID</h2></div>
          <span className={`${styles.pill} ${statusTone(events?.event_pipeline?.status)}`}>{events?.count ?? 0} shown</span>
        </div>
        <form className={styles.filters} onSubmit={loadControlCenter}>
          <label>Severity<select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as (typeof SEVERITIES)[number])}>{SEVERITIES.map((severity) => <option value={severity} key={severity || "all"}>{severity ? severity.toUpperCase() : "All severities"}</option>)}</select></label>
          <label>Correlation ID<input value={correlationFilter} onChange={(event) => setCorrelationFilter(event.target.value)} placeholder="corr_..." maxLength={128} spellCheck={false} /></label>
          <button type="submit" disabled={loading || !adminToken.trim()}>Apply filters</button>
        </form>
        {events?.events?.length ? <div className={styles.eventTable} role="table" aria-label="Operational events">
          <div className={styles.eventHeader} role="row"><span>Severity</span><span>Event</span><span>Route</span><span>Status / duration</span><span>Correlation</span><span>Time</span></div>
          {events.events.map((item, index) => <div className={styles.eventRow} role="row" key={item.event_id || `${item.correlation_id}-${index}`}>
            <span><b className={`${styles.pill} ${statusTone(item.severity)}`}>{item.severity || "unknown"}</b></span>
            <span><b>{item.event_name || "unknown"}</b><small>{item.outcome || "unknown outcome"}</small></span>
            <span><code>{item.metadata?.method || "?"} {item.metadata?.route || "unavailable"}</code></span>
            <span>{formatNumber(item.metadata?.status_code)} · {formatNumber(item.metadata?.duration_ms, " ms")}</span>
            <span><code>{item.correlation_id || "unavailable"}</code></span>
            <span>{item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "Unavailable"}</span>
          </div>)}
        </div> : <div className={styles.emptyState}>{events ? "No events matched the bounded filters." : "Load operations to view recent events."}</div>}
      </section>

      <section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><p className={styles.eyebrow}>Readiness checks</p><h2>Required production boundaries</h2></div>
          <span className={`${styles.pill} ${statusTone(readiness?.status)}`}>{readiness?.status || "unavailable"}</span>
        </div>
        {readiness?.checks?.length ? <div className={styles.checkList}>{readiness.checks.map((check) => <article className={styles.checkCard} key={check.id}>
          <div className={styles.cardHead}><div><span>{check.required ? "required" : "advisory"}</span><b>{check.label || check.id}</b></div><span className={`${styles.pill} ${statusTone(check.status)}`}>{check.status || "unknown"}</span></div>
          {check.remediation ? <p>{check.remediation}</p> : <p className={styles.goodText}>No remediation is required for this check.</p>}
        </article>)}</div> : <div className={styles.emptyState}>Readiness checks are unavailable until the control center is loaded.</div>}
        {readiness?.next_action ? <div className={styles.nextAction}><b>Next operator action</b><p>{readiness.next_action}</p></div> : null}
      </section>
    </main>
  );
}
