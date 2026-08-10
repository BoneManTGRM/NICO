"use client";

import {FormEvent, useEffect, useState} from "react";
import styles from "./reviewer-queue.module.css";

type JsonRecord = Record<string, unknown>;
type ReviewQueuePayload = {
  run_id?: string;
  commit_sha?: string;
  status?: string;
  terminal?: boolean;
  read_only?: boolean;
  source?: string;
  candidate_count?: number;
  human_review_work_units?: number;
  human_review_required?: boolean;
  client_delivery_allowed?: boolean;
  candidate_register?: JsonRecord;
};
type QueueUnit = {id: string; kind: "individual" | "group"; candidates: JsonRecord[]; representative: JsonRecord};
type QueueModel = {
  units: QueueUnit[];
  individualUnits: QueueUnit[];
  groupedUnits: QueueUnit[];
  candidateCount: number;
  integrityErrors: string[];
};

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}
function asRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is JsonRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}
function text(value: unknown): string { return String(value ?? "").trim(); }
function textList(value: unknown): string[] { return Array.isArray(value) ? value.map(text).filter(Boolean) : []; }
function candidateId(candidate: JsonRecord): string { return text(candidate.candidate_id) || "candidate-id-missing"; }
function canonicalRegister(payload: ReviewQueuePayload): JsonRecord {
  return asRecord(payload.candidate_register);
}
function routingPriority(candidate: JsonRecord): number {
  return ({CRITICAL_ATTENTION: 0, HUMAN_TECHNICAL_REVIEW: 1, QUALITY_CONTROL_ELIGIBLE: 2, STABLE_CARRY_FORWARD: 3, AUTOMATED_TRIAGE_COMPLETE: 4} as Record<string, number>)[text(candidate.review_routing_class)] ?? 5;
}
function severityPriority(candidate: JsonRecord): number {
  return ({critical: 0, high: 1, medium: 2, moderate: 2, low: 3, informational: 4, info: 4} as Record<string, number>)[text(candidate.severity).toLowerCase()] ?? 5;
}
function categoryPriority(candidate: JsonRecord): number {
  return ({secret: 0, dependency: 1, static: 2} as Record<string, number>)[text(candidate.category).toLowerCase()] ?? 3;
}
function compareCandidates(left: JsonRecord, right: JsonRecord): number {
  return routingPriority(left) - routingPriority(right)
    || severityPriority(left) - severityPriority(right)
    || categoryPriority(left) - categoryPriority(right)
    || candidateId(left).localeCompare(candidateId(right));
}

function buildQueue(payload: ReviewQueuePayload): QueueModel {
  const register = canonicalRegister(payload);
  if (!Array.isArray(register.findings)) throw new Error("The exact terminal report does not contain a canonical scanner candidate register.");
  const findings = asRecords(register.findings);

  const individuals: JsonRecord[] = [];
  const grouped = new Map<string, JsonRecord[]>();
  for (const candidate of findings) {
    const clusterId = text(candidate.cluster_id);
    if (candidate.grouped_review_eligible === true && candidate.review_requires_individual_attention !== true && clusterId) {
      const members = grouped.get(clusterId) || [];
      members.push(candidate);
      grouped.set(clusterId, members);
    } else {
      individuals.push(candidate);
    }
  }

  const individualUnits: QueueUnit[] = individuals.sort(compareCandidates).map((candidate) => ({
    id: candidateId(candidate), kind: "individual", candidates: [candidate], representative: candidate,
  }));
  const groupedUnits: QueueUnit[] = Array.from(grouped.entries()).map(([clusterId, candidates]) => {
    const ordered = [...candidates].sort(compareCandidates);
    const declared = text(ordered[0]?.representative_candidate_id);
    return {
      id: clusterId,
      kind: "group" as const,
      candidates: ordered,
      representative: ordered.find((item) => candidateId(item) === declared) || ordered[0],
    };
  }).sort((left, right) => compareCandidates(left.representative, right.representative) || left.id.localeCompare(right.id));

  const units = [...individualUnits, ...groupedUnits];
  const triage = asRecord(register.technical_triage);
  const expectedWorkUnits = Number(triage.human_review_work_units);
  const declaredCandidateCount = Number(register.candidate_record_count);
  const candidateCount = Number.isFinite(declaredCandidateCount) ? declaredCandidateCount : findings.length;
  const sourceIds = findings.map(candidateId);
  const queuedIds = units.flatMap((unit) => unit.candidates.map(candidateId));
  const integrityErrors: string[] = [];
  if (new Set(sourceIds).size !== sourceIds.length) integrityErrors.push("Candidate identities are not unique.");
  if (candidateCount !== findings.length) integrityErrors.push("Candidate count does not match the canonical register.");
  if (new Set(queuedIds).size !== findings.length || queuedIds.length !== findings.length) integrityErrors.push("The queue does not preserve every canonical candidate exactly once.");
  if (Number.isFinite(expectedWorkUnits) && expectedWorkUnits !== units.length) integrityErrors.push("Displayed work units do not reconcile with the canonical workload metric.");
  if (Number.isFinite(Number(payload.candidate_count)) && Number(payload.candidate_count) !== candidateCount) integrityErrors.push("Protected queue candidate count does not match the canonical register.");
  if (Number.isFinite(Number(payload.human_review_work_units)) && Number(payload.human_review_work_units) !== units.length) integrityErrors.push("Protected queue work-unit count does not reconcile with the displayed queue.");
  return {units, individualUnits, groupedUnits, candidateCount, integrityErrors};
}

