"use client";

import styles from "./operations.module.css";
import {SEVERITIES, SeverityFilter} from "./operations-types";
import {
  OperationsControlCenterController,
  useOperationsControlCenter,
} from "./use-operations-control-center";

const ALERT_SEVERITIES = ["p0", "p1", "p2", "p3"] as const;

type ControllerProps = {
  controller: OperationsControlCenterController;
};

function statusTone(value?: string | boolean) {
  const status = String(value ?? "unavailable").toLowerCase();
  if (
    [
      "ready",
      "ok",
      "clear",
      "success",
      "passed",
      "true",
      "durable",
      "available",
    ].includes(status)
  ) {
    return styles.good;
  }
  if (["degraded", "warning", "p2", "p3", "pending", "false"].includes(status)) {
    return styles.warn;
  }
  if (
    [
      "blocked",
      "failed",
      "error",
      "alerting",
      "p0",
      "p1",
      "unavailable",
    ].includes(status)
  ) {
    return styles.bad;
  }
  return styles.neutral;
}

function formatPercent(value?: number) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(2)}%`
    : "Unavailable";
}

function formatNumber(value?: number | null, suffix = "") {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString()}${suffix}`
    : "Unavailable";
}

function shortSha(value?: string) {
  if (!value || value === "unavailable") {
    return "Unavailable";
  }
  return value.length > 12 ? value.slice(0, 12) : value;
}

function jsonText(value: unknown) {
  return JSON.stringify(value ?? "Unavailable", null, 2);
}

function OperationsHero({controller}: ControllerProps) {
  return (
    <section className={styles.hero}>
      <div>
        <p className={styles.eyebrow}>NICO Operations</p>
        <h1>Operator Control Center</h1>
        <p className={styles.lead}>
          Current deployment, readiness, reliability, workload pressure, incident
          events, and deterministic alerts in one evidence-bound view.
        </p>
      </div>
      <div className={styles.heroState}>
        <span
          className={`${styles.pill} ${statusTone(controller.readiness?.status)}`}
        >
          Readiness: {controller.readiness?.status || "not loaded"}
        </span>
        <span
          className={`${styles.pill} ${statusTone(
            controller.alerts?.highest_severity || "neutral",
          )}`}
        >
          Highest alert: {controller.alerts?.highest_severity || "not loaded"}
        </span>
      </div>
    </section>
  );
}

