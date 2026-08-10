"use client";

import {useEffect, useState} from "react";
import type {ChangeEvent, FormEvent, SyntheticEvent} from "react";
import styles from "./reviewer-queue.module.css";

type JsonRecord = Record<string, unknown>;
type ReviewQueuePayload = {
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  evidence_ledger_id?: string;
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
type QueueUnit = {
  id: string;
  kind: "individual" | "group";
  candidates: JsonRecord[];
  representative: JsonRecord;
  cluster: JsonRecord;
};
type QueueModel = {
  units: QueueUnit[];
  individualUnits: QueueUnit[];
  groupedUnits: QueueUnit[];
  candidateCount: number;
  clusterCount: number;
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
function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || text(value) === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
function sameList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}
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
function addMetricError(errors: string[], value: unknown, actual: number, label: string): void {
  const expected = finiteNumber(value);
  if (expected === null || expected !== actual) errors.push(`${label} does not reconcile with the canonical cluster workload.`);
}

function buildQueue(payload: ReviewQueuePayload): QueueModel {
  const register = canonicalRegister(payload);
  if (!Array.isArray(register.findings)) throw new Error("The exact terminal report does not contain a canonical scanner candidate register.");
  const findings = asRecords(register.findings);
  const triage = asRecord(register.technical_triage);
  const integrityErrors: string[] = [];
  const rawClusters = register.review_workload_clusters;
  if (!Array.isArray(rawClusters)) integrityErrors.push("Canonical deterministic cluster metadata is unavailable.");
  const clusterRecords = asRecords(rawClusters);
  if (Array.isArray(rawClusters) && clusterRecords.length !== rawClusters.length) integrityErrors.push("Canonical cluster metadata contains a malformed record.");

  const candidateById = new Map<string, JsonRecord>();
  const sourceIds: string[] = [];
  for (const candidate of findings) {
    const id = text(candidate.candidate_id);
    if (!id) {
      integrityErrors.push("A canonical candidate identity is missing.");
      continue;
    }
    sourceIds.push(id);
    if (candidateById.has(id)) integrityErrors.push(`Candidate identity ${id} is duplicated.`);
    candidateById.set(id, candidate);
    const exactCommit = text(candidate.exact_commit_sha);
    if (exactCommit !== text(payload.commit_sha)) integrityErrors.push(`Candidate ${id} does not match the exact run commit.`);
    if (candidate.human_review_required !== true || candidate.client_delivery_allowed === true) integrityErrors.push(`Candidate ${id} does not preserve the mandatory pre-approval review boundary.`);
    if (candidate.human_disposition !== null && candidate.human_disposition !== undefined) integrityErrors.push(`Candidate ${id} already contains a human disposition outside this read-only work package.`);
  }

  const observedClusterIds = new Set<string>();
  const clusteredCandidateIds: string[] = [];
  const builtUnits: QueueUnit[] = [];
  clusterRecords.forEach((cluster, index) => {
    const clusterId = text(cluster.cluster_id);
    if (!clusterId) integrityErrors.push(`Cluster record ${index + 1} has no canonical identity.`);
    if (clusterId && observedClusterIds.has(clusterId)) integrityErrors.push(`Cluster identity ${clusterId} is duplicated.`);
    if (clusterId) observedClusterIds.add(clusterId);

    const candidateIds = textList(cluster.candidate_ids);
    if (!Array.isArray(cluster.candidate_ids)) integrityErrors.push(`Cluster ${clusterId || index + 1} has no canonical candidate list.`);
    if (new Set(candidateIds).size !== candidateIds.length) integrityErrors.push(`Cluster ${clusterId || index + 1} repeats a candidate identity.`);
    const declaredCount = finiteNumber(cluster.candidate_record_count);
    const declaredSize = finiteNumber(cluster.cluster_size);
    if (declaredCount !== candidateIds.length || declaredSize !== candidateIds.length) integrityErrors.push(`Cluster ${clusterId || index + 1} size does not match its candidate list.`);

    const grouped = cluster.grouped_review_eligible === true;
    const candidates: JsonRecord[] = [];
    for (const id of candidateIds) {
      clusteredCandidateIds.push(id);
      const candidate = candidateById.get(id);
      if (!candidate) {
        integrityErrors.push(`Cluster ${clusterId || index + 1} references unknown candidate ${id}.`);
        continue;
      }
      candidates.push(candidate);
      if (text(candidate.cluster_id) !== clusterId) integrityErrors.push(`Candidate ${id} does not match cluster ${clusterId}.`);
      if (finiteNumber(candidate.cluster_size) !== candidateIds.length) integrityErrors.push(`Candidate ${id} has inconsistent cluster size.`);
      if (!sameList(textList(candidate.cluster_candidate_ids), candidateIds)) integrityErrors.push(`Candidate ${id} has inconsistent deterministic cluster membership.`);
      if (text(candidate.representative_candidate_id) !== text(cluster.representative_candidate_id)) integrityErrors.push(`Candidate ${id} has inconsistent representative identity.`);
      if (candidate.grouped_review_eligible !== cluster.grouped_review_eligible) integrityErrors.push(`Candidate ${id} has inconsistent grouped-review eligibility.`);
      if (candidate.homogeneous_evidence !== cluster.homogeneous_evidence || candidate.homogeneous_verdict !== cluster.homogeneous_verdict) integrityErrors.push(`Candidate ${id} has inconsistent cluster homogeneity metadata.`);
      const expectedReviewUnit = grouped ? clusterId : id;
      if (text(candidate.review_unit_id) !== expectedReviewUnit) integrityErrors.push(`Candidate ${id} has inconsistent deterministic review-unit identity.`);
    }

    const routingClasses = Array.from(new Set(candidates.map((candidate) => text(candidate.review_routing_class)).filter(Boolean))).sort();
    const declaredRoutingClasses = textList(cluster.review_routing_classes).sort();
    if (!sameList(routingClasses, declaredRoutingClasses)) integrityErrors.push(`Cluster ${clusterId || index + 1} has inconsistent review-routing classes.`);
    if (!text(cluster.cluster_reason) || !text(cluster.homogeneous_evidence_basis)) integrityErrors.push(`Cluster ${clusterId || index + 1} is missing its deterministic grouping basis.`);

    const representativeId = text(cluster.representative_candidate_id);
    const representative = candidates.find((candidate) => candidateId(candidate) === representativeId);
    if (!representative || !candidateIds.includes(representativeId)) integrityErrors.push(`Cluster ${clusterId || index + 1} has an invalid representative candidate.`);
    if (grouped) {
      if (cluster.grouped_human_review_cluster !== true || candidateIds.length < 2) integrityErrors.push(`Cluster ${clusterId || index + 1} is not a valid grouped human-review unit.`);
      if (cluster.homogeneous_evidence !== true || cluster.homogeneous_verdict !== true) integrityErrors.push(`Cluster ${clusterId || index + 1} is not homogeneous enough for grouped review.`);
      if (candidates.some((candidate) => candidate.grouped_review_eligible !== true || candidate.review_requires_individual_attention === true)) integrityErrors.push(`Cluster ${clusterId || index + 1} contains a candidate that requires individual attention.`);
    } else {
      if (cluster.grouped_human_review_cluster === true || candidateIds.length !== 1) integrityErrors.push(`Individual cluster ${clusterId || index + 1} does not contain exactly one candidate.`);
      if (candidates.some((candidate) => candidate.grouped_review_eligible === true || candidate.review_requires_individual_attention !== true)) integrityErrors.push(`Individual cluster ${clusterId || index + 1} has inconsistent routing.`);
    }
    if (cluster.underlying_candidate_disposition_required !== true) integrityErrors.push(`Cluster ${clusterId || index + 1} does not preserve candidate-level human disposition requirements.`);

    if (candidates.length) {
      builtUnits.push({
        id: grouped ? clusterId : candidateId(candidates[0]),
        kind: grouped ? "group" : "individual",
        candidates: [...candidates],
        representative: representative || candidates[0],
        cluster,
      });
    }
  });

  const queuedIds = clusteredCandidateIds;
  if (new Set(sourceIds).size !== sourceIds.length) integrityErrors.push("Candidate identities are not unique.");
  if (queuedIds.length !== findings.length || new Set(queuedIds).size !== findings.length || sourceIds.some((id) => !queuedIds.includes(id))) integrityErrors.push("Deterministic clusters do not preserve every canonical candidate exactly once.");

  const individualUnits = builtUnits.filter((unit) => unit.kind === "individual").sort((left, right) => compareCandidates(left.representative, right.representative));
  const groupedUnits = builtUnits.filter((unit) => unit.kind === "group").sort((left, right) => compareCandidates(left.representative, right.representative) || left.id.localeCompare(right.id));
  const units = [...individualUnits, ...groupedUnits];
  const groupedCandidateCount = groupedUnits.reduce((total, unit) => total + unit.candidates.length, 0);
  const individualCandidateCount = individualUnits.reduce((total, unit) => total + unit.candidates.length, 0);
  const declaredCandidateCount = finiteNumber(register.candidate_record_count);
  const candidateCount = declaredCandidateCount ?? findings.length;

  if (candidateCount !== findings.length) integrityErrors.push("Candidate count does not match the canonical register.");
  addMetricError(integrityErrors, triage.total_candidates, findings.length, "Total candidate count");
  addMetricError(integrityErrors, triage.cluster_count, clusterRecords.length, "Cluster count");
  addMetricError(integrityErrors, triage.grouped_review_cluster_count, groupedUnits.length, "Grouped cluster count");
  addMetricError(integrityErrors, triage.candidates_eligible_for_grouped_review, groupedCandidateCount, "Grouped candidate count");
  addMetricError(integrityErrors, triage.grouped_human_review_candidate_count, groupedCandidateCount, "Grouped human-review candidate count");
  addMetricError(integrityErrors, triage.candidates_requiring_individual_human_attention, individualCandidateCount, "Individual-attention candidate count");
  addMetricError(integrityErrors, triage.individual_human_review_record_count, individualCandidateCount, "Individual review record count");
  const expectedWorkUnits = finiteNumber(triage.human_review_work_units);
  if (expectedWorkUnits === null || expectedWorkUnits !== units.length) integrityErrors.push("Human-review work-unit count does not reconcile with the canonical cluster workload.");
  if (!Array.isArray(triage.review_workload_clusters) || JSON.stringify(triage.review_workload_clusters) !== JSON.stringify(rawClusters)) integrityErrors.push("Top-level and technical-triage cluster records are not identical.");
  if (finiteNumber(payload.candidate_count) !== candidateCount) integrityErrors.push("Protected queue candidate count does not match the canonical register.");
  if (finiteNumber(payload.human_review_work_units) !== units.length) integrityErrors.push("Protected queue work-unit count does not reconcile with the displayed queue.");

  return {units, individualUnits, groupedUnits, candidateCount, clusterCount: clusterRecords.length, integrityErrors: Array.from(new Set(integrityErrors))};
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
      <div><dt>Rule or advisory</dt><dd>{text(candidate.rule) || text(candidate.rule_id) || text(candidate.advisory) || "not stated"}</dd></div>
      <div><dt>Package context</dt><dd>{[text(candidate.dependency_package), text(candidate.dependency_version), text(candidate.dependency_ecosystem)].filter(Boolean).join(" · ") || "not applicable"}</dd></div>
      <div><dt>Production scope</dt><dd>{text(candidate.production_test_development_scope) || text(candidate.production_classification) || "not stated"}</dd></div>
      <div><dt>Analysis model</dt><dd>{text(candidate.technical_triage_model_or_version) || text(candidate.technical_triage_source) || "not stated"}</dd></div>
      <div><dt>Reachability</dt><dd>{text(candidate.reachability_assessment) || text(candidate.reachability) || "not established"}</dd></div>
      <div><dt>Exploitability</dt><dd>{text(candidate.exploitability_assessment) || "not established"}</dd></div>
      <div><dt>Environment relevance</dt><dd>{text(candidate.environment_relevance) || "not established"}</dd></div>
      <div><dt>Boundary assessment</dt><dd>{text(candidate.technical_triage_boundary_assessment) || text(candidate.boundary_assessment) || "not established"}</dd></div>
    </dl>
    <div className={styles.evidenceGrid}>
      <section><h4>Evidence used</h4><pre>{JSON.stringify(candidate.evidence_used ?? candidate.evidence ?? [], null, 2)}</pre></section>
      <section><h4>Counterevidence</h4><pre>{JSON.stringify(candidate.counterevidence ?? [], null, 2)}</pre></section>
    </div>
    <p>{text(candidate.technical_triage_rationale) || "No automated rationale was retained."}</p>
    {proofGaps.length ? <p className={styles.proofGap}><strong>Proof gaps:</strong> {proofGaps.join(" · ")}</p> : null}
    {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step) ? <p><strong>Recommended next step:</strong> {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step)}</p> : null}
  </>;
}

