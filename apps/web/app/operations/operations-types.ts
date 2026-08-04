export const SEVERITIES = ["", "p0", "p1", "p2", "p3", "info"] as const;

export type SeverityFilter = (typeof SEVERITIES)[number];
export type JsonRecord = Record<string, unknown>;

export type DeploymentIdentity = {
  artifact_schema?: string;
  status?: string;
  provider?: string;
  frontend_commit?: string;
  backend_origin?: string;
  deployment_environment?: string;
  commit_identity_available?: boolean;
};

export type ReadinessCheck = {
  id?: string;
  label?: string;
  status?: string;
  passed?: boolean;
  required?: boolean;
  remediation?: string;
  observed?: unknown;
};

export type Readiness = {
  status?: string;
  operational_ready?: boolean;
  blockers?: string[];
  warnings?: string[];
  checks?: ReadinessCheck[];
  deployment?: {
    deployed_commit?: string;
    matches_expected_build?: boolean;
    build_marker?: string;
  };
  storage?: {
    persistence_available?: boolean;
    database_configured?: boolean;
    warnings?: string[];
  };
  next_action?: string;
};

export type WorkloadSummary = {
  total?: number;
  active?: number;
  queued?: number;
  oldest_queue_age_seconds?: number;
  status_counts?: Record<string, number>;
};

export type DurationSummary = {
  sample_count?: number;
  p50?: number | null;
  p95?: number | null;
  max?: number | null;
};

export type Observability = {
  status?: string;
  generated_at?: string;
  events_observed?: number;
  request_metrics?: {
    request_count?: number;
    failure_count?: number;
    failure_rate?: number;
    timeout_count?: number;
    timeout_rate?: number;
    latency_ms?: {
      p50?: number | null;
      p95?: number | null;
      max?: number | null;
    };
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
  storage?: {
    adapter?: string;
    persistence_available?: boolean;
    database_configured?: boolean;
  };
  deployment?: {
    status?: string;
    deployed_commit?: string;
    matches_expected_build?: boolean;
    build_marker?: string;
  };
  semantic_readiness?: {
    status?: string;
    operational_ready?: boolean;
    blockers?: string[];
    warnings?: string[];
  };
};

export type OperationalEvent = {
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

export type EventsResponse = {
  status?: string;
  count?: number;
  limit?: number;
  events?: OperationalEvent[];
  event_pipeline?: {
    status?: string;
    write_failures?: number;
    read_failures?: number;
  };
};

export type OperationalAlert = {
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

export type AlertsResponse = {
  status?: string;
  highest_severity?: string;
  alert_count?: number;
  alerts?: OperationalAlert[];
  alert_set_sha256?: string;
  source_observability_sha256?: string;
};
