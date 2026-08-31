const COMPREHENSIVE_RUN_ID = /^comprun_[a-f0-9]{32}$/;

function randomHex(bytes: number): string {
  const values = new Uint8Array(bytes);
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.getRandomValues) {
    throw new Error("secure_run_identity_unavailable");
  }
  cryptoApi.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
}
/**
 * Reserve the exact durable identity before the single public-intake POST. The
 * backend binds this ID to its idempotent intake reservation, so an ambiguous
 * response is recovered by exact GET and the browser never replays the POST.
 */
export function reserveComprehensiveRunId(): string {
  return `comprun_${randomHex(16)}`;
}

export function isReservedComprehensiveRunId(value: unknown): boolean {
  return COMPREHENSIVE_RUN_ID.test(String(value || "").trim());
}

export function isIntakeReservationPending(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  const operation = String(record.operation || "").trim().toLowerCase();
  const status = String(record.status || "").trim().toLowerCase();
  return operation === "intake_pending"
    || operation === "intake_reserved"
    || record.intake_pending === true
    || (record.intake_reserved === true && ["", "pending", "reserved", "starting"].includes(status));
}