function CandidateDisclosure({candidate, representative = false}: {candidate: JsonRecord; representative?: boolean}) {
  const [open, setOpen] = useState(false);
  const title = text(candidate.title) || text(candidate.rule) || text(candidate.advisory) || "Technical review candidate";
  return <details className={styles.candidateDisclosure} data-candidate-id={candidateId(candidate)} onToggle={(event: SyntheticEvent<HTMLDetailsElement>) => setOpen(event.currentTarget.open)}>
    <summary className={styles.candidateSummary}>
      <span className={styles.summaryIdentity}><code>{candidateId(candidate)}</code><strong>{title}</strong></span>
      <span className={styles.summaryMeta}>{representative ? "Representative · " : ""}{text(candidate.category) || "uncategorized"}</span>
      <span className={styles.disclosureState}><span className={styles.closedLabel}>Expand candidate</span><span className={styles.openLabel}>Collapse candidate</span></span>
    </summary>
    {open ? <div className={styles.candidateBody}>
      <CandidateSummary candidate={candidate} />
      <section className={styles.canonicalRecord} data-canonical-candidate-record="true" aria-label={`Complete canonical record for ${candidateId(candidate)}`}>
        <h4>Complete retained canonical candidate record</h4>
        <p>All retained evidence, counterevidence, source context, dependency context, scope, reachability, exploitability, proof gaps, lineage, clustering, and technical-triage fields are shown below without creating a human disposition.</p>
        <pre>{JSON.stringify(candidate, null, 2)}</pre>
      </section>
    </div> : null}
  </details>;
}