function AuthenticationPanel({controller}: ControllerProps) {
  return (
    <section className={styles.securityPanel}>
      <div>
        <h2>Operator authentication</h2>
        <p>
          The admin token is held only in React memory for this open page. It is
          never placed in a URL, cookie, localStorage, sessionStorage, or build
          output.
        </p>
      </div>
      <form className={styles.authForm} onSubmit={controller.loadControlCenter}>
        <label>
          Admin token
          <input
            type="password"
            value={controller.adminToken}
            onChange={(event) => controller.setAdminToken(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            placeholder="Enter NICO_ADMIN_TOKEN"
          />
        </label>
        <button
          type="submit"
          disabled={controller.loading || !controller.backendConfigured}
        >
          {controller.loading ? "Loading evidence..." : "Load operations"}
        </button>
      </form>
      {!controller.backendConfigured ? (
        <div className={styles.error}>Backend URL is not configured in Vercel.</div>
      ) : null}
      {controller.error ? <div className={styles.error}>{controller.error}</div> : null}
      {controller.correlationId ? (
        <div className={styles.correlation}>
          Correlation ID: <code>{controller.correlationId}</code>
        </div>
      ) : null}
      {controller.lastLoadedAt ? (
        <p className={styles.timestamp}>
          Last loaded: {new Date(controller.lastLoadedAt).toLocaleString()}
        </p>
      ) : null}
    </section>
  );
}

function PrimaryStatusPanel({controller}: ControllerProps) {
  return (
    <section className={styles.gridFour} aria-label="Primary operations status">
      <article className={styles.metricCard}>
        <span>Semantic readiness</span>
        <strong className={statusTone(controller.readiness?.status)}>
          {controller.readiness?.status || "Unavailable"}
        </strong>
        <small>
          {controller.readiness?.operational_ready === true
            ? "Required production checks passed"
            : "Trusted work remains blocked or unverified"}
        </small>
      </article>
      <article className={styles.metricCard}>
        <span>Release alignment</span>
        <strong
          className={controller.releasesAligned ? styles.good : styles.bad}
        >
          {controller.releasesAligned ? "Aligned" : "Unverified"}
        </strong>
        <small>
          Frontend {shortSha(controller.frontendCommit)} · Backend{" "}
          {shortSha(controller.backendCommit)}
        </small>
      </article>
      <article className={styles.metricCard}>
        <span>Durable storage</span>
        <strong
          className={statusTone(
            controller.observability?.storage?.persistence_available,
          )}
        >
          {controller.observability?.storage?.persistence_available === true
            ? "Durable"
            : "Unavailable"}
        </strong>
        <small>{controller.observability?.storage?.adapter || "Unknown adapter"}</small>
      </article>
      <article className={styles.metricCard}>
        <span>Alert state</span>
        <strong className={statusTone(controller.alerts?.highest_severity)}>
          {controller.alerts
            ? `${controller.alerts.alert_count || 0} active`
            : "Unavailable"}
        </strong>
        <small>
          Highest severity: {controller.alerts?.highest_severity || "unavailable"}
        </small>
      </article>
    </section>
  );
}

function DeploymentPanel({controller}: ControllerProps) {
  const deployment = controller.deployment;
  const observability = controller.observability;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Deployment identity</p>
          <h2>Frontend and backend release</h2>
        </div>
        <span
          className={`${styles.pill} ${
            controller.releasesAligned ? styles.good : styles.bad
          }`}
        >
          {controller.releasesAligned
            ? "same exact SHA"
            : "mismatch or unavailable"}
        </span>
      </div>
      <div className={styles.gridThree}>
        <article className={styles.detailCard}>
          <span>Vercel frontend</span>
          <b>{shortSha(controller.frontendCommit)}</b>
          <small>
            {deployment?.provider || "unknown provider"} ·{" "}
            {deployment?.deployment_environment || "unknown environment"}
          </small>
        </article>
        <article className={styles.detailCard}>
          <span>Railway backend</span>
          <b>{shortSha(controller.backendCommit)}</b>
          <small>
            {observability?.deployment?.status || "unavailable"} · build{" "}
            {observability?.deployment?.build_marker || "unavailable"}
          </small>
        </article>
        <article className={styles.detailCard}>
          <span>Expected build match</span>
          <b
            className={statusTone(
              observability?.deployment?.matches_expected_build,
            )}
          >
            {observability?.deployment?.matches_expected_build === true
              ? "Verified"
              : "Unavailable"}
          </b>
          <small>HTTP reachability alone does not establish release integrity.</small>
        </article>
      </div>
    </section>
  );
}

function ReliabilityPanel({controller}: ControllerProps) {
  const metrics = controller.metrics;
  const observability = controller.observability;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Reliability</p>
          <h2>Request and event pipeline health</h2>
        </div>
        <span
          className={`${styles.pill} ${statusTone(
            observability?.event_pipeline?.status,
          )}`}
        >
          Pipeline: {observability?.event_pipeline?.status || "unavailable"}
        </span>
      </div>
      <div className={styles.gridFour}>
        <article className={styles.metricCard}>
          <span>Requests</span>
          <strong>{formatNumber(metrics?.request_count)}</strong>
          <small>{formatNumber(observability?.events_observed)} events observed</small>
        </article>
        <article className={styles.metricCard}>
          <span>Failure rate</span>
          <strong
            className={(metrics?.failure_rate || 0) >= 0.05 ? styles.bad : styles.good}
          >
            {formatPercent(metrics?.failure_rate)}
          </strong>
          <small>{formatNumber(metrics?.failure_count)} server failures</small>
        </article>
        <article className={styles.metricCard}>
          <span>Timeout rate</span>
          <strong
            className={(metrics?.timeout_rate || 0) >= 0.02 ? styles.warn : styles.good}
          >
            {formatPercent(metrics?.timeout_rate)}
          </strong>
          <small>{formatNumber(metrics?.timeout_count)} timeouts</small>
        </article>
        <article className={styles.metricCard}>
          <span>P95 latency</span>
          <strong>{formatNumber(metrics?.latency_ms?.p95, " ms")}</strong>
          <small>
            P50 {formatNumber(metrics?.latency_ms?.p50, " ms")} · Max{" "}
            {formatNumber(metrics?.latency_ms?.max, " ms")}
          </small>
        </article>
      </div>
      <div className={styles.gridThree}>
        <article className={styles.detailCard}>
          <span>Event writes failed</span>
          <b
            className={
              (observability?.event_pipeline?.write_failures || 0) > 0
                ? styles.bad
                : styles.good
            }
          >
            {formatNumber(observability?.event_pipeline?.write_failures)}
          </b>
          <small>Expected: 0</small>
        </article>
        <article className={styles.detailCard}>
          <span>Event reads failed</span>
          <b
            className={
              (observability?.event_pipeline?.read_failures || 0) > 0
                ? styles.warn
                : styles.good
            }
          >
            {formatNumber(observability?.event_pipeline?.read_failures)}
          </b>
          <small>Expected: 0</small>
        </article>
        <article className={styles.detailCard}>
          <span>Event durability</span>
          <b className={statusTone(observability?.event_pipeline?.durability)}>
            {observability?.event_pipeline?.durability || "Unavailable"}
          </b>
          <small>
            {observability?.event_pipeline?.storage_adapter || "unknown adapter"}
          </small>
        </article>
      </div>
    </section>
  );
}

