import {useEffect, useRef} from "react";

export type WorkspaceProps = {
  runId: string;
  refresh?: number;
  isCurrent?: () => boolean;
  onChanged?: (runId: string) => void;
};

// Standalone panels retain their read-only saved-run entry point.
export function savedRun(): WorkspaceProps {
  return {runId: typeof window === "undefined" ? "" : new URL(window.location.href).searchParams.get("run_id") || ""};
}

export function useReviewScope(isCurrent?: () => boolean) {
  const sequence = useRef(0);
  const pending = useRef(false);
  const mutation = useRef(false);
  const refreshDeferred = useRef(false);
  useEffect(() => () => {sequence.current++; pending.current = false;}, []);
  return {
    pending, mutation, refreshDeferred,
    begin() {pending.current = true; return ++sequence.current;},
    current(token: number) {return token === sequence.current && (!isCurrent || isCurrent());},
    finish(token: number) {if (token === sequence.current) pending.current = false;},
  };
}

export class ReviewResponseError extends Error {
  constructor(message: string, readonly ambiguous = false) {super(message);}
}

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export async function reviewResponse(response: Response, runId: string, locale: "en" | "es-MX"): Promise<Record<string, any>> {
  const invalid = locale === "es-MX" ? "No fue posible verificar la respuesta de revisión para esta ejecución exacta." : "The review response could not be verified for this exact run.";
  let value: unknown;
  try {value = await response.json();} catch {throw new ReviewResponseError(invalid, response.ok || response.status >= 500);}
  if (!response.ok) throw new ReviewResponseError(locale === "es-MX"
    ? `No fue posible completar la solicitud protegida de revisión (HTTP ${response.status}).`
    : `The protected review request failed (HTTP ${response.status}).`, response.status >= 500 || response.status === 408);
  if (!record(value) || value.run_id !== runId || typeof value.repository !== "string" || !value.repository
    || typeof value.commit_sha !== "string" || !/^[a-f0-9]{40}$/i.test(value.commit_sha)
    || typeof value.evidence_ledger_id !== "string" || !value.evidence_ledger_id
    || value.human_review_required !== true || value.client_delivery_allowed !== false
    || typeof value.ready_for_final_approval !== "boolean"
    || !Array.isArray(value.candidates) || !value.candidates.every(row => record(row) && typeof row.candidate_id === "string" && row.candidate_id.trim())
    || !Array.isArray(value.clusters) || !value.clusters.every(record)
    || !["ledger", "queue_counts", "workload_metrics", "quality_control_sampling", "empirical_measurement"].every(key => record(value[key]))
    || !["candidate_count", "dispositioned_candidate_count", "remaining_candidate_count", "quality_control_required_count", "quality_control_completed_count", "open_evidence_request_count"].every(key => Number.isInteger(value[key]) && Number(value[key]) >= 0)
    || value.candidate_count !== value.candidates.length
    || Number(value.dispositioned_candidate_count) + Number(value.remaining_candidate_count) !== value.candidate_count) {
    throw new ReviewResponseError(invalid, true);
  }
  return value;
}

export function ambiguousWrite(error: unknown): boolean {
  return !(error instanceof ReviewResponseError) || error.ambiguous;
}

export function reconciliationMessage(locale: "en" | "es-MX"): string {
  return locale === "es-MX"
    ? "El resultado de la acción no se confirmó. Se consultó el estado guardado; revísalo antes de registrar otra acción. La acción no se repitió."
    : "The action outcome was not confirmed. Saved state was requested; review it before recording another action. The action was not repeated.";
}

export function reviewError(error: unknown, locale: "en" | "es-MX"): string {
  if (error instanceof ReviewResponseError) return error.message;
  return locale === "es-MX" ? "No fue posible completar la solicitud protegida de revisión." : "The protected review request could not be completed.";
}