function ClusterDisclosure({unit}: {unit: QueueUnit}) {
  const [open, setOpen] = useState(false);
  const cluster = unit.cluster;
  return <details className={styles.clusterDisclosure} data-cluster-id={unit.id} onToggle={(event: SyntheticEvent<HTMLDetailsElement>) => setOpen(event.currentTarget.open)}>
    <summary className={styles.clusterSummary}>
      <span className={styles.summaryIdentity}><span>Cluster</span><code>{unit.id}</code></span>
      <span className={styles.summaryMeta}>{unit.candidates.length} candidates · {textList(cluster.review_routing_classes).join(" · ") || "technical review"}</span>
      <span className={styles.disclosureState}><span className={styles.closedLabel}>Expand cluster</span><span className={styles.openLabel}>Collapse cluster</span></span>
    </summary>
    {open ? <div className={styles.clusterBody}>
      <dl className={styles.clusterGrid}>
        <div><dt>Cluster reason</dt><dd>{text(cluster.cluster_reason) || "not stated"}</dd></div>
        <div><dt>Representative</dt><dd><code>{candidateId(unit.representative)}</code></dd></div>
        <div><dt>Evidence homogeneity</dt><dd>{cluster.homogeneous_evidence === true ? "Verified" : "Not verified"}</dd></div>
        <div><dt>Verdict homogeneity</dt><dd>{cluster.homogeneous_verdict === true ? "Verified" : "Not verified"}</dd></div>
      </dl>
      {text(cluster.homogeneous_evidence_basis) ? <p className={styles.clusterBasis}><strong>Homogeneity basis:</strong> {text(cluster.homogeneous_evidence_basis)}</p> : null}
      <p className={styles.clusterBoundary}>The cluster summary is routing context only. Every underlying candidate remains canonical, independently expandable, and subject to an explicit later human disposition.</p>
      <div className={styles.clusterCandidates} aria-label={`Underlying candidates in ${unit.id}`}>
        {unit.candidates.map((candidate) => <CandidateDisclosure key={candidateId(candidate)} candidate={candidate} representative={candidateId(candidate) === candidateId(unit.representative)} />)}
      </div>
    </div> : null}
  </details>;
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
      const requestedRunId = runId.trim();
      const response = await fetch(new URL(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(requestedRunId)}/review-queue`, window.location.origin), {
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken.trim()},
      });
      if (!response.ok) throw new Error(`Unable to load the exact protected review queue (${response.status}).`);
      const next = await response.json() as ReviewQueuePayload;
      if (text(next.run_id) !== requestedRunId || !text(next.repository) || !text(next.commit_sha) || !text(next.evidence_ledger_id)) throw new Error("The protected reviewer queue did not preserve the exact canonical run identity.");
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

  return <main className={styles.shell} data-review-queue-contract="exception-first-v1" data-expandable-clusters-contract="canonical-read-only-v1" data-human-disposition-controls="absent" data-client-delivery-authorization="absent">
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO PHASE 2 · WORK PACKAGE 2</p>
      <h1>Expandable deterministic review clusters</h1>
      <p>Review individual exceptions first, then expand deterministic clusters and every underlying candidate without leaving the same immutable NICO Comprehensive run.</p>
      <div className={styles.boundary}>Authenticated, read-only technical review routing. Cluster summaries never replace candidate evidence. No candidate disposition, reviewer identity, risk acceptance, approval, score change, or client-delivery authorization is created here.</div>
    </section>
    <section className={styles.panel}>
      <h2>Open an exact terminal run</h2>
      <form className={styles.form} onSubmit={loadQueue}>
        <label>Exact Comprehensive run ID<input value={runId} onChange={(event: ChangeEvent<HTMLInputElement>) => setRunId(event.target.value)} placeholder="comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        <label>Operator admin token<input type="password" value={adminToken} onChange={(event: ChangeEvent<HTMLInputElement>) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} /></label>
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
        <article><span>Canonical candidates</span><strong>{model.candidateCount}</strong></article><article><span>Deterministic clusters</span><strong>{model.clusterCount}</strong></article>
        <article><span>Individual work units</span><strong>{model.individualUnits.length}</strong></article><article><span>Grouped work units</span><strong>{model.groupedUnits.length}</strong></article><article><span>Total work units</span><strong>{model.units.length}</strong></article>
      </section>
      {model.integrityErrors.length ? <section className={styles.integrityError} role="alert"><strong>Queue integrity check failed closed.</strong><p>No candidate or cluster content is displayed until exact candidate, cluster, identity, and workload parity is restored.</p><ul>{model.integrityErrors.map((item) => <li key={item}>{item}</li>)}</ul></section> : <>
        <section className={styles.integrityOk}><strong>Canonical parity verified.</strong> Every retained candidate appears exactly once, deterministic cluster membership matches the canonical register, and the work-unit total reconciles with the report.</section>
        <section className={styles.queueSection}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>FIRST</p><h2>Individual attention</h2></div><strong>{model.individualUnits.length} work units</strong></div>
          <p className={styles.sectionLead}>Each candidate expands into its complete retained canonical evidence and technical-triage record.</p>
          <div className={styles.queue}>{model.individualUnits.map((unit) => <CandidateDisclosure key={unit.id} candidate={unit.representative} />)}</div>
        </section>
        <section className={styles.queueSection}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>THEN</p><h2>Deterministic grouped work units</h2></div><strong>{model.groupedUnits.length} work units</strong></div>
          <p className={styles.sectionLead}>Expand a cluster to inspect its deterministic basis and then expand every underlying candidate. Groups are presentation-only and never replace candidate identities, evidence, or later human dispositions.</p>
          <div className={styles.queue}>{model.groupedUnits.map((unit) => <ClusterDisclosure key={unit.id} unit={unit} />)}</div>
        </section>
      </>}
    </> : null}
  </main>;
}
