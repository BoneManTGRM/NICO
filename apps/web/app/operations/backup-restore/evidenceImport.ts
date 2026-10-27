/** Local-only, bounded evidence interchange. No auth, network or persistence. */
export const IMPORT_FORMAT = "nico.backup-restore-evidence-import.v1";
export const MAX_IMPORT_BYTES = 16384;
export type BackupEvidence = {
  completed_at: string; backup_reference_sha256: string; successful: boolean;
  encrypted_at_rest_verified: boolean; separated_copy_verified: boolean;
  retention_days: number; pitr_applicable: boolean; pitr_window_hours: number;
};
export type RestoreEvidence = {
  completed_at: string; source_backup_reference_sha256: string;
  restored_record_set_sha256: string; successful: boolean;
  isolated_nonproduction_target_verified: boolean; required_tables_verified: boolean;
  application_read_verified: boolean;
};
export type EvidenceImport = {
  format: typeof IMPORT_FORMAT; provider: "Railway PostgreSQL";
  schema_contract_sha256: string; backup: BackupEvidence; restore: RestoreEvidence;
  verification: {method: "nico.restore.unreviewed-application-sample.v1";
    sample_count: number; full_bootstrap_or_http_verified: false};
};
function requireValue(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
function exact(value: unknown, keys: string[]): Record<string, unknown> {
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value), "Expected an evidence object.");
  const object = value as Record<string, unknown>;
  requireValue(Object.keys(object).length === keys.length && keys.every(key => Object.hasOwn(object, key)),
    "Unexpected or missing fields. Only the documented nonsensitive evidence format is accepted.");
  return object;
}
function hash(value: unknown) {
  requireValue(typeof value === "string" && /^[a-f0-9]{64}$/.test(value), "Evidence hashes must be 64 lowercase hexadecimal characters.");
}
function booleanFields(value: Record<string, unknown>, keys: string[]) {
  keys.forEach(key => requireValue(typeof value[key] === "boolean", "Evidence flags must be explicit booleans."));
}
function integer(value: unknown, min: number, max: number) {
  requireValue(typeof value === "number" && Number.isInteger(value) && value >= min && value <= max, "Evidence counts are outside the supported range.");
}
function instant(value: unknown, now: number) {
  requireValue(typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{3})?Z$/.test(value), "Use complete UTC timestamps ending in Z.");
  const date = new Date(value);
  requireValue(Number.isFinite(date.getTime()) && date.toISOString() === (value.includes(".") ? value : value.replace("Z", ".000Z")), "The evidence contains an invalid calendar date.");
  requireValue(date.getTime() <= now, "Evidence completion cannot be in the future.");
}
/** JSON.parse accepts duplicate keys. Detect them before interpreting any evidence. */
function rejectDuplicateKeys(text: string) {
  let i = 0;
  const space = () => {while (/\s/.test(text[i] || "") && i < text.length) i++;};
  function string(): string {
    const start = i++;
    while (i < text.length) {
      if (text[i] === "\\") {i += 2; continue;}
      if (text[i++] === '"') return JSON.parse(text.slice(start, i));
    }
    throw new Error("Invalid JSON file.");
  }
  function value(depth: number) {
    requireValue(depth <= 5, "Evidence nesting is too deep."); space();
    if (text[i] === '{') {
      i++; space(); const keys = new Set<string>();
      if (text[i] === '}') {i++; return;}
      while (i < text.length) {
        requireValue(text[i] === '"', "Invalid JSON file.");
        const key = string(); requireValue(!keys.has(key), "Duplicate JSON fields are not accepted."); keys.add(key);
        space(); requireValue(text[i++] === ':', "Invalid JSON file."); value(depth + 1); space();
        if (text[i] === '}') {i++; return;}
        requireValue(text[i++] === ',', "Invalid JSON file."); space();
      }
    } else if (text[i] === '[') {
      throw new Error("Arrays are not part of the evidence format.");
    } else if (text[i] === '"') {string(); return;}
    else {const start = i; while (i < text.length && !/[\s,}]/.test(text[i])) i++; requireValue(i > start, "Invalid JSON file."); return;}
    throw new Error("Invalid JSON file.");
  }
  value(0); space(); requireValue(i === text.length, "Invalid JSON file.");
}
export function parseEvidenceImport(text: string, now = Date.now()): EvidenceImport {
  requireValue(new TextEncoder().encode(text).length <= MAX_IMPORT_BYTES, "Evidence files must be 16 KiB or smaller.");
  rejectDuplicateKeys(text);
  let parsed: unknown;
  try {parsed = JSON.parse(text);} catch {throw new Error("Invalid JSON file.");}
  const root = exact(parsed, ["format", "provider", "schema_contract_sha256", "backup", "restore", "verification"]);
  requireValue(root.format === IMPORT_FORMAT && root.provider === "Railway PostgreSQL", "Unsupported evidence format or provider.");
  hash(root.schema_contract_sha256);
  const backup = exact(root.backup, ["completed_at", "backup_reference_sha256", "successful", "encrypted_at_rest_verified", "separated_copy_verified", "retention_days", "pitr_applicable", "pitr_window_hours"]);
  const restore = exact(root.restore, ["completed_at", "source_backup_reference_sha256", "restored_record_set_sha256", "successful", "isolated_nonproduction_target_verified", "required_tables_verified", "application_read_verified"]);
  const verification = exact(root.verification, ["method", "sample_count", "full_bootstrap_or_http_verified"]);
  instant(backup.completed_at, now); instant(restore.completed_at, now);
  requireValue(Date.parse(restore.completed_at as string) >= Date.parse(backup.completed_at as string), "Restore verification cannot precede its backup.");
  hash(backup.backup_reference_sha256); hash(restore.source_backup_reference_sha256); hash(restore.restored_record_set_sha256);
  requireValue(backup.backup_reference_sha256 === restore.source_backup_reference_sha256, "Backup and restore references do not match.");
  booleanFields(backup, ["successful", "encrypted_at_rest_verified", "separated_copy_verified", "pitr_applicable"]);
  booleanFields(restore, ["successful", "isolated_nonproduction_target_verified", "required_tables_verified", "application_read_verified"]);
  integer(backup.retention_days, 0, 3650); integer(backup.pitr_window_hours, 0, 87600);
  requireValue(backup.pitr_applicable || backup.pitr_window_hours === 0, "A non-applicable PITR window must be zero.");
  requireValue(verification.method === "nico.restore.unreviewed-application-sample.v1" && verification.full_bootstrap_or_http_verified === false, "Unsupported verification scope. Full application verification cannot be claimed by this sampled format.");
  integer(verification.sample_count, 1, 3);
  return parsed as EvidenceImport;
}
export function requireMatchingSchema(evidence: EvidenceImport, current?: string) {
  requireValue(Boolean(current), "Load current evidence status before applying this file.");
  requireValue(evidence.schema_contract_sha256 === current, "The file does not match the current schema contract. No fields were changed.");
}
export function localDateTime(utc: string): string {
  const date = new Date(utc), pad = (n: number, width = 2) => String(n).padStart(width, "0");
  return `${pad(date.getFullYear(), 4)}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(),3)}`;
}
export function evidenceInstant(local: string, importedUtc?: string): string {
  // Preserve the exact imported instant even in a repeated DST local hour.
  if (importedUtc && local === localDateTime(importedUtc)) return importedUtc;
  const date = new Date(local);
  return Number.isFinite(date.getTime()) ? date.toISOString() : local;
}
export function sampledNote(evidence: EvidenceImport): string {
  return `Bounded isolated application-code verification: ${evidence.verification.sample_count} unreviewed records. Method ${evidence.verification.method}. Full bootstrap/HTTP, approved records and whole-database equivalence were not tested.`;
}
/** In-memory only: do not retry uncertain or acknowledged writes from this page. */
export class SubmissionGuard {
  private busy = false;
  private attempts = new Map<string, "pending" | "recorded" | "uncertain">();
  begin(key: string) {
    if (this.busy || this.attempts.has(key)) return false;
    this.busy = true; this.attempts.set(key, "pending"); return true;
  }
  finish(key: string, recorded: boolean) {this.attempts.set(key, recorded ? "recorded" : "uncertain"); this.busy = false;}
  has(key: string) {return this.attempts.has(key);}
}
export function submissionKey(kind: "backup" | "restore", scope: string, completed: string, reference: string, recordHash = "") {
  return JSON.stringify([kind, scope, Math.floor(Date.parse(completed) / 1000), reference.toLowerCase(), recordHash.toLowerCase()]);
}
export function matchesRecorded(record: Record<string, unknown> | undefined, completed: string, reference: string, recordHash?: string) {
  return Boolean(record?.present && Date.parse(String(record.completed_at)) / 1000 === Math.floor(Date.parse(completed) / 1000)
    && (record.backup_reference_sha256 ?? record.source_backup_reference_sha256) === reference
    && (recordHash === undefined || record.restored_record_set_sha256 === recordHash));
}
