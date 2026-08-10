"use client";

import {FormEvent, useEffect, useState} from "react";
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
};
const TRIAGE_VERDICTS = new Set(["not_actionable", "needs_review", "confirmed"]);
const ROUTING_CLASSES = new Set(["CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW", "AUTOMATED_TRIAGE_COMPLETE", "STABLE_CARRY_FORWARD", "QUALITY_CONTROL_ELIGIBLE"]);

type QueueModel = {
  units: QueueUnit[];
  individualUnits: QueueUnit[];
  groupedUnits: QueueUnit[];
  candidateCount: number;
  clusterCount: number;
  groupedCandidateCount: number;
  individualCandidateCount: number;
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
function candidateId(candidate: JsonRecord): string { return text(candidate.candidate_id); }
function candidateDisplayId(candidate: JsonRecord): string { return candidateId(candidate) || "candidate-id-missing"; }
function canonicalRegister(payload: ReviewQueuePayload): JsonRecord { return asRecord(payload.candidate_register); }
function numberOrNaN(value: unknown): number { return typeof value === "number" ? value : Number(value); }
function sortedUnique(values: string[]): string[] { return Array.from(new Set(values)).sort((left, right) => left.localeCompare(right)); }
function sameMembers(left: string[], right: string[]): boolean {
  const normalizedLeft = sortedUnique(left);
  const normalizedRight = sortedUnique(right);
  return normalizedLeft.length === normalizedRight.length
    && normalizedLeft.every((item, index) => item === normalizedRight[index]);
}
function domToken(value: string): string { return Array.from(value).map((item) => item.codePointAt(0)?.toString(16) || "0").join("-"); }
function toggleSet(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  if (next.has(value)) next.delete(value); else next.add(value);
  return next;
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
    || candidateDisplayId(left).localeCompare(candidateDisplayId(right));
}

function buildQueue(payload: ReviewQueuePayload): QueueModel {
  const register = canonicalRegister(payload);
  if (!Array.isArray(register.findings)) throw new Error("The exact terminal report does not contain a canonical scanner candidate register.");
  const findings = asRecords(register.findings);
  const integrityErrors = new Set<string>();
  const addError = (message: string) => integrityErrors.add(message);
  const expectedCommit = text(payload.commit_sha);
  const expectedRepository = text(payload.repository).toLowerCase();
  const sourceIds = findings.map(candidateId);
  const subject = asRecord(register.assessment_subject);
  const canonicalDigest = text(register.canonical_digest_sha256);
  const sourceDigest = text(register.source_canonical_digest_sha256);

  if (text(register.status) !== "complete") addError("The canonical register is not complete.");
  if (sourceIds.some((item) => !item)) addError("Every canonical candidate must retain a non-empty candidate ID.");
  if (new Set(sourceIds).size !== sourceIds.length) addError("Candidate identities are not unique.");
  if (register.count_parity_verified !== true) addError("The canonical register did not retain its candidate-count parity proof.");
  if (register.candidate_record_count_matches_raw !== true) addError("The canonical register does not reconcile with its retained raw candidate count.");
  if (register.every_raw_candidate_has_stable_identity !== true) addError("The canonical register does not prove stable identity for every retained raw candidate.");
  if (register.mutually_exclusive_dispositions_verified !== true) addError("The canonical register did not retain its mutually-exclusive disposition proof.");
  if (register.raw_payload_retention_complete !== true) addError("The canonical register does not prove complete retained candidate payload coverage.");
  if (register.projection_redaction_preserves_source_fingerprints !== true) addError("The canonical reviewer projection does not prove redaction-preserving source fingerprints.");
  if (register.candidate_evidence_quality_totals_match_source !== true || register.source_evidence_quality_preserved !== true) addError("The canonical reviewer projection does not preserve source evidence-quality totals.");
  if (Array.isArray(register.discrepancies) && register.discrepancies.length) addError("The canonical register retains unresolved reconciliation discrepancies.");
  if (!canonicalDigest || !sourceDigest || canonicalDigest !== sourceDigest || !text(register.rendered_projection_digest_sha256)) addError("The canonical register does not retain complete source and rendered projection digests.");
  if (expectedCommit && text(register.exact_commit_sha) !== expectedCommit) addError("The canonical register commit does not match the exact terminal run.");
  if (expectedRepository && text(subject.repository).toLowerCase() !== expectedRepository) addError("The canonical register repository does not match the exact terminal run.");

  const clusters = new Map<string, JsonRecord[]>();
  for (const candidate of findings) {
    const id = candidateDisplayId(candidate);
    const clusterId = text(candidate.cluster_id);
    const grouped = candidate.grouped_review_eligible === true;
    const individual = candidate.review_requires_individual_attention === true;

    if (!clusterId) addError(`${id} does not retain a deterministic cluster ID.`);
    else clusters.set(clusterId, [...(clusters.get(clusterId) || []), candidate]);
    if (grouped && individual) addError(`${id} is assigned to both grouped and individual review.`);
    if (!grouped && !individual) addError(`${id} is not assigned to an exception-first review work unit.`);
    if (expectedCommit && text(candidate.exact_commit_sha) !== expectedCommit) addError(`${id} does not match the exact terminal commit.`);
    if (!TRIAGE_VERDICTS.has(text(candidate.technical_triage_verdict))) addError(`${id} does not retain a valid proposal-only technical-triage verdict.`);
    if (!ROUTING_CLASSES.has(text(candidate.review_routing_class))) addError(`${id} does not retain a valid reviewer-routing class.`);
    if (!text(candidate.technical_triage_status) || !text(candidate.technical_triage_confidence) || !text(candidate.technical_triage_rationale) || !text(candidate.technical_triage_source)) {
      addError(`${id} does not retain the complete proposal-only technical-triage context.`);
    }
    if (candidate.human_review_required !== true) addError(`${id} does not preserve mandatory human review.`);
    if (text(candidate.human_approval_status) !== "pending" || text(candidate.technical_triage_human_approval_status) !== "pending") addError(`${id} does not preserve pending human approval.`);
    if (candidate.human_approval_carried_forward !== false || candidate.technical_triage_human_approval_carried_forward !== false) addError(`${id} contains an impermissible carried-forward human approval.`);
    if (candidate.review_grouping_is_human_decision !== false || candidate.review_routing_is_human_decision !== false) addError(`${id} misrepresents automated routing as a human decision.`);
    if (candidate.human_disposition) addError(`${id} contains an automation-created human disposition.`);
    if (candidate.reviewer_identity) addError(`${id} contains an automation-created reviewer identity.`);
    if (candidate.technical_triage_client_delivery_allowed !== false) addError(`${id} does not preserve blocked pre-approval client delivery.`);
    if (!text(candidate.evidence_digest_sha256) || !text(candidate.raw_fingerprint)) addError(`${id} does not retain canonical evidence identity.`);
    if (!Array.isArray(candidate.evidence_used) || !Array.isArray(candidate.counterevidence) || !Array.isArray(candidate.proof_gaps)) {
      addError(`${id} does not retain the complete evidence, counterevidence, and proof-gap arrays.`);
    }
    if (text(candidate.category).toLowerCase() === "secret") {
      const evidence = text(candidate.evidence).toLowerCase();
      if (evidence && !evidence.includes("redacted") && !evidence.includes("without a human-readable message")) {
        addError(`${id} contains secret evidence that is not safely redacted for the reviewer projection.`);
      }
    }
  }

  const groupedClusters = new Map<string, JsonRecord[]>();
  for (const [clusterId, members] of clusters.entries()) {
    const actualIds = members.map(candidateId);
    const representativeIds = sortedUnique(members.map((item) => text(item.representative_candidate_id)));
    const reasons = sortedUnique(members.map((item) => text(item.cluster_reason)));
    const verdicts = sortedUnique(members.map((item) => text(item.technical_triage_verdict)));
    const reviewUnitIds = sortedUnique(members.map((item) => text(item.review_unit_id)));
    const groupedMembers = members.filter((item) => item.grouped_review_eligible === true);
    const individualMembers = members.filter((item) => item.review_requires_individual_attention === true);

    for (const member of members) {
      const id = candidateDisplayId(member);
      if (numberOrNaN(member.cluster_size) !== members.length) addError(`${id} has a cluster size that does not match ${clusterId}.`);
      if (!sameMembers(textList(member.cluster_candidate_ids), actualIds)) addError(`${id} has deterministic cluster membership that does not match ${clusterId}.`);
      if (member.homogeneous_evidence !== true || member.homogeneous_verdict !== true) addError(`${clusterId} is not supported by homogeneous evidence and verdict metadata.`);
    }
    if (representativeIds.length !== 1 || !actualIds.includes(representativeIds[0])) addError(`${clusterId} does not retain one valid representative candidate.`);
    if (reasons.length !== 1 || !reasons[0]) addError(`${clusterId} does not retain one deterministic cluster reason.`);
    if (verdicts.length !== 1) addError(`${clusterId} contains conflicting technical-triage verdicts.`);
    if (reviewUnitIds.length !== 1 || !reviewUnitIds[0]) addError(`${clusterId} does not retain one deterministic review work-unit identity.`);

    if (groupedMembers.length) {
      if (groupedMembers.length !== members.length || individualMembers.length) addError(`${clusterId} mixes grouped and individual review routing.`);
      if (members.length < 2) addError(`${clusterId} is marked for grouped review but contains fewer than two candidates.`);
      if (reviewUnitIds[0] !== clusterId) addError(`${clusterId} does not use its cluster identity as the grouped review work-unit identity.`);
      groupedClusters.set(clusterId, members);
    } else if (members.length === 1 && reviewUnitIds[0] !== actualIds[0]) {
      addError(`${clusterId} does not preserve its candidate identity as the individual review work-unit identity.`);
    }
  }

  const individuals = findings.filter((candidate) => candidate.review_requires_individual_attention === true);
  const individualUnits: QueueUnit[] = [...individuals].sort(compareCandidates).map((candidate) => ({
    id: candidateDisplayId(candidate), kind: "individual", candidates: [candidate], representative: candidate,
  }));
  const groupedUnits: QueueUnit[] = Array.from(groupedClusters.entries()).map(([clusterId, candidates]) => {
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
  const declaredCandidateCount = numberOrNaN(register.candidate_record_count);
  const candidateCount = Number.isFinite(declaredCandidateCount) ? declaredCandidateCount : findings.length;
  const groupedCandidateCount = groupedUnits.reduce((total, unit) => total + unit.candidates.length, 0);
  const individualCandidateCount = individualUnits.length;
  const queuedIds = units.flatMap((unit) => unit.candidates.map(candidateId));

  if (candidateCount !== findings.length) addError("Candidate count does not match the canonical register.");
  if (new Set(queuedIds).size !== findings.length || queuedIds.length !== findings.length || !sameMembers(queuedIds, sourceIds)) {
    addError("The queue does not preserve every canonical candidate exactly once.");
  }
  const expectedWorkUnits = numberOrNaN(triage.human_review_work_units);
  if (Number.isFinite(expectedWorkUnits) && expectedWorkUnits !== units.length) addError("Displayed work units do not reconcile with the canonical workload metric.");
  const expectedCandidates = numberOrNaN(triage.total_candidates);
  if (Number.isFinite(expectedCandidates) && expectedCandidates !== findings.length) addError("Technical-triage candidate totals do not reconcile with the canonical register.");
  const expectedIndividual = numberOrNaN(triage.candidates_requiring_individual_human_attention);
  if (Number.isFinite(expectedIndividual) && expectedIndividual !== individualCandidateCount) addError("Individual-attention candidates do not reconcile with the canonical workload metric.");
  const expectedGrouped = numberOrNaN(triage.candidates_eligible_for_grouped_review);
  if (Number.isFinite(expectedGrouped) && expectedGrouped !== groupedCandidateCount) addError("Grouped-review candidates do not reconcile with the canonical workload metric.");
  const expectedClusters = numberOrNaN(triage.cluster_count);
  if (Number.isFinite(expectedClusters) && expectedClusters !== clusters.size) addError("Deterministic cluster totals do not reconcile with the canonical workload metric.");
  if (Number.isFinite(numberOrNaN(payload.candidate_count)) && numberOrNaN(payload.candidate_count) !== candidateCount) addError("Protected queue candidate count does not match the canonical register.");
  if (Number.isFinite(numberOrNaN(payload.human_review_work_units)) && numberOrNaN(payload.human_review_work_units) !== units.length) addError("Protected queue work-unit count does not reconcile with the displayed queue.");

  return {
    units,
    individualUnits,
    groupedUnits,
    candidateCount,
    clusterCount: clusters.size,
    groupedCandidateCount,
    individualCandidateCount,
    integrityErrors: Array.from(integrityErrors),
  };
}

function evidenceLabel(candidate: JsonRecord): string {
  const location = text(candidate.source_path) || text(candidate.path) || text(candidate.manifest_path) || text(candidate.advisory) || text(candidate.rule) || text(candidate.rule_id) || "Evidence location retained in the canonical register";
  const line = text(candidate.line);
  const column = text(candidate.column);
  return line ? `${location}:${line}${column ? `:${column}` : ""}` : location;
}
function CandidateSummary({candidate, representative = false}: {candidate: JsonRecord; representative?: boolean}) {
  const proofGaps = textList(candidate.technical_triage_proof_gaps || candidate.proof_gaps);
  return <>
    <div className={styles.candidateHeader}>
      <code>{candidateDisplayId(candidate)}</code>
      <span>{text(candidate.category) || "uncategorized"}</span>
      <span>{text(candidate.review_routing_class).replaceAll("_", " ") || "review routing unavailable"}</span>
      {representative ? <span className={styles.representativeBadge}>representative</span> : null}
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
    {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step) ? <p><strong>Recommended next step:</strong> {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step)}</p> : null}
  </>;
}

function CanonicalValue({value}: {value: unknown}) {
  if (value === undefined) return <span className={styles.emptyValue}>field unavailable</span>;
  if (value === null) return <code className={styles.scalarValue}>null</code>;
  if (value === "") return <span className={styles.emptyValue}>empty string</span>;
  if (typeof value === "boolean") return <code className={styles.scalarValue}>{value ? "true" : "false"}</code>;
  if (typeof value === "object") return <pre className={styles.jsonValue}>{JSON.stringify(value, null, 2)}</pre>;
  return <span className={styles.scalarValue}>{String(value)}</span>;
}
function CompleteCandidateRecord({candidate, regionId}: {candidate: JsonRecord; regionId: string}) {
  const entries = Object.entries(candidate).sort(([left], [right]) => left.localeCompare(right));
  return <section id={regionId} className={styles.canonicalPanel} role="region" aria-label={`Complete canonical evidence for ${candidateDisplayId(candidate)}`}>
    <div className={styles.canonicalIntro}>
      <strong>Complete canonical candidate record</strong>
      <span>Every retained evidence, lineage, clustering, and proposal-only technical-triage field is shown from the exact Comprehensive run. Secret values remain redacted by the canonical evidence projection.</span>
    </div>
    <dl className={styles.canonicalRecord}>
      {entries.map(([field, value]) => <div className={styles.canonicalField} key={field}><dt>{field}</dt><dd><CanonicalValue value={value} /></dd></div>)}
    </dl>
    <p className={styles.humanBoundary}>This is NICO technical-analysis evidence only. No human disposition, reviewer identity, risk acceptance, approval, or client-delivery authorization is created by expanding this record.</p>
  </section>;
}
function ExpansionButton({expanded, controls, onClick, expandLabel, collapseLabel}: {expanded: boolean; controls: string; onClick: () => void; expandLabel: string; collapseLabel: string}) {
  return <button type="button" className={styles.expandButton} aria-expanded={expanded} aria-controls={controls} onClick={onClick}>{expanded ? collapseLabel : expandLabel}</button>;
}
function CandidateReviewCard({candidate, expanded, onToggle, representative = false, member = false}: {candidate: JsonRecord; expanded: boolean; onToggle: () => void; representative?: boolean; member?: boolean}) {
  const id = candidateDisplayId(candidate);
  const regionId = `canonical-candidate-${domToken(id)}`;
  return <div className={member ? styles.memberCard : styles.candidateCard} data-candidate-id={id}>
    <CandidateSummary candidate={candidate} representative={representative} />
    <div className={styles.candidateActions}>
      <ExpansionButton expanded={expanded} controls={regionId} onClick={onToggle} expandLabel="Show complete retained evidence" collapseLabel="Hide complete retained evidence" />
    </div>
    {expanded ? <CompleteCandidateRecord candidate={candidate} regionId={regionId} /> : null}
  </div>;
}
function ClusterCard({unit, expanded, onToggleCluster, expandedCandidates, onToggleCandidate}: {unit: QueueUnit; expanded: boolean; onToggleCluster: () => void; expandedCandidates: Set<string>; onToggleCandidate: (id: string) => void}) {
  const regionId = `cluster-members-${domToken(unit.id)}`;
  const representativeId = text(unit.representative.representative_candidate_id) || candidateDisplayId(unit.representative);
  return <article className={styles.groupCard} data-cluster-id={unit.id}>
    <div className={styles.groupTitle}><div><span>Deterministic cluster</span><code>{unit.id}</code></div><strong>{unit.candidates.length} candidates</strong></div>
    <dl className={styles.clusterMeta}>
      <div><dt>Representative candidate</dt><dd><code>{representativeId}</code></dd></div>
      <div><dt>Technical verdict</dt><dd>{text(unit.representative.technical_triage_verdict).replaceAll("_", " ")}</dd></div>
      <div><dt>Evidence homogeneity</dt><dd>{unit.representative.homogeneous_evidence === true ? "verified" : "not verified"}</dd></div>
      <div><dt>Verdict homogeneity</dt><dd>{unit.representative.homogeneous_verdict === true ? "verified" : "not verified"}</dd></div>
    </dl>
    <p className={styles.clusterReason}><strong>Grouping basis:</strong> {text(unit.representative.cluster_reason)}</p>
    {text(unit.representative.homogeneous_evidence_basis) ? <p><strong>Homogeneity basis:</strong> {text(unit.representative.homogeneous_evidence_basis)}</p> : null}
    <div className={styles.representativeSummary}><CandidateSummary candidate={unit.representative} representative /></div>
    <ExpansionButton expanded={expanded} controls={regionId} onClick={onToggleCluster} expandLabel={`Expand ${unit.candidates.length} underlying candidates`} collapseLabel="Collapse underlying candidates" />
    {expanded ? <section id={regionId} className={styles.clusterMembers} role="region" aria-label={`Underlying candidates in ${unit.id}`}>
      <p className={styles.clusterNotice}>The cluster summary is routing context only. Each candidate below retains its own identity, source location, evidence, counterevidence, proof gaps, lineage, and technical-triage record.</p>
      {unit.candidates.map((candidate) => {
        const id = candidateDisplayId(candidate);
        return <CandidateReviewCard key={id} candidate={candidate} member representative={id === representativeId} expanded={expandedCandidates.has(id)} onToggle={() => onToggleCandidate(id)} />;
      })}
    </section> : null}
  </article>;
}

export default function ReviewerQueue() {
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [payload, setPayload] = useState<ReviewQueuePayload | null>(null);
  const [model, setModel] = useState<QueueModel | null>(null);
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(() => new Set());
  const [expandedCandidates, setExpandedCandidates] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setRunId(new URLSearchParams(window.location.search).get("run_id") || ""); }, []);

  async function loadQueue(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!runId.trim() || !adminToken.trim()) {
      setError("Enter the exact Comprehensive run ID and operator admin token.");
      return;
    }
    setLoading(true); setError(""); setPayload(null); setModel(null); setExpandedClusters(new Set()); setExpandedCandidates(new Set());
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

  const integrityFailed = Boolean(model?.integrityErrors.length);
  const visibleIntegrityErrors = model?.integrityErrors.slice(0, 100) || [];
  const hiddenIntegrityErrorCount = Math.max(0, (model?.integrityErrors.length || 0) - visibleIntegrityErrors.length);
  return <main className={styles.shell} data-review-queue-contract="exception-first-v1" data-cluster-expansion-contract="expandable-deterministic-clusters-v1" data-candidate-record-projection="complete-canonical-record" data-human-disposition-controls="absent" data-client-delivery-authorization="absent">
    <section className={styles.hero}>
      <p className={styles.eyebrow}>NICO PHASE 2 · WORK PACKAGE 2</p>
      <h1>Expandable deterministic cluster review</h1>
      <p>Review candidates requiring individual attention first, then expand deterministic groups and inspect every underlying candidate without leaving the same immutable NICO Comprehensive run.</p>
      <div className={styles.boundary}>Authenticated, read-only technical review. Cluster summaries never replace candidate-level evidence. No candidate disposition, reviewer identity, risk acceptance, approval, score change, or client-delivery authorization is created here.</div>
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
      {integrityFailed ? <section className={styles.integrityError} role="alert"><strong>Queue integrity check failed closed.</strong><p>Candidate and cluster evidence will not be displayed until exact-run parity is restored.</p><ul>{visibleIntegrityErrors.map((item) => <li key={item}>{item}</li>)}</ul>{hiddenIntegrityErrorCount ? <p>{hiddenIntegrityErrorCount} additional integrity errors were retained but not rendered.</p> : null}</section> : <>
        <section className={styles.integrityOk}><strong>Canonical parity verified.</strong> {model.candidateCount} candidates, {model.clusterCount} deterministic clusters, and {model.units.length} human-review work units reconcile with the exact report.</section>
        {model.candidateCount === 0 ? <section className={styles.emptyQueue}><strong>No scanner candidates are present in this exact run.</strong> Human review and approval boundaries remain unchanged.</section> : <>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>FIRST</p><h2>Individual attention</h2></div><strong>{model.individualUnits.length} work units</strong></div>
            <div className={styles.queue}>{model.individualUnits.map((unit) => {
              const id = candidateDisplayId(unit.representative);
              return <CandidateReviewCard key={unit.id} candidate={unit.representative} expanded={expandedCandidates.has(id)} onToggle={() => setExpandedCandidates((current) => toggleSet(current, id))} />;
            })}</div>
          </section>
          <section className={styles.queueSection}>
            <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>THEN</p><h2>Deterministic grouped work units</h2></div><strong>{model.groupedUnits.length} work units · {model.groupedCandidateCount} candidates</strong></div>
            <p className={styles.sectionLead}>Groups are presentation-only. Expand a cluster to inspect every underlying candidate, then expand any candidate to review its complete canonical record.</p>
            <div className={styles.queue}>{model.groupedUnits.map((unit) => <ClusterCard key={unit.id} unit={unit} expanded={expandedClusters.has(unit.id)} onToggleCluster={() => setExpandedClusters((current) => toggleSet(current, unit.id))} expandedCandidates={expandedCandidates} onToggleCandidate={(id) => setExpandedCandidates((current) => toggleSet(current, id))} />)}</div>
          </section>
        </>}
      </>}
    </> : null}
  </main>;
}
