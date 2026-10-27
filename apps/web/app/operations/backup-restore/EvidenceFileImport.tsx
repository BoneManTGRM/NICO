"use client";
import {useRef, useState} from "react";
import {EvidenceImport, MAX_IMPORT_BYTES, backupEvidenceNote, localDateTime, parseEvidenceImport, requireMatchingSchema, sampledNote} from "./evidenceImport";

export default function EvidenceFileImport({schema, scope, disabled, onConfirm}: {
  schema?: string; scope: string; disabled: boolean; onConfirm: (evidence: EvidenceImport) => void;
}) {
  const [preview, setPreview] = useState<EvidenceImport | null>(null);
  const [previewScope, setPreviewScope] = useState("");
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const sequence = useRef(0);
  function cancel() {sequence.current++; setPreview(null); setReading(false); setError("");}
  async function select(file?: File) {
    const current = ++sequence.current;
    setPreview(null); setError(""); setReading(false);
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) {setError("Evidence files must be 16 KiB or smaller."); return;}
    setReading(true);
    try {
      const parsed = parseEvidenceImport(await file.text());
      if (current !== sequence.current) return;
      setPreviewScope(scope);
      setPreview(parsed);
    } catch {if (current === sequence.current) setError("This file is not valid evidence. Use the documented JSON format without extra fields, credentials or private data.");}
    finally {if (current === sequence.current) setReading(false);}
  }
  function confirm() {
    if (!preview || disabled || reading || previewScope !== scope) return;
    try {requireMatchingSchema(preview, schema); onConfirm(preview); cancel();}
    catch (caught) {setError(caught instanceof Error ? caught.message : "Evidence could not be applied.");}
  }
  const labels: Record<string, string> = {
    completed_at: "Completed at", backup_reference_sha256: "Backup reference SHA-256",
    source_backup_reference_sha256: "Source backup reference SHA-256", restored_record_set_sha256: "Restored record-set SHA-256",
    successful: "Successful", encrypted_at_rest_verified: "Encryption at rest verified", separated_copy_verified: "Separated copy verified",
    retention_days: "Retention days", pitr_applicable: "PITR applicable", pitr_window_hours: "PITR window (hours)",
    isolated_nonproduction_target_verified: "Isolated target verified", required_tables_verified: "Required tables verified",
    application_read_verified: "Bounded application-code reads verified",
  };
  function details(values: EvidenceImport["backup"] | EvidenceImport["restore"]) {
    return <dl>{Object.entries(values).map(([key, value]) => <div key={key} style={{overflowWrap: "anywhere", marginBottom: "0.75rem"}}>
      <dt>{labels[key]}</dt><dd>{key === "completed_at" ? <>
        <span>UTC: {String(value)}</span><br/><span>Local: {localDateTime(String(value))} ({Intl.DateTimeFormat().resolvedOptions().timeZone})</span>
      </> : typeof value === "boolean" ? (value ? "Yes — verify the supporting evidence" : "No — not verified") : String(value)}</dd>
    </div>)}</dl>;
  }
  return <section className="section panel" aria-labelledby="evidence-import-title">
    <h2 id="evidence-import-title">Import evidence from a file</h2>
    <p>Choose a nonsensitive JSON evidence file on this device. It stays in this page's memory; selecting or applying it sends nothing. Review every claim before applying it to the forms. Confirmation replaces the backup/restore fields, provider and notes; it does not change your reviewer or access fields.</p>
    <label>Evidence JSON file<input type="file" accept=".json,application/json" disabled={disabled} onChange={event => {
      const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; void select(file);
    }}/></label>
    {reading ? <p role="status">Reading evidence file…</p> : null}
    {(preview || reading) ? <button type="button" disabled={disabled} onClick={cancel}>Cancel import</button> : null}
    {error ? <p role="alert" className="error-box">{error}</p> : null}
    {preview ? <div>
      <h3>Review before applying</h3>
      <p style={{overflowWrap: "anywhere"}}>Evidence scope: {previewScope}</p>
      <p>Provider: {preview.provider}. Customer, project, reviewer and authentication remain under your control.</p>
      <p style={{overflowWrap: "anywhere"}}>Schema contract: {preview.schema_contract_sha256}</p>
      <h4>Backup</h4>{details(preview.backup)}
      <h4>Matching restore</h4>{details(preview.restore)}
      <p>Verification window in local time: {localDateTime(preview.evidence_basis.verifier_window_start_utc)} to {localDateTime(preview.evidence_basis.verifier_window_end_utc)} ({Intl.DateTimeFormat().resolvedOptions().timeZone}). The UTC window is preserved below.</p>
      <p className="warning-box">{backupEvidenceNote(preview)} {sampledNote(preview)} Import does not independently verify these claims or grant approval or delivery authority.</p>
      {previewScope !== scope ? <p role="alert">The customer/project scope changed. Select the file again and review it for this scope.</p> : null}
      {!schema ? <p>Load current evidence status first, then return to this preview.</p> : schema !== preview.schema_contract_sha256 ? <p role="alert">Schema mismatch. These fields cannot be applied.</p> : null}
      <button type="button" className="primary-button" disabled={disabled || reading || previewScope !== scope || schema !== preview.schema_contract_sha256} onClick={confirm}>Confirm and fill forms — no submission</button>
    </div> : null}
  </section>;
}