function CapacityPanel({controller}: ControllerProps) {
  const workloads = controller.workloads;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Capacity</p>
          <h2>Assessment and scanner workloads</h2>
        </div>
        <span
          className={`${styles.pill} ${statusTone(controller.observability?.status)}`}
        >
          Observability: {controller.observability?.status || "unavailable"}
        </span>
      </div>
      <div className={styles.gridTwo}>
        <article className={styles.workloadCard}>
          <div className={styles.cardHead}>
            <div>
              <span>Assessment runs</span>
              <b>{formatNumber(workloads?.assessment_runs?.total)} total</b>
            </div>
            <span className={styles.counter}>
              {formatNumber(workloads?.assessment_runs?.queued)} queued
            </span>
          </div>
          <div className={styles.statRow}>
            <span>Active</span>
            <b>{formatNumber(workloads?.assessment_runs?.active)}</b>
          </div>
          <div className={styles.statRow}>
            <span>Oldest queue age</span>
            <b>
              {formatNumber(
                workloads?.assessment_runs?.oldest_queue_age_seconds,
                " sec",
              )}
            </b>
          </div>
          <pre>{jsonText(workloads?.assessment_runs?.status_counts)}</pre>
        </article>
        <article className={styles.workloadCard}>
          <div className={styles.cardHead}>
            <div>
              <span>Scanner runs</span>
              <b>{formatNumber(workloads?.scanner_runs?.total)} total</b>
            </div>
            <span className={styles.counter}>
              {formatNumber(workloads?.scanner_runs?.queued)} queued
            </span>
          </div>
          <div className={styles.statRow}>
            <span>Active</span>
            <b>{formatNumber(workloads?.scanner_runs?.active)}</b>
          </div>
          <div className={styles.statRow}>
            <span>Oldest queue age</span>
            <b>
              {formatNumber(
                workloads?.scanner_runs?.oldest_queue_age_seconds,
                " sec",
              )}
            </b>
          </div>
          <pre>{jsonText(workloads?.scanner_runs?.status_counts)}</pre>
        </article>
      </div>
      <div className={styles.gridTwo}>
        <article className={styles.detailCard}>
          <span>Scanner duration</span>
          <b>
            P50 {formatNumber(workloads?.scanner_duration_seconds?.p50, " sec")}
          </b>
          <small>
            P95 {formatNumber(workloads?.scanner_duration_seconds?.p95, " sec")} ·
            Max {formatNumber(workloads?.scanner_duration_seconds?.max, " sec")}
          </small>
        </article>
        <article className={styles.detailCard}>
          <span>Report generation</span>
          <b>
            P50 {formatNumber(workloads?.report_generation_seconds?.p50, " sec")}
          </b>
          <small>
            P95 {formatNumber(workloads?.report_generation_seconds?.p95, " sec")} ·
            Max {formatNumber(workloads?.report_generation_seconds?.max, " sec")}
          </small>
        </article>
      </div>
    </section>
  );
}