function evidenceLabel(candidate: JsonRecord): string {
  return text(candidate.source_path) || text(candidate.path) || text(candidate.manifest_path) || text(candidate.advisory) || text(candidate.rule) || text(candidate.rule_id) || "Evidence location retained in the canonical register";
}
function CandidateSummary({candidate}: {candidate: JsonRecord}) {
  const proofGaps = textList(candidate.technical_triage_proof_gaps || candidate.proof_gaps);
  return <>
    <div className={styles.candidateHeader}>
      <code>{candidateId(candidate)}</code>
      <span>{text(candidate.category) || "uncategorized"}</span>
      <span>{text(candidate.review_routing_class).replaceAll("_", " ") || "review routing unavailable"}</span>
    </div>
    <h3>{text(candidate.title) || text(candidate.rule) || text(candidate.advisory) || "Technical review candidate"}</h3>
    <p className={styles.evidence}>{evidenceLabel(candidate)}</p>
    <dl className={styles.detailGrid}>
      <div><dt>Technical proposal</dt><dd>{text(candidate.technical_triage_verdict).replaceAll("_", " ") || "needs review"}</dd></div>
      <div><dt>Confidence</dt><dd>{text(candidate.technical_triage_confidence) || "not stated"}</dd></div>
      <div><dt>Scanner</dt><dd>{text(candidate.scanner) || text(candidate.tool) || "not stated"}</dd></div>
      <div><dt>Lineage</dt><dd>{text(candidate.lineage_status).replaceAll("_", " ") || "not stated"}</dd></div>
    </dl>
    <p>{text(candidate.technical_triage_rationale) || "No automated rationale was retained."}</p>
    {proofGaps.length ? <p className={styles.proofGap}><strong>Proof gaps:</strong> {proofGaps.join(" · ")}</p> : null}
    {text(candidate.technical_triage_recommended_next_step) ? <p><strong>Recommended next step:</strong> {text(candidate.technical_triage_recommended_next_step)}</p> : null}
  </>;
}

