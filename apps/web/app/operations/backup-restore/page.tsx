"use client";

import {useRef, useState} from "react";
import EvidenceFileImport from "./EvidenceFileImport";
import {EvidenceImport, SubmissionGuard, backupEvidenceNote, evidenceInstant, localDateTime, matchesRecorded, requireImportedTiming, requireMatchingSchema, sampledNote, submissionKey} from "./evidenceImport";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");

type EvidenceSummary = {
  status?: string;
  backup_restore_ready?: boolean;
  adapter?: string;
  persistence_available?: boolean;
  schema_contract_version?: string;
  schema_contract_sha256?: string;
  blockers?: string[];
  warnings?: string[];
  checked_at?: string;
  latest_backup?: Record<string, unknown>;
  latest_restore_drill?: Record<string, unknown>;
  thresholds?: Record<string, unknown>;
  next_action?: string;
  guardrail?: string;
};

type ApiResponse = {
  status?: string;
  backup_restore?: EvidenceSummary;
  backup_evidence?: Record<string, unknown>;
  restore_drill?: Record<string, unknown>;
  detail?: {message?: string};
};

function statusClass(value?: string) {
  const normalized = String(value || "").toLowerCase();
  if (["ready", "recorded"].includes(normalized)) return "status green";
  if (["degraded", "missing", "stale"].includes(normalized)) return "status yellow";
  if (["blocked", "failed"].includes(normalized)) return "status red";
  return "status gray";
}

function localNow(): string {
  const value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return value.toISOString().slice(0, 16);
}

