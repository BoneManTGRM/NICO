"use client";

import {FormEvent, useMemo, useState} from "react";
import {
  AlertsResponse,
  DeploymentIdentity,
  EventsResponse,
  Observability,
  Readiness,
  SeverityFilter,
} from "./operations-types";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const CORRELATION_HEADER = "X-NICO-Correlation-ID";

class OperatorRequestError extends Error {
  correlationId: string;

  constructor(message: string, correlationId = "") {
    super(message);
    this.name = "OperatorRequestError";
    this.correlationId = correlationId;
  }
}

function sameRelease(frontend?: string, backend?: string) {
  return Boolean(
    frontend &&
      backend &&
      frontend !== "unavailable" &&
      backend !== "unavailable" &&
      frontend === backend,
  );
}

export function useOperationsControlCenter() {
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
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("");
  const [correlationFilter, setCorrelationFilter] = useState("");

  const backendConfigured = Boolean(API_URL);
  const frontendCommit = deployment?.frontend_commit || "";
  const backendCommit =
    observability?.deployment?.deployed_commit ||
    readiness?.deployment?.deployed_commit ||
    "";
  const releasesAligned = sameRelease(frontendCommit, backendCommit);
  const metrics = observability?.request_metrics;
  const workloads = observability?.workloads;
  const severityCounts = metrics?.severity_counts || {};
  const activeAlertCounts = useMemo(() => {
    const counts: Record<string, number> = {
      p0: 0,
      p1: 0,
      p2: 0,
      p3: 0,
      info: 0,
    };
    for (const item of alerts?.alerts || []) {
      const key = item.severity || "info";
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [alerts]);

  async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(url, {cache: "no-store", ...options});
    const responseCorrelation = response.headers.get(CORRELATION_HEADER) || "";
    if (responseCorrelation) {
      setCorrelationId(responseCorrelation);
    }

    let data: unknown = {};
    try {
      data = await response.json();
    } catch {
      throw new OperatorRequestError(
        `Operator endpoint returned invalid JSON (${response.status}).`,
        responseCorrelation,
      );
    }

    if (!response.ok) {
      const payload = data as {
        detail?: {message?: string; code?: string};
        message?: string;
        error?: string;
      };
      const message =
        payload?.detail?.message ||
        payload?.message ||
        payload?.error ||
        `Operator request failed (${response.status}).`;
      throw new OperatorRequestError(message, responseCorrelation);
    }
    return data as T;
  }

  function operatorHeaders() {
    return {"X-NICO-Admin-Token": adminToken};
  }

  async function loadControlCenter(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!backendConfigured) {
      setError(
        "NEXT_PUBLIC_NICO_API_URL is not configured for this Vercel deployment.",
      );
      return;
    }
    if (!adminToken.trim()) {
      setError(
        "Enter the operator admin token. It remains only in this page's memory and is not saved.",
      );
      return;
    }

    setLoading(true);
    setError("");
    setCorrelationId("");
    try {
      const frontend = await fetchJson<DeploymentIdentity>("/api/deployment");
      const eventParams = new URLSearchParams({limit: "100"});
      if (severityFilter) {
        eventParams.set("severity", severityFilter);
      }
      if (correlationFilter.trim()) {
        eventParams.set("correlation_id", correlationFilter.trim());
      }

      const alertParams = new URLSearchParams({event_window: "500"});
      if (
        frontend.frontend_commit &&
        frontend.frontend_commit !== "unavailable"
      ) {
        alertParams.set("frontend_commit", frontend.frontend_commit);
      }

      const [readinessPayload, observabilityPayload, eventsPayload, alertsPayload] =
        await Promise.all([
          fetchJson<Readiness>(`${API_URL}/operations/readiness`),
          fetchJson<Observability>(
            `${API_URL}/operations/observability?event_window=500`,
            {headers: operatorHeaders()},
          ),
          fetchJson<EventsResponse>(
            `${API_URL}/operations/events?${eventParams.toString()}`,
            {headers: operatorHeaders()},
          ),
          fetchJson<AlertsResponse>(
            `${API_URL}/operations/alerts?${alertParams.toString()}`,
            {headers: operatorHeaders()},
          ),
        ]);

      setDeployment(frontend);
      setReadiness(readinessPayload);
      setObservability(observabilityPayload);
      setEvents(eventsPayload);
      setAlerts(alertsPayload);
      setLastLoadedAt(new Date().toISOString());
    } catch (requestError) {
      const normalized =
        requestError instanceof Error
          ? requestError
          : new Error("Operator control center request failed.");
      setError(normalized.message);
      if (
        normalized instanceof OperatorRequestError &&
        normalized.correlationId
      ) {
        setCorrelationId(normalized.correlationId);
      }
    } finally {
      setLoading(false);
    }
  }

  return {
    adminToken,
    setAdminToken,
    loading,
    error,
    correlationId,
    lastLoadedAt,
    deployment,
    readiness,
    observability,
    events,
    alerts,
    severityFilter,
    setSeverityFilter,
    correlationFilter,
    setCorrelationFilter,
    backendConfigured,
    frontendCommit,
    backendCommit,
    releasesAligned,
    metrics,
    workloads,
    severityCounts,
    activeAlertCounts,
    loadControlCenter,
  };
}

export type OperationsControlCenterController = ReturnType<
  typeof useOperationsControlCenter
>;
