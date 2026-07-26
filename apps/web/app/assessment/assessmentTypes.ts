export const POLL_INTERVAL_MS = 3000;
export const MAX_POLL_ATTEMPTS = 360;

export type Locale = "en" | "es-MX";
export type Service = "express" | "comprehensive";
export type Phase = "idle" | "checking" | "starting" | "running" | "review_required" | "complete" | "unavailable" | "failed" | "timed_out";
export type Evidence = Record<string, unknown> | string[];
export type Report = Record<string, unknown> & {
  markdown?: string;
  html?: string;
  pdf_base64?: string;
  pdf_filename?: string;
  pdf_error?: string;
  report_id?: string;
  pdf_sha256?: string;
  json?: Record<string, unknown>;
  markdown_available?: boolean;
  html_available?: boolean;
  json_available?: boolean;
  pdf_available?: boolean;
  artifact_delivery?: string;
  response_bounded?: boolean;
};
export type Section = Record<string, unknown> & {id?: string; label?: string; score?: number | null; presented_score?: number | null; summary?: string; evidence?: string[]; findings?: string[]; unavailable?: string[]};
export type Assessment = Record<string, unknown> & {executive_summary?: string; evidence_coverage?: {calculated?: boolean; percent?: number; label?: string}; maturity_signal?: {level?: string; score?: number; presented_score?: number}; sections?: Section[]; unavailable_data_notes?: string[]};
export type Stage = {status?: string; message?: string; summary?: string; evidence?: Evidence; assessment?: Assessment; report_package?: Report; reports?: Report};
export type ProgressItem = {step?: string; status?: string; message?: string; evidence?: Record<string, unknown>};
export type Result = Assessment & {service_id?: string; status?: string; reason?: string; run_id?: string; repository?: string; commit_sha?: string; evidence_ledger_id?: string; customer_id?: string; project_id?: string; current_stage?: string | null; progress_percent?: number; progress?: ProgressItem[]; assessment?: Assessment; reports?: Report; record?: {status?: string; current_stage?: string | null; progress_percent?: number; stage_results?: Record<string, Stage>}; repository_snapshot?: {commit_sha?: string}; scanner?: {status?: string}; scanner_evidence?: {status?: string; scanner_status?: string}; persistence?: {recorded?: boolean; durable?: boolean; durability_verified?: boolean; survives_container_replacement_verified?: boolean; adapter?: string}; survives_container_replacement_verified?: boolean; human_review_required?: boolean};
export type Scope = {customerId: string; projectId: string};
// Copy is intentionally data-driven; every locale is validated by the shared workspace tests.
export type Copy = Record<string, any>;
