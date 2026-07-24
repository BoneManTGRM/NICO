export const POLL_INTERVAL_MS = 3000;
export const MAX_POLL_ATTEMPTS = 360;

export type Locale = "en" | "es-MX";
export type Service = "express" | "comprehensive";
export type Phase = "idle" | "starting" | "running" | "review_required" | "complete" | "failed" | "timed_out";
export type Evidence = Record<string, unknown> | string[];

export type Report = {
  markdown?: string;
  html?: string;
  pdf_base64?: string;
  pdf_filename?: string;
  pdf_error?: string;
  report_id?: string;
  pdf_sha256?: string;
};

export type Section = {
  id?: string;
  label?: string;
  score?: number | null;
  presented_score?: number | null;
  status?: string;
  presented_status?: string;
  score_band_label?: string;
  assurance_label?: string;
  risk_disposition?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
};

export type Assessment = {
  executive_summary?: string;
  evidence_coverage?: {calculated?: boolean; percent?: number; label?: string};
  maturity_signal?: {level?: string; score?: number; presented_score?: number};
  sections?: Section[];
  unavailable_data_notes?: string[];
  human_review_required?: boolean;
  client_ready?: boolean;
};

export type Stage = {
  status?: string;
  message?: string;
  summary?: string;
  evidence?: Evidence;
  assessment?: Assessment;
  report_package?: Report;
  reports?: Report;
};

export type ProgressItem = {
  step?: string;
  status?: string;
  message?: string;
  evidence?: Record<string, unknown>;
};

export type Result = Assessment & {
  service_id?: string;
  status?: string;
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  evidence_ledger_id?: string;
  customer_id?: string;
  project_id?: string;
  current_stage?: string | null;
  progress_percent?: number;
  progress?: ProgressItem[];
  assessment?: Assessment;
  reports?: Report;
  record?: {
    status?: string;
    current_stage?: string | null;
    progress_percent?: number;
    stage_results?: Record<string, Stage>;
    revision?: number;
    integrity_sha256?: string;
  };
  repository_snapshot?: {commit_sha?: string};
  scanner?: {status?: string};
  scanner_evidence?: {status?: string; scanner_status?: string};
  persistence?: {recorded?: boolean; durable?: boolean; durability_verified?: boolean; adapter?: string};
  human_review_required?: boolean;
  client_ready?: boolean;
  client_delivery_allowed?: boolean;
};

export type Scope = {customerId: string; projectId: string};

export type Copy = {
  heroEyebrow: string;
  title: string;
  lead: string;
  depthLabel: string;
  coverage: string;
  warning: string;
  repo: string;
  repoPlaceholder: string;
  client: string;
  project: string;
  confirm: string;
  run: string;
  state: string;
  stage: string;
  progress: string;
  elapsed: string;
  checks: string;
  runId: string;
  commit: string;
  scanner: string;
  report: string;
  review: string;
  maturity: string;
  score: string;
  durable: string;
  awaitingStage: string;
  awaitingScanner: string;
  reviewAfterReport: string;
  maturityAfterScoring: string;
  notScoredYet: string;
  reviewLimitedNotScored: string;
  unavailableStatus: string;
  evidenceLimitations: string;
  notApplicable: string;
  copyValue: string;
  valueCopied: string;
  notScored: string;
  verificationPending: string;
  verifiedPersistentStorage: string;
  notVerified: string;
  copied: string;
  copy: string;
  download: string;
  select: string;
  evidence: string;
  findings: string;
  stepEvidence: string;
  reviewNotice: string;
  backendError: string;
  authError: string;
  invalidJson: string;
  runIdMissing: string;
  expressComplete: string;
  comprehensiveReview: string;
  stopped: string;
  pdfMissing: string;
  services: Record<Service, {
    label: string;
    internalLabel: string;
    eyebrow: string;
    heading: string;
    summary: string;
    instructionsTitle: string;
    instructions: string[];
  }>;
  phases: Record<Phase, string>;
  stageLabels: Record<string, string>;
};