export default function ReviewerQueue() {
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [payload, setPayload] = useState<ReviewQueuePayload | null>(null);
  const [model, setModel] = useState<QueueModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setRunId(new URLSearchParams(window.location.search).get("run_id") || ""); }, []);

  async function loadQueue(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!runId.trim() || !adminToken.trim()) {
      setError("Enter the exact Comprehensive run ID and operator admin token.");
      return;
    }
    setLoading(true); setError(""); setPayload(null); setModel(null);
    try {
      const response = await fetch(new URL(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review-queue`, window.location.origin), {
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken.trim()},
      });
      if (!response.ok) throw new Error(`Unable to load the exact protected review queue (${response.status}).`);
      const next = await response.json() as ReviewQueuePayload;
      if (!next.terminal || text(next.status) !== "review_required") throw new Error("The exact run must reach the terminal human-review boundary before its reviewer queue can open.");
      if (next.read_only !== true) throw new Error("The protected reviewer queue did not preserve its read-only contract.");
      if (text(next.source) !== "canonical_terminal_comprehensive_report_json") throw new Error("The reviewer queue is not bound to the terminal canonical Comprehensive report.");
      if (next.human_review_required !== true || next.client_delivery_allowed === true) throw new Error("The exact run does not preserve the mandatory pre-approval human-review boundary.");
      const queue = buildQueue(next);
      setPayload(next); setModel(queue);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the exact review queue.");
    } finally {
      setAdminToken("");
      setLoading(false);
    }
  }

  return <main className={styles.shell} data-review-queue-contract="exception-first-v1" data-human-disposition-controls="absent" data-client-delivery-authorization="absent">
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO PHASE 2 · WORK PACKAGE 1</p>
      <h1>Exception-first technical review queue</h1>
      <p>Review candidates that require individual attention first, followed by deterministic grouped work units from the same immutable Comprehensive report package.</p>
      <div className={styles.boundary}>Authenticated, read-only technical review routing. No candidate disposition, reviewer identity, risk acceptance, approval, score change, or client-delivery authorization is created here.</div>
    </section>
    <section className={styles.panel}>
      <h2>Open an exact terminal run</h2>
      <form className={styles.form} onSubmit={loadQueue}>
        <label>Exact Comprehensive run ID<input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        <label>Operator admin token<input type="password" value={adminToken} onChange={(event) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} /></label>
        <button type="submit" disabled={loading || !runId.trim() || !adminToken.trim()}>{loading ? "Loading exact queue…" : "Load reviewer queue"}</button>
      </form>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
    </section>
    {payload && model ? <>
      <section className={styles.identity} aria-label="Exact run identity">
        <div><span>Run</span><strong>{payload.run_id || runId}</strong></div><div><span>Commit</span><strong>{payload.commit_sha}</strong></div>
        <div><span>Review</span><strong>Human required</strong></div><div><span>Client delivery</span><strong>{payload.client_delivery_allowed === true ? "Authorized elsewhere" : "Blocked"}</strong></div>
      </section>
      <section className={styles.metrics} aria-label="Canonical review workload">
        <article><span>Canonical candidates</span><strong>{model.candidateCount}</strong></article><article><span>Individual work units</span><strong>{model.individualUnits.length}</strong></article>
        <article><span>Grouped work units</span><strong>{model.groupedUnits.length}</strong></article><article><span>Total work units</span><strong>{model.units.length}</strong></article>
      </section>
      {model.integrityErrors.length ? <section className={styles.integrityError} role="alert"><strong>Queue integrity check failed closed.</strong><ul>{model.integrityErrors.map((item) => <li key={item}>{item}</li>)}</ul></section> : <section className={styles.integrityOk}><strong>Canonical parity verified.</strong> Every retained candidate appears exactly once and the work-unit total reconciles with the report.</section>}
      <section className={styles.queueSection}>
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>FIRST</p><h2>Individual attention</h2></div><strong>{model.individualUnits.length} work units</strong></div>
        <div className={styles.queue}>{model.individualUnits.map((unit) => <article className={styles.candidateCard} key={unit.id}><CandidateSummary candidate={unit.representative} /></article>)}</div>
      </section>
      <section className={styles.queueSection}>
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>THEN</p><h2>Deterministic grouped work units</h2></div><strong>{model.groupedUnits.length} work units</strong></div>
        <p className={styles.sectionLead}>Groups are presentation-only. Every underlying candidate identity remains visible and no group action or human disposition is available in this work package.</p>
        <div className={styles.queue}>{model.groupedUnits.map((unit) => <article className={styles.groupCard} key={unit.id}>
          <div className={styles.groupTitle}><div><span>Cluster</span><code>{unit.id}</code></div><strong>{unit.candidates.length} candidates</strong></div>
          <CandidateSummary candidate={unit.representative} />
          <div className={styles.identityList} aria-label={`Candidate identities in ${unit.id}`}>{unit.candidates.map((candidate) => <code key={candidateId(candidate)}>{candidateId(candidate)}</code>)}</div>
        </article>)}</div>
      </section>
    </> : null}
  </main>;
}