export default function BackupRestoreOperationsPage() {
  const [adminToken, setAdminToken] = useState("");
  const [customerId, setCustomerId] = useState("default_customer");
  const [projectId, setProjectId] = useState("default_project");
  const [actor, setActor] = useState("");
  const [provider, setProvider] = useState("Railway PostgreSQL");
  const [summary, setSummary] = useState<EvidenceSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [summaryScope, setSummaryScope] = useState("");
  const [imported, setImported] = useState<EvidenceImport | null>(null);
  const [importedScope, setImportedScope] = useState("");
  const inFlight = useRef(false);
  const submissions = useRef(new SubmissionGuard());
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [backupCompletedAt, setBackupCompletedAt] = useState(localNow);
  const [backupReference, setBackupReference] = useState("");
  const [backupSuccessful, setBackupSuccessful] = useState(false);
  const [encrypted, setEncrypted] = useState(false);
  const [separatedCopy, setSeparatedCopy] = useState(false);
  const [retentionDays, setRetentionDays] = useState(7);
  const [pitrApplicable, setPitrApplicable] = useState(true);
  const [pitrHours, setPitrHours] = useState(24);
  const [backupNote, setBackupNote] = useState("");

  const [restoreCompletedAt, setRestoreCompletedAt] = useState(localNow);
  const [restoreSourceReference, setRestoreSourceReference] = useState("");
  const [restoredRecordHash, setRestoredRecordHash] = useState("");
  const [restoreSuccessful, setRestoreSuccessful] = useState(false);
  const [isolatedTarget, setIsolatedTarget] = useState(false);
  const [requiredTables, setRequiredTables] = useState(false);
  const [applicationRead, setApplicationRead] = useState(false);
  const [restoreNote, setRestoreNote] = useState("");

  function applyImport(evidence: EvidenceImport) {
    if (inFlight.current) return;
    requireMatchingSchema(evidence, summaryScope === query() ? summary?.schema_contract_sha256 : undefined);
    setImported(evidence);
    setImportedScope(query());
    setProvider(evidence.provider);
    setBackupCompletedAt(localDateTime(evidence.backup.completed_at));
    setBackupReference(evidence.backup.backup_reference_sha256);
    setBackupSuccessful(evidence.backup.successful);
    setEncrypted(evidence.backup.encrypted_at_rest_verified);
    setSeparatedCopy(evidence.backup.separated_copy_verified);
    setRetentionDays(evidence.backup.retention_days);
    setPitrApplicable(evidence.backup.pitr_applicable);
    setPitrHours(evidence.backup.pitr_window_hours);
    setBackupNote(backupEvidenceNote(evidence));
    setRestoreCompletedAt(localDateTime(evidence.restore.completed_at));
    setRestoreSourceReference(evidence.restore.source_backup_reference_sha256);
    setRestoredRecordHash(evidence.restore.restored_record_set_sha256);
    setRestoreSuccessful(evidence.restore.successful);
    setIsolatedTarget(evidence.restore.isolated_nonproduction_target_verified);
    setRequiredTables(evidence.restore.required_tables_verified);
    setApplicationRead(evidence.restore.application_read_verified);
    setRestoreNote(sampledNote(evidence));
    setError("");
    setMessage("Evidence applied locally. Review the forms, record the backup first, then record the matching restore. Nothing has been submitted.");
  }

  function query() {
    return new URLSearchParams({
      customer_id: customerId.trim() || "default_customer",
      project_id: projectId.trim() || "default_project",
    }).toString();
  }

  async function readJson(response: Response): Promise<ApiResponse> {
    const data = await response.json() as ApiResponse;
    if (!response.ok) throw new Error(data.detail?.message || `Backup/restore request failed with ${response.status}.`);
    return data;
  }

  async function refresh() {
    if (!API_URL || !adminToken.trim() || inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/operations/backup-restore?${query()}`, {
        headers: {"X-NICO-Admin-Token": adminToken},
        cache: "no-store",
      });
      const data = await readJson(response) as EvidenceSummary;
      setSummary(data);
      setSummaryScope(query());
      if (data.schema_contract_sha256) {
        setMessage("Current backup and restore evidence loaded. The schema-contract hash may be used only after an isolated restore has actually been verified against that contract.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Backup/restore status could not be loaded.");
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }

  async function submitBackup() {
    if (!API_URL || !adminToken.trim() || actor.trim().length < 2 || inFlight.current) return;
    if (imported && (importedScope !== query() || summaryScope !== query() || summary?.schema_contract_sha256 !== imported.schema_contract_sha256)) {
      setError("Refresh status for this scope. Re-import and confirm if the scope changed; imported evidence must match its confirmed scope and current schema contract."); return;
    }
    if (imported) {
      try {requireImportedTiming(imported, backupCompletedAt, restoreCompletedAt);}
      catch {setError("Imported dates are bound to the verification window. Re-import corrected evidence to change them; nothing was submitted."); return;}
    }
    const completed = evidenceInstant(backupCompletedAt, imported?.backup.completed_at);
    const key = submissionKey("backup", query(), completed, backupReference.trim());
    if ((summaryScope === query() && matchesRecorded(summary?.latest_backup, completed, backupReference.trim().toLowerCase())) || !submissions.current.begin(key)) {
      setError("This backup was recorded or its submission outcome is unresolved. Refresh and review existing evidence before any further submission."); return;
    }
    inFlight.current = true;
    let recorded = false;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/operations/backup-restore/backup-evidence?${query()}`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({
          completed_at: completed,
          provider,
          backup_reference_sha256: backupReference.trim().toLowerCase(),
          successful: backupSuccessful,
          encrypted_at_rest_verified: encrypted,
          separated_copy_verified: separatedCopy,
          retention_days: retentionDays,
          pitr_applicable: pitrApplicable,
          pitr_window_hours: pitrApplicable ? pitrHours : 0,
          actor,
          note: backupNote,
        }),
        cache: "no-store",
      });
      const data = await readJson(response);
      recorded = data.status === "recorded";
      if (!recorded) throw new Error("The backup response did not confirm recording. Refresh and review evidence; do not submit again.");
      setSummary(data.backup_restore || null);
      setSummaryScope(query());
      if (!restoreSourceReference.trim()) setRestoreSourceReference(backupReference.trim().toLowerCase());
      setMessage("Bounded backup evidence recorded. NICO did not create, access, or download a backup.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Backup evidence could not be recorded.");
    } finally {
      submissions.current.finish(key, recorded);
      inFlight.current = false;
      setLoading(false);
    }
  }

  async function submitRestore() {
    if (!API_URL || !adminToken.trim() || actor.trim().length < 2 || !summary?.schema_contract_sha256 || inFlight.current) return;
    if (summaryScope !== query() || (imported && (importedScope !== query() || summary.schema_contract_sha256 !== imported.schema_contract_sha256))) {
      setError("Refresh status for this scope. Re-import and confirm if the scope changed; imported evidence must match its confirmed scope and current schema contract."); return;
    }
    if (!summary.latest_backup?.present || summary.latest_backup.backup_reference_sha256 !== restoreSourceReference.trim().toLowerCase()) {
      setError("Record or load the matching backup before recording this restore."); return;
    }
    if (imported) {
      try {requireImportedTiming(imported, backupCompletedAt, restoreCompletedAt);}
      catch {setError("Imported dates are bound to the verification window. Re-import corrected evidence to change them; nothing was submitted."); return;}
    }
    const completed = evidenceInstant(restoreCompletedAt, imported?.restore.completed_at);
    const key = submissionKey("restore", query(), completed, restoreSourceReference.trim(), restoredRecordHash.trim());
    if (matchesRecorded(summary.latest_restore_drill, completed, restoreSourceReference.trim().toLowerCase(), restoredRecordHash.trim().toLowerCase()) || !submissions.current.begin(key)) {
      setError("This restore was recorded or its submission outcome is unresolved. Refresh and review existing evidence before any further submission."); return;
    }
    inFlight.current = true;
    let recorded = false;
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/operations/backup-restore/restore-drill?${query()}`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-NICO-Admin-Token": adminToken},
        body: JSON.stringify({
          completed_at: completed,
          provider,
          source_backup_reference_sha256: restoreSourceReference.trim().toLowerCase(),
          restored_record_set_sha256: restoredRecordHash.trim().toLowerCase(),
          successful: restoreSuccessful,
          isolated_nonproduction_target_verified: isolatedTarget,
          schema_contract_sha256: summary.schema_contract_sha256,
          required_tables_verified: requiredTables,
          application_read_verified: applicationRead,
          actor,
          note: restoreNote,
        }),
        cache: "no-store",
      });
      const data = await readJson(response);
      recorded = data.status === "recorded";
      if (!recorded) throw new Error("The restore response did not confirm recording. Refresh and review evidence; do not submit again.");
      setSummary(data.backup_restore || null);
      setSummaryScope(query());
      setMessage("Bounded isolated restore-drill evidence recorded. NICO did not execute a restore, failover, rollback, or production mutation.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Restore-drill evidence could not be recorded.");
    } finally {
      submissions.current.finish(key, recorded);
      inFlight.current = false;
      setLoading(false);
    }
  }

  return <main className="shell">
    <section className="hero">
      <p className="eyebrow">NICO Operations</p>
      <h1>Backup and restore verification</h1>
      <p className="lead">Record bounded proof of a real production backup and a real isolated non-production restore drill. This interface does not create backups or execute restores.</p>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Operator access</p><h2>Evidence scope</h2></div><span className={statusClass(summary?.status)}>{summary?.status || "not checked"}</span></div>
      <p className="warning-box">The admin token remains only in live React memory. Do not paste database URLs, credentials, backup URLs, archive contents, provider response bodies, or connection strings. Notes are hashed and are not retained.</p>
      <div className="form-grid">
        <label>Customer ID<input disabled={loading} value={customerId} onChange={(event) => setCustomerId(event.target.value)} /></label>
        <label>Project ID<input disabled={loading} value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
        <label>Operator or reviewer<input disabled={loading} value={actor} onChange={(event) => setActor(event.target.value)} /></label>
        <label>Provider label<input disabled={loading} value={provider} onChange={(event) => setProvider(event.target.value)} /></label>
        <label>NICO admin token<input disabled={loading} type="password" autoComplete="off" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} /></label>
      </div>
      <button type="button" className="primary-button" disabled={!API_URL || !adminToken.trim() || loading} onClick={refresh}>{loading ? "Checking evidence..." : "Refresh backup and restore status"}</button>
      {error ? <p className="error-box">{error}</p> : null}
      {message ? <p className="summary-box">{message}</p> : null}
    </section>

    <EvidenceFileImport scope={query()} schema={summaryScope === query() ? summary?.schema_contract_sha256 : undefined} disabled={loading} onConfirm={applyImport}/>
    {imported ? <p className="warning-box">{backupEvidenceNote(imported)} {sampledNote(imported)} Imported dates remain bound to the file; re-import corrected evidence to change them. Each submission still requires your explicit action. Re-importing does not reset recorded or unresolved submissions.</p> : null}

    {summary ? <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Current evidence</p><h2>{summary.backup_restore_ready ? "Backup and restore evidence verified" : "Evidence remains incomplete"}</h2></div><span className={statusClass(summary.status)}>{summary.status}</span></div>
      <div className="grid four target-grid">
        <article><b>Storage adapter</b><span>{summary.adapter || "unknown"}</span></article>
        <article><b>Durable persistence</b><span>{String(Boolean(summary.persistence_available))}</span></article>
        <article><b>Backup evidence</b><span>{String(Boolean(summary.latest_backup?.present))}</span></article>
        <article><b>Restore drill</b><span>{String(Boolean(summary.latest_restore_drill?.present))}</span></article>
      </div>
      {summary.blockers?.length ? <div className="error-box">Blockers: {summary.blockers.join(", ")}</div> : null}
      {summary.warnings?.length ? <div className="warning-box">Warnings: {summary.warnings.join(", ")}</div> : null}
      <details className="help-details"><summary>Safe evidence identity</summary><pre className="json-block">{JSON.stringify({
        checked_at: summary.checked_at,
        schema_contract_version: summary.schema_contract_version,
        schema_contract_sha256: summary.schema_contract_sha256,
        thresholds: summary.thresholds,
        latest_backup: summary.latest_backup,
        latest_restore_drill: summary.latest_restore_drill,
      }, null, 2)}</pre></details>
      <p className="muted">{summary.next_action}</p>
      <p className="muted">{summary.guardrail}</p>
    </section> : null}

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Step 1</p><h2>Record real backup evidence</h2></div><span className="status gray">No backup execution</span></div>
      <div className="form-grid">
        <label>Backup completed at<input disabled={loading} type="datetime-local" step="0.001" value={backupCompletedAt} onChange={(event) => setBackupCompletedAt(event.target.value)} /></label>
        <label>Backup reference SHA-256<input disabled={loading} value={backupReference} onChange={(event) => setBackupReference(event.target.value)} placeholder="64 lowercase hexadecimal characters" /></label>
        <label>Retention days<input disabled={loading} type="number" min={0} max={3650} value={retentionDays} onChange={(event) => setRetentionDays(Number(event.target.value))} /></label>
        <label>Point-in-time recovery hours<input type="number" min={0} max={87600} disabled={loading || !pitrApplicable} value={pitrHours} onChange={(event) => setPitrHours(Number(event.target.value))} /></label>
        <label><input disabled={loading} type="checkbox" checked={backupSuccessful} onChange={(event) => setBackupSuccessful(event.target.checked)} /> Backup completed successfully</label>
        <label><input disabled={loading} type="checkbox" checked={encrypted} onChange={(event) => setEncrypted(event.target.checked)} /> Encryption at rest verified</label>
        <label><input disabled={loading} type="checkbox" checked={separatedCopy} onChange={(event) => setSeparatedCopy(event.target.checked)} /> Provider-separated or offsite copy verified</label>
        <label><input disabled={loading} type="checkbox" checked={pitrApplicable} onChange={(event) => setPitrApplicable(event.target.checked)} /> Point-in-time recovery applies</label>
        <label>Review note<textarea disabled={loading} value={backupNote} onChange={(event) => setBackupNote(event.target.value)} placeholder="Do not include secrets or provider URLs. The note is hashed and not retained." /></label>
      </div>
      <button type="button" className="primary-button" disabled={!adminToken.trim() || actor.trim().length < 2 || backupReference.trim().length !== 64 || loading} onClick={submitBackup}>Record backup evidence</button>
    </section>

    <section className="section panel">
      <div className="section-head"><div><p className="eyebrow">Step 2</p><h2>Record isolated restore-drill evidence</h2></div><span className="status red">Never production</span></div>
      <p className="warning-box">Submit this only after a backup was restored into an isolated non-production target and the current schema, required tables, and application reads were actually verified.</p>
      <div className="form-grid">
        <label>Restore drill completed at<input disabled={loading} type="datetime-local" step="0.001" value={restoreCompletedAt} onChange={(event) => setRestoreCompletedAt(event.target.value)} /></label>
        <label>Source backup reference SHA-256<input disabled={loading} value={restoreSourceReference} onChange={(event) => setRestoreSourceReference(event.target.value)} placeholder="Must match the latest recorded backup" /></label>
        <label>Restored record-set SHA-256<input disabled={loading} value={restoredRecordHash} onChange={(event) => setRestoredRecordHash(event.target.value)} placeholder="Safe hash only; no record data" /></label>
        <label>Current schema-contract SHA-256<input disabled={loading} readOnly value={summary?.schema_contract_sha256 || "Load current status first"} /></label>
        <label><input disabled={loading} type="checkbox" checked={restoreSuccessful} onChange={(event) => setRestoreSuccessful(event.target.checked)} /> Restore completed successfully</label>
        <label><input disabled={loading} type="checkbox" checked={isolatedTarget} onChange={(event) => setIsolatedTarget(event.target.checked)} /> Isolated non-production target verified</label>
        <label><input disabled={loading} type="checkbox" checked={requiredTables} onChange={(event) => setRequiredTables(event.target.checked)} /> Required tables verified</label>
        <label><input disabled={loading} type="checkbox" checked={applicationRead} onChange={(event) => setApplicationRead(event.target.checked)} /> Application read verification passed</label>
        <label>Review note<textarea disabled={loading} value={restoreNote} onChange={(event) => setRestoreNote(event.target.value)} placeholder="Do not include secrets or provider URLs. The note is hashed and not retained." /></label>
      </div>
      <button type="button" className="primary-button" disabled={!adminToken.trim() || actor.trim().length < 2 || restoreSourceReference.trim().length !== 64 || restoredRecordHash.trim().length !== 64 || !summary?.schema_contract_sha256 || loading} onClick={submitRestore}>Record isolated restore-drill evidence</button>
    </section>
  </main>;
}