function AlertsPanel({controller}: ControllerProps) {
  const alerts = controller.alerts;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Deterministic alerts</p>
          <h2>Active operator actions</h2>
        </div>
        <span
          className={`${styles.pill} ${statusTone(alerts?.highest_severity)}`}
        >
          {alerts?.alert_count ?? "Unavailable"} alerts
        </span>
      </div>
      <div className={styles.severityStrip}>
        {ALERT_SEVERITIES.map((severity) => (
          <div key={severity}>
            <span>{severity.toUpperCase()}</span>
            <b className={statusTone(severity)}>
              {controller.activeAlertCounts[severity] || 0}
            </b>
            <small>Events: {controller.severityCounts[severity] || 0}</small>
          </div>
        ))}
      </div>
      {alerts?.alerts?.length ? (
        <div className={styles.alertList}>
          {alerts.alerts.map((alert) => (
            <article
              className={styles.alertCard}
              key={alert.alert_id || alert.code}
            >
              <div className={styles.cardHead}>
                <div>
                  <span>{alert.category || "operations"}</span>
                  <b>{alert.title || alert.code}</b>
                </div>
                <span
                  className={`${styles.pill} ${statusTone(alert.severity)}`}
                >
                  {alert.severity || "unknown"}
                </span>
              </div>
              <p>{alert.operator_action}</p>
              <div className={styles.alertEvidence}>
                <div>
                  <span>Observed</span>
                  <pre>{jsonText(alert.observed)}</pre>
                </div>
                <div>
                  <span>Threshold</span>
                  <pre>{jsonText(alert.threshold)}</pre>
                </div>
              </div>
              <small>
                Evidence: {alert.evidence_status || "unavailable"} · Automatic
                remediation:{" "}
                {alert.auto_remediation_eligible ? "eligible" : "not allowed"}
              </small>
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          {alerts
            ? "No deterministic alerts are active for the loaded evidence."
            : "Load operations to evaluate alerts."}
        </div>
      )}
    </section>
  );
}

function EventsPanel({controller}: ControllerProps) {
  const events = controller.events;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Incident events</p>
          <h2>Search by severity or correlation ID</h2>
        </div>
        <span
          className={`${styles.pill} ${statusTone(events?.event_pipeline?.status)}`}
        >
          {events?.count ?? 0} shown
        </span>
      </div>
      <form className={styles.filters} onSubmit={controller.loadControlCenter}>
        <label>
          Severity
          <select
            value={controller.severityFilter}
            onChange={(event) =>
              controller.setSeverityFilter(event.target.value as SeverityFilter)
            }
          >
            {SEVERITIES.map((severity) => (
              <option value={severity} key={severity || "all"}>
                {severity ? severity.toUpperCase() : "All severities"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Correlation ID
          <input
            value={controller.correlationFilter}
            onChange={(event) =>
              controller.setCorrelationFilter(event.target.value)
            }
            placeholder="corr_..."
            maxLength={128}
            spellCheck={false}
          />
        </label>
        <button
          type="submit"
          disabled={controller.loading || !controller.adminToken.trim()}
        >
          Apply filters
        </button>
      </form>
      {events?.events?.length ? (
        <div
          className={styles.eventTable}
          role="table"
          aria-label="Operational events"
        >
          <div className={styles.eventHeader} role="row">
            <span>Severity</span>
            <span>Event</span>
            <span>Route</span>
            <span>Status / duration</span>
            <span>Correlation</span>
            <span>Time</span>
          </div>
          {events.events.map((item, index) => (
            <div
              className={styles.eventRow}
              role="row"
              key={item.event_id || `${item.correlation_id}-${index}`}
            >
              <span>
                <b className={`${styles.pill} ${statusTone(item.severity)}`}>
                  {item.severity || "unknown"}
                </b>
              </span>
              <span>
                <b>{item.event_name || "unknown"}</b>
                <small>{item.outcome || "unknown outcome"}</small>
              </span>
              <span>
                <code>
                  {item.metadata?.method || "?"}{" "}
                  {item.metadata?.route || "unavailable"}
                </code>
              </span>
              <span>
                {formatNumber(item.metadata?.status_code)} ·{" "}
                {formatNumber(item.metadata?.duration_ms, " ms")}
              </span>
              <span>
                <code>{item.correlation_id || "unavailable"}</code>
              </span>
              <span>
                {item.occurred_at
                  ? new Date(item.occurred_at).toLocaleString()
                  : "Unavailable"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          {events
            ? "No events matched the bounded filters."
            : "Load operations to view recent events."}
        </div>
      )}
    </section>
  );
}

function ReadinessPanel({controller}: ControllerProps) {
  const readiness = controller.readiness;
  return (
    <section className={styles.panel}>
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Readiness checks</p>
          <h2>Required production boundaries</h2>
        </div>
        <span className={`${styles.pill} ${statusTone(readiness?.status)}`}>
          {readiness?.status || "unavailable"}
        </span>
      </div>
      {readiness?.checks?.length ? (
        <div className={styles.checkList}>
          {readiness.checks.map((check) => (
            <article className={styles.checkCard} key={check.id}>
              <div className={styles.cardHead}>
                <div>
                  <span>{check.required ? "required" : "advisory"}</span>
                  <b>{check.label || check.id}</b>
                </div>
                <span
                  className={`${styles.pill} ${statusTone(check.status)}`}
                >
                  {check.status || "unknown"}
                </span>
              </div>
              {check.remediation ? (
                <p>{check.remediation}</p>
              ) : (
                <p className={styles.goodText}>
                  No remediation is required for this check.
                </p>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          Readiness checks are unavailable until the control center is loaded.
        </div>
      )}
      {readiness?.next_action ? (
        <div className={styles.nextAction}>
          <b>Next operator action</b>
          <p>{readiness.next_action}</p>
        </div>
      ) : null}
    </section>
  );
}

export function OperationsControlCenter() {
  const controller = useOperationsControlCenter();
  return (
    <main className={styles.shell}>
      <OperationsHero controller={controller} />
      <AuthenticationPanel controller={controller} />
      <PrimaryStatusPanel controller={controller} />
      <DeploymentPanel controller={controller} />
      <ReliabilityPanel controller={controller} />
      <CapacityPanel controller={controller} />
      <AlertsPanel controller={controller} />
      <EventsPanel controller={controller} />
      <ReadinessPanel controller={controller} />
    </main>
  );
}
