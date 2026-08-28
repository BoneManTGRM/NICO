import type {Phase, Result, Service} from "./assessmentTypes";

/**
 * Project a browser terminal phase only from an explicit canonical terminal marker.
 *
 * Status text can be observed through a stale continuation response while the durable
 * exact-run status remains active. The Comprehensive API publishes `terminal: true`
 * only after the canonical record reaches a terminal boundary, so browser state must
 * not infer failure, review, or approval from status text alone.
 */
export function terminal(_service: Service, result: Result): Phase | null {
  if (result.terminal !== true) {
    return null;
  }

  const value = String(result.status || result.record?.status || "").toLowerCase();
  // Human approval is a terminal run decision even when the separately issued
  // client-delivery authorization is still pending or has been invalidated.
  // Deliberately do not consult client_delivery_allowed: delivery authorization
  // is a later human boundary and cannot restart completed assessment execution.
  if (value === "approved") {
    return "complete";
  }
  if (
    ["failed", "blocked", "error", "rejected", "interrupted"].includes(value)
  ) {
    return "failed";
  }
  if (
    value === "review_required" ||
    (["complete", "completed"].includes(value) &&
      result.human_review_required !== false)
  ) {
    return "review_required";
  }
  return null;
}
