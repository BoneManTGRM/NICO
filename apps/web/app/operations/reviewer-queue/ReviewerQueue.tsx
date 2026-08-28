"use client";

import {useEffect, useState} from "react";
import type {ChangeEvent, FormEvent, SyntheticEvent} from "react";
import styles from "./reviewer-queue.module.css";

type JsonRecord = Record<string, unknown>;
type Locale = "en" | "es-MX";
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

function tr(locale: Locale, english: string, spanish: string): string {
  return locale === "es-MX" ? spanish : english;
}

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
function addMetricError(errors: string[], value: unknown, actual: number, label: string, locale: Locale): void {
  const expected = finiteNumber(value);
  if (expected === null || expected !== actual) errors.push(tr(
    locale,
    `${label} does not reconcile with the canonical cluster workload.`,
    `${label} no coincide con la carga de trabajo canónica de los grupos.`,
  ));
}

function buildQueue(payload: ReviewQueuePayload, locale: Locale): QueueModel {
  const register = canonicalRegister(payload);
  if (!Array.isArray(register.findings)) throw new Error(tr(locale, "The exact terminal report does not contain a canonical scanner candidate register.", "El informe terminal exacto no contiene un registro canónico de candidatos de los analizadores."));
  const findings = asRecords(register.findings);
  const triage = asRecord(register.technical_triage);
  const integrityErrors: string[] = [];
  const rawClusters = register.review_workload_clusters;
  if (!Array.isArray(rawClusters)) integrityErrors.push(tr(locale, "Canonical deterministic cluster metadata is unavailable.", "Los metadatos canónicos de los grupos deterministas no están disponibles."));
  const clusterRecords = asRecords(rawClusters);
  if (Array.isArray(rawClusters) && clusterRecords.length !== rawClusters.length) integrityErrors.push(tr(locale, "Canonical cluster metadata contains a malformed record.", "Los metadatos canónicos de los grupos contienen un registro con formato incorrecto."));

  const candidateById = new Map<string, JsonRecord>();
  const sourceIds: string[] = [];
  for (const candidate of findings) {
    const id = text(candidate.candidate_id);
    if (!id) {
      integrityErrors.push(tr(locale, "A canonical candidate identity is missing.", "Falta una identidad canónica de candidato."));
      continue;
    }
    sourceIds.push(id);
    if (candidateById.has(id)) integrityErrors.push(tr(locale, `Candidate identity ${id} is duplicated.`, `La identidad de candidato ${id} está duplicada.`));
    candidateById.set(id, candidate);
    const exactCommit = text(candidate.exact_commit_sha);
    if (exactCommit !== text(payload.commit_sha)) integrityErrors.push(tr(locale, `Candidate ${id} does not match the exact run commit.`, `El candidato ${id} no corresponde al commit exacto de la ejecución.`));
    if (candidate.human_review_required !== true || candidate.client_delivery_allowed === true) integrityErrors.push(tr(locale, `Candidate ${id} does not preserve the mandatory pre-approval review boundary.`, `El candidato ${id} no conserva el límite obligatorio de revisión previa a la aprobación.`));
    if (candidate.human_disposition !== null && candidate.human_disposition !== undefined) integrityErrors.push(tr(locale, `Candidate ${id} already contains a human disposition outside this read-only work package.`, `El candidato ${id} ya contiene una disposición humana fuera de este paquete de trabajo de solo lectura.`));
  }

  const observedClusterIds = new Set<string>();
  const clusteredCandidateIds: string[] = [];
  const builtUnits: QueueUnit[] = [];
  clusterRecords.forEach((cluster, index) => {
    const clusterId = text(cluster.cluster_id);
    if (!clusterId) integrityErrors.push(tr(locale, `Cluster record ${index + 1} has no canonical identity.`, `El registro de grupo ${index + 1} no tiene identidad canónica.`));
    if (clusterId && observedClusterIds.has(clusterId)) integrityErrors.push(tr(locale, `Cluster identity ${clusterId} is duplicated.`, `La identidad del grupo ${clusterId} está duplicada.`));
    if (clusterId) observedClusterIds.add(clusterId);

    const candidateIds = textList(cluster.candidate_ids);
    if (!Array.isArray(cluster.candidate_ids)) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} has no canonical candidate list.`, `El grupo ${clusterId || index + 1} no tiene una lista canónica de candidatos.`));
    if (new Set(candidateIds).size !== candidateIds.length) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} repeats a candidate identity.`, `El grupo ${clusterId || index + 1} repite una identidad de candidato.`));
    const declaredCount = finiteNumber(cluster.candidate_record_count);
    const declaredSize = finiteNumber(cluster.cluster_size);
    if (declaredCount !== candidateIds.length || declaredSize !== candidateIds.length) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} size does not match its candidate list.`, `El tamaño del grupo ${clusterId || index + 1} no coincide con su lista de candidatos.`));

    const grouped = cluster.grouped_review_eligible === true;
    const candidates: JsonRecord[] = [];
    for (const id of candidateIds) {
      clusteredCandidateIds.push(id);
      const candidate = candidateById.get(id);
      if (!candidate) {
        integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} references unknown candidate ${id}.`, `El grupo ${clusterId || index + 1} hace referencia al candidato desconocido ${id}.`));
        continue;
      }
      candidates.push(candidate);
      if (text(candidate.cluster_id) !== clusterId) integrityErrors.push(tr(locale, `Candidate ${id} does not match cluster ${clusterId}.`, `El candidato ${id} no corresponde al grupo ${clusterId}.`));
      if (finiteNumber(candidate.cluster_size) !== candidateIds.length) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent cluster size.`, `El candidato ${id} tiene un tamaño de grupo inconsistente.`));
      if (!sameList(textList(candidate.cluster_candidate_ids), candidateIds)) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent deterministic cluster membership.`, `El candidato ${id} tiene una pertenencia inconsistente al grupo determinista.`));
      if (text(candidate.representative_candidate_id) !== text(cluster.representative_candidate_id)) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent representative identity.`, `El candidato ${id} tiene una identidad representativa inconsistente.`));
      if (candidate.grouped_review_eligible !== cluster.grouped_review_eligible) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent grouped-review eligibility.`, `El candidato ${id} tiene una elegibilidad inconsistente para revisión agrupada.`));
      if (candidate.homogeneous_evidence !== cluster.homogeneous_evidence || candidate.homogeneous_verdict !== cluster.homogeneous_verdict) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent cluster homogeneity metadata.`, `El candidato ${id} tiene metadatos inconsistentes de homogeneidad del grupo.`));
      const expectedReviewUnit = grouped ? clusterId : id;
      if (text(candidate.review_unit_id) !== expectedReviewUnit) integrityErrors.push(tr(locale, `Candidate ${id} has inconsistent deterministic review-unit identity.`, `El candidato ${id} tiene una identidad inconsistente de unidad de revisión determinista.`));
    }

    const routingClasses = Array.from(new Set(candidates.map((candidate) => text(candidate.review_routing_class)).filter(Boolean))).sort();
    const declaredRoutingClasses = textList(cluster.review_routing_classes).sort();
    if (!sameList(routingClasses, declaredRoutingClasses)) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} has inconsistent review-routing classes.`, `El grupo ${clusterId || index + 1} tiene clases inconsistentes de enrutamiento de revisión.`));
    if (!text(cluster.cluster_reason) || !text(cluster.homogeneous_evidence_basis)) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} is missing its deterministic grouping basis.`, `Al grupo ${clusterId || index + 1} le falta su fundamento de agrupación determinista.`));

    const representativeId = text(cluster.representative_candidate_id);
    const representative = candidates.find((candidate) => candidateId(candidate) === representativeId);
    if (!representative || !candidateIds.includes(representativeId)) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} has an invalid representative candidate.`, `El grupo ${clusterId || index + 1} tiene un candidato representativo no válido.`));
    if (grouped) {
      if (cluster.grouped_human_review_cluster !== true || candidateIds.length < 2) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} is not a valid grouped human-review unit.`, `El grupo ${clusterId || index + 1} no es una unidad válida de revisión humana agrupada.`));
      if (cluster.homogeneous_evidence !== true || cluster.homogeneous_verdict !== true) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} is not homogeneous enough for grouped review.`, `El grupo ${clusterId || index + 1} no es suficientemente homogéneo para la revisión agrupada.`));
      if (candidates.some((candidate) => candidate.grouped_review_eligible !== true || candidate.review_requires_individual_attention === true)) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} contains a candidate that requires individual attention.`, `El grupo ${clusterId || index + 1} contiene un candidato que requiere atención individual.`));
    } else {
      if (cluster.grouped_human_review_cluster === true || candidateIds.length !== 1) integrityErrors.push(tr(locale, `Individual cluster ${clusterId || index + 1} does not contain exactly one candidate.`, `El grupo individual ${clusterId || index + 1} no contiene exactamente un candidato.`));
      if (candidates.some((candidate) => candidate.grouped_review_eligible === true || candidate.review_requires_individual_attention !== true)) integrityErrors.push(tr(locale, `Individual cluster ${clusterId || index + 1} has inconsistent routing.`, `El grupo individual ${clusterId || index + 1} tiene un enrutamiento inconsistente.`));
    }
    if (cluster.underlying_candidate_disposition_required !== true) integrityErrors.push(tr(locale, `Cluster ${clusterId || index + 1} does not preserve candidate-level human disposition requirements.`, `El grupo ${clusterId || index + 1} no conserva los requisitos de disposición humana a nivel de candidato.`));

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
  if (new Set(sourceIds).size !== sourceIds.length) integrityErrors.push(tr(locale, "Candidate identities are not unique.", "Las identidades de los candidatos no son únicas."));
  if (queuedIds.length !== findings.length || new Set(queuedIds).size !== findings.length || sourceIds.some((id) => !queuedIds.includes(id))) integrityErrors.push(tr(locale, "Deterministic clusters do not preserve every canonical candidate exactly once.", "Los grupos deterministas no conservan cada candidato canónico exactamente una vez."));

  const individualUnits = builtUnits.filter((unit) => unit.kind === "individual").sort((left, right) => compareCandidates(left.representative, right.representative));
  const groupedUnits = builtUnits.filter((unit) => unit.kind === "group").sort((left, right) => compareCandidates(left.representative, right.representative) || left.id.localeCompare(right.id));
  const units = [...individualUnits, ...groupedUnits];
  const groupedCandidateCount = groupedUnits.reduce((total, unit) => total + unit.candidates.length, 0);
  const individualCandidateCount = individualUnits.reduce((total, unit) => total + unit.candidates.length, 0);
  const declaredCandidateCount = finiteNumber(register.candidate_record_count);
  const candidateCount = declaredCandidateCount ?? findings.length;

  if (candidateCount !== findings.length) integrityErrors.push(tr(locale, "Candidate count does not match the canonical register.", "El número de candidatos no coincide con el registro canónico."));
  addMetricError(integrityErrors, triage.total_candidates, findings.length, tr(locale, "Total candidate count", "El número total de candidatos"), locale);
  addMetricError(integrityErrors, triage.cluster_count, clusterRecords.length, tr(locale, "Cluster count", "El número de grupos"), locale);
  addMetricError(integrityErrors, triage.grouped_review_cluster_count, groupedUnits.length, tr(locale, "Grouped cluster count", "El número de grupos agrupados"), locale);
  addMetricError(integrityErrors, triage.candidates_eligible_for_grouped_review, groupedCandidateCount, tr(locale, "Grouped candidate count", "El número de candidatos agrupados"), locale);
  addMetricError(integrityErrors, triage.grouped_human_review_candidate_count, groupedCandidateCount, tr(locale, "Grouped human-review candidate count", "El número de candidatos para revisión humana agrupada"), locale);
  addMetricError(integrityErrors, triage.candidates_requiring_individual_human_attention, individualCandidateCount, tr(locale, "Individual-attention candidate count", "El número de candidatos que requieren atención individual"), locale);
  addMetricError(integrityErrors, triage.individual_human_review_record_count, individualCandidateCount, tr(locale, "Individual review record count", "El número de registros de revisión individual"), locale);
  const expectedWorkUnits = finiteNumber(triage.human_review_work_units);
  if (expectedWorkUnits === null || expectedWorkUnits !== units.length) integrityErrors.push(tr(locale, "Human-review work-unit count does not reconcile with the canonical cluster workload.", "El número de unidades de trabajo de revisión humana no coincide con la carga canónica de los grupos."));
  if (!Array.isArray(triage.review_workload_clusters) || JSON.stringify(triage.review_workload_clusters) !== JSON.stringify(rawClusters)) integrityErrors.push(tr(locale, "Top-level and technical-triage cluster records are not identical.", "Los registros de grupos del nivel superior y del triaje técnico no son idénticos."));
  if (finiteNumber(payload.candidate_count) !== candidateCount) integrityErrors.push(tr(locale, "Protected queue candidate count does not match the canonical register.", "El número de candidatos de la cola protegida no coincide con el registro canónico."));
  if (finiteNumber(payload.human_review_work_units) !== units.length) integrityErrors.push(tr(locale, "Protected queue work-unit count does not reconcile with the displayed queue.", "El número de unidades de trabajo de la cola protegida no coincide con la cola mostrada."));

  return {units, individualUnits, groupedUnits, candidateCount, clusterCount: clusterRecords.length, integrityErrors: Array.from(new Set(integrityErrors))};
}

function evidenceLabel(candidate: JsonRecord, locale: Locale): string {
  return text(candidate.source_path) || text(candidate.path) || text(candidate.manifest_path) || text(candidate.advisory) || text(candidate.rule) || text(candidate.rule_id) || tr(locale, "Evidence location retained in the canonical register", "Ubicación de evidencia conservada en el registro canónico");
}
function CandidateSummary({candidate, locale}: {candidate: JsonRecord; locale: Locale}) {
  const proofGaps = textList(candidate.technical_triage_proof_gaps || candidate.proof_gaps);
  return <>
    <div className={styles.candidateHeader}>
      <code>{candidateId(candidate)}</code>
      <span>{text(candidate.category) || tr(locale, "uncategorized", "sin categoría")}</span>
      <span>{text(candidate.review_routing_class).replaceAll("_", " ") || tr(locale, "review routing unavailable", "enrutamiento de revisión no disponible")}</span>
    </div>
    <h3>{text(candidate.title) || text(candidate.rule) || text(candidate.advisory) || tr(locale, "Technical review candidate", "Candidato para revisión técnica")}</h3>
    <p className={styles.evidence}>{evidenceLabel(candidate, locale)}</p>
    <dl className={styles.detailGrid}>
      <div><dt>{tr(locale, "Technical proposal", "Propuesta técnica")}</dt><dd>{text(candidate.technical_triage_verdict).replaceAll("_", " ") || tr(locale, "needs review", "requiere revisión")}</dd></div>
      <div><dt>{tr(locale, "Confidence", "Confianza")}</dt><dd>{text(candidate.technical_triage_confidence) || tr(locale, "not stated", "no indicada")}</dd></div>
      <div><dt>{tr(locale, "Scanner", "Analizador")}</dt><dd>{text(candidate.scanner) || text(candidate.tool) || tr(locale, "not stated", "no indicado")}</dd></div>
      <div><dt>{tr(locale, "Lineage", "Linaje")}</dt><dd>{text(candidate.lineage_status).replaceAll("_", " ") || tr(locale, "not stated", "no indicado")}</dd></div>
      <div><dt>{tr(locale, "Rule or advisory", "Regla o aviso")}</dt><dd>{text(candidate.rule) || text(candidate.rule_id) || text(candidate.advisory) || tr(locale, "not stated", "no indicado")}</dd></div>
      <div><dt>{tr(locale, "Package context", "Contexto del paquete")}</dt><dd>{[text(candidate.dependency_package), text(candidate.dependency_version), text(candidate.dependency_ecosystem)].filter(Boolean).join(" · ") || tr(locale, "not applicable", "no aplica")}</dd></div>
      <div><dt>{tr(locale, "Production scope", "Alcance de producción")}</dt><dd>{text(candidate.production_test_development_scope) || text(candidate.production_classification) || tr(locale, "not stated", "no indicado")}</dd></div>
      <div><dt>{tr(locale, "Analysis model", "Modelo de análisis")}</dt><dd>{text(candidate.technical_triage_model_or_version) || text(candidate.technical_triage_source) || tr(locale, "not stated", "no indicado")}</dd></div>
      <div><dt>{tr(locale, "Reachability", "Alcanzabilidad")}</dt><dd>{text(candidate.reachability_assessment) || text(candidate.reachability) || tr(locale, "not established", "no establecida")}</dd></div>
      <div><dt>{tr(locale, "Exploitability", "Explotabilidad")}</dt><dd>{text(candidate.exploitability_assessment) || tr(locale, "not established", "no establecida")}</dd></div>
      <div><dt>{tr(locale, "Environment relevance", "Relevancia para el entorno")}</dt><dd>{text(candidate.environment_relevance) || tr(locale, "not established", "no establecida")}</dd></div>
      <div><dt>{tr(locale, "Boundary assessment", "Evaluación de límites")}</dt><dd>{text(candidate.technical_triage_boundary_assessment) || text(candidate.boundary_assessment) || tr(locale, "not established", "no establecida")}</dd></div>
    </dl>
    <div className={styles.evidenceGrid}>
      <section><h4>{tr(locale, "Evidence used", "Evidencia utilizada")}</h4><pre>{JSON.stringify(candidate.evidence_used ?? candidate.evidence ?? [], null, 2)}</pre></section>
      <section><h4>{tr(locale, "Counterevidence", "Contraevidencia")}</h4><pre>{JSON.stringify(candidate.counterevidence ?? [], null, 2)}</pre></section>
    </div>
    <p>{text(candidate.technical_triage_rationale) || tr(locale, "No automated rationale was retained.", "No se conservó una justificación automatizada.")}</p>
    {proofGaps.length ? <p className={styles.proofGap}><strong>{tr(locale, "Proof gaps:", "Brechas de evidencia:")}</strong> {proofGaps.join(" · ")}</p> : null}
    {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step) ? <p><strong>{tr(locale, "Recommended next step:", "Siguiente paso recomendado:")}</strong> {text(candidate.technical_triage_recommended_next_step || candidate.recommended_next_step)}</p> : null}
  </>;
}

function CandidateDisclosure({candidate, locale, representative = false}: {candidate: JsonRecord; locale: Locale; representative?: boolean}) {
  const [open, setOpen] = useState(false);
  const title = text(candidate.title) || text(candidate.rule) || text(candidate.advisory) || tr(locale, "Technical review candidate", "Candidato para revisión técnica");
  return <details className={styles.candidateDisclosure} data-candidate-id={candidateId(candidate)} onToggle={(event: SyntheticEvent<HTMLDetailsElement>) => setOpen(event.currentTarget.open)}>
    <summary className={styles.candidateSummary}>
      <span className={styles.summaryIdentity}><code>{candidateId(candidate)}</code><strong>{title}</strong></span>
      <span className={styles.summaryMeta}>{representative ? tr(locale, "Representative · ", "Representante · ") : ""}{text(candidate.category) || tr(locale, "uncategorized", "sin categoría")}</span>
      <span className={styles.disclosureState}><span className={styles.closedLabel}>{tr(locale, "Expand candidate", "Expandir candidato")}</span><span className={styles.openLabel}>{tr(locale, "Collapse candidate", "Contraer candidato")}</span></span>
    </summary>
    {open ? <div className={styles.candidateBody}>
      <CandidateSummary candidate={candidate} locale={locale} />
      <section className={styles.canonicalRecord} data-canonical-candidate-record="true" aria-label={tr(locale, `Complete canonical record for ${candidateId(candidate)}`, `Registro canónico completo de ${candidateId(candidate)}`)}>
        <h4>{tr(locale, "Complete retained canonical candidate record", "Registro canónico completo del candidato conservado")}</h4>
        <p>{tr(locale, "All retained evidence, counterevidence, source context, dependency context, scope, reachability, exploitability, proof gaps, lineage, clustering, and technical-triage fields are shown below without creating a human disposition.", "A continuación se muestran toda la evidencia y contraevidencia conservadas, el contexto de origen y dependencias, el alcance, la alcanzabilidad, la explotabilidad, las brechas de evidencia, el linaje, la agrupación y los campos de triaje técnico, sin crear una disposición humana.")}</p>
        <pre>{JSON.stringify(candidate, null, 2)}</pre>
      </section>
    </div> : null}
  </details>;
}

function ClusterDisclosure({unit, locale}: {unit: QueueUnit; locale: Locale}) {
  const [open, setOpen] = useState(false);
  const cluster = unit.cluster;
  return <details className={styles.clusterDisclosure} data-cluster-id={unit.id} onToggle={(event: SyntheticEvent<HTMLDetailsElement>) => setOpen(event.currentTarget.open)}>
    <summary className={styles.clusterSummary}>
      <span className={styles.summaryIdentity}><span>{tr(locale, "Cluster", "Grupo")}</span><code>{unit.id}</code></span>
      <span className={styles.summaryMeta}>{unit.candidates.length} {tr(locale, unit.candidates.length === 1 ? "candidate" : "candidates", unit.candidates.length === 1 ? "candidato" : "candidatos")} · {textList(cluster.review_routing_classes).join(" · ") || tr(locale, "technical review", "revisión técnica")}</span>
      <span className={styles.disclosureState}><span className={styles.closedLabel}>{tr(locale, "Expand cluster", "Expandir grupo")}</span><span className={styles.openLabel}>{tr(locale, "Collapse cluster", "Contraer grupo")}</span></span>
    </summary>
    {open ? <div className={styles.clusterBody}>
      <dl className={styles.clusterGrid}>
        <div><dt>{tr(locale, "Cluster reason", "Motivo del grupo")}</dt><dd>{text(cluster.cluster_reason) || tr(locale, "not stated", "no indicado")}</dd></div>
        <div><dt>{tr(locale, "Representative", "Representante")}</dt><dd><code>{candidateId(unit.representative)}</code></dd></div>
        <div><dt>{tr(locale, "Evidence homogeneity", "Homogeneidad de la evidencia")}</dt><dd>{cluster.homogeneous_evidence === true ? tr(locale, "Verified", "Verificada") : tr(locale, "Not verified", "No verificada")}</dd></div>
        <div><dt>{tr(locale, "Verdict homogeneity", "Homogeneidad del veredicto")}</dt><dd>{cluster.homogeneous_verdict === true ? tr(locale, "Verified", "Verificada") : tr(locale, "Not verified", "No verificada")}</dd></div>
      </dl>
      {text(cluster.homogeneous_evidence_basis) ? <p className={styles.clusterBasis}><strong>{tr(locale, "Homogeneity basis:", "Fundamento de homogeneidad:")}</strong> {text(cluster.homogeneous_evidence_basis)}</p> : null}
      <p className={styles.clusterBoundary}>{tr(locale, "The cluster summary is routing context only. Every underlying candidate remains canonical, independently expandable, and subject to an explicit later human disposition.", "El resumen del grupo sirve únicamente como contexto de enrutamiento. Cada candidato subyacente sigue siendo canónico, se puede expandir de forma independiente y queda sujeto a una disposición humana posterior y explícita.")}</p>
      <div className={styles.clusterCandidates} aria-label={tr(locale, `Underlying candidates in ${unit.id}`, `Candidatos subyacentes en ${unit.id}`)}>
        {unit.candidates.map((candidate) => <CandidateDisclosure key={candidateId(candidate)} candidate={candidate} locale={locale} representative={candidateId(candidate) === candidateId(unit.representative)} />)}
      </div>
    </div> : null}
  </details>;
}

export default function ReviewerQueue() {
  const [locale, setLocale] = useState<Locale>("en");
  const [runId, setRunId] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [payload, setPayload] = useState<ReviewQueuePayload | null>(null);
  const [model, setModel] = useState<QueueModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedLocale: Locale = query.get("lang") === "es-MX" ? "es-MX" : "en";
    setRunId(query.get("run_id") || "");
    setLocale(requestedLocale);
    document.documentElement.lang = requestedLocale;
    document.title = tr(requestedLocale, "Human review workspace | NICO", "Espacio de revisión humana | NICO");
  }, []);

  function switchLocale(): void {
    const nextLocale: Locale = locale === "es-MX" ? "en" : "es-MX";
    const target = new URL(window.location.href);
    target.searchParams.set("lang", nextLocale);
    if (runId.trim()) target.searchParams.set("run_id", runId.trim());
    window.location.assign(`${target.pathname}${target.search}${target.hash}`);
  }

  async function loadQueue(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!runId.trim() || !adminToken.trim()) {
      setError(tr(locale, "Enter the exact Comprehensive run ID and operator admin token.", "Ingresa el ID exacto de la ejecución Comprehensive y el token de administrador."));
      return;
    }
    setLoading(true); setError(""); setPayload(null); setModel(null);
    try {
      const requestedRunId = runId.trim();
      const response = await fetch(new URL(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(requestedRunId)}/review-queue`, window.location.origin), {
        cache: "no-store",
        headers: {Accept: "application/json", "X-NICO-Admin-Token": adminToken.trim()},
      });
      if (!response.ok) throw new Error(tr(locale, `Unable to load the exact protected review queue (${response.status}).`, `No fue posible cargar la cola protegida de revisión exacta (${response.status}).`));
      const next = await response.json() as ReviewQueuePayload;
      if (text(next.run_id) !== requestedRunId || !text(next.repository) || !text(next.commit_sha) || !text(next.evidence_ledger_id)) throw new Error(tr(locale, "The protected reviewer queue did not preserve the exact canonical run identity.", "La cola protegida de revisión no conservó la identidad canónica exacta de la ejecución."));
      if (!next.terminal || text(next.status) !== "review_required") throw new Error(tr(locale, "The exact run must reach the terminal human-review boundary before its reviewer queue can open.", "La ejecución exacta debe llegar al límite terminal de revisión humana antes de abrir su cola de revisión."));
      if (next.read_only !== true) throw new Error(tr(locale, "The protected reviewer queue did not preserve its read-only contract.", "La cola protegida de revisión no conservó su contrato de solo lectura."));
      if (text(next.source) !== "canonical_terminal_comprehensive_report_json") throw new Error(tr(locale, "The reviewer queue is not bound to the terminal canonical Comprehensive report.", "La cola de revisión no está vinculada al informe Comprehensive canónico terminal."));
      if (next.human_review_required !== true || next.client_delivery_allowed === true) throw new Error(tr(locale, "The exact run does not preserve the mandatory pre-approval human-review boundary.", "La ejecución exacta no conserva el límite obligatorio de revisión humana previa a la aprobación."));
      const queue = buildQueue(next, locale);
      setPayload(next); setModel(queue);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : tr(locale, "Unable to load the exact review queue.", "No fue posible cargar la cola de revisión exacta."));
    } finally {
      setAdminToken("");
      setLoading(false);
    }
  }

  return <main className={styles.shell} data-review-queue-contract="exception-first-v1" data-expandable-clusters-contract="canonical-read-only-v1" data-human-disposition-controls="absent" data-client-delivery-authorization="absent">
    <section className={styles.hero}>
      <div className={styles.sectionHeading}>
        <p className={styles.eyebrow}>{tr(locale, "NICO PHASE 2 · WORK PACKAGE 2", "NICO FASE 2 · PAQUETE DE TRABAJO 2")}</p>
        <button type="button" className={styles.language} onClick={switchLocale} aria-label={tr(locale, "Switch review workspace to Mexican Spanish", "Cambiar el espacio de revisión a inglés")}>{locale === "es-MX" ? "English" : "Español (México)"}</button>
      </div>
      <h1>{tr(locale, "Expandable deterministic review clusters", "Grupos deterministas de revisión expandibles")}</h1>
      <p>{tr(locale, "Review individual exceptions first, then expand deterministic clusters and every underlying candidate without leaving the same immutable NICO Comprehensive run.", "Revisa primero las excepciones individuales; después, expande los grupos deterministas y cada candidato subyacente sin salir de la misma ejecución inmutable de NICO Comprehensive.")}</p>
      <div className={styles.boundary}>{tr(locale, "Authenticated, read-only technical review routing. Cluster summaries never replace candidate evidence. No candidate disposition, reviewer identity, risk acceptance, approval, score change, or client-delivery authorization is created here.", "Enrutamiento autenticado y de solo lectura para revisión técnica. Los resúmenes de los grupos nunca sustituyen la evidencia de los candidatos. Aquí no se crea ninguna disposición de candidato, identidad de revisor, aceptación de riesgo, aprobación, cambio de puntuación ni autorización de entrega al cliente.")}</div>
    </section>
    <section className={styles.panel}>
      <h2>{tr(locale, "Open an exact terminal run", "Abrir una ejecución terminal exacta")}</h2>
      <form className={styles.form} onSubmit={loadQueue}>
        <label>{tr(locale, "Exact Comprehensive run ID", "ID exacto de la ejecución Comprehensive")}<input value={runId} onChange={(event: ChangeEvent<HTMLInputElement>) => setRunId(event.target.value)} placeholder="comprun_…" autoCapitalize="none" autoCorrect="off" spellCheck={false} /></label>
        <label>{tr(locale, "Operator admin token", "Token de administrador")}<input type="password" value={adminToken} onChange={(event: ChangeEvent<HTMLInputElement>) => setAdminToken(event.target.value)} autoComplete="off" spellCheck={false} /></label>
        <button type="submit" disabled={loading || !runId.trim() || !adminToken.trim()}>{loading ? tr(locale, "Loading exact queue…", "Cargando la cola exacta…") : tr(locale, "Load reviewer queue", "Cargar cola de revisión")}</button>
      </form>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
    </section>
    {payload && model ? <>
      <section className={styles.identity} aria-label={tr(locale, "Exact run identity", "Identidad exacta de la ejecución")}>
        <div><span>{tr(locale, "Run", "Ejecución")}</span><strong>{payload.run_id || runId}</strong></div><div><span>Commit</span><strong>{payload.commit_sha}</strong></div>
        <div><span>{tr(locale, "Review", "Revisión")}</span><strong>{tr(locale, "Human required", "Revisión humana requerida")}</strong></div><div><span>{tr(locale, "Client delivery", "Entrega al cliente")}</span><strong>{payload.client_delivery_allowed === true ? tr(locale, "Authorized elsewhere", "Autorizada en otro proceso") : tr(locale, "Blocked", "Bloqueada")}</strong></div>
      </section>
      <section className={styles.metrics} aria-label={tr(locale, "Canonical review workload", "Carga de trabajo canónica de revisión")}>
        <article><span>{tr(locale, "Canonical candidates", "Candidatos canónicos")}</span><strong>{model.candidateCount}</strong></article><article><span>{tr(locale, "Deterministic clusters", "Grupos deterministas")}</span><strong>{model.clusterCount}</strong></article>
        <article><span>{tr(locale, "Individual work units", "Unidades de trabajo individuales")}</span><strong>{model.individualUnits.length}</strong></article><article><span>{tr(locale, "Grouped work units", "Unidades de trabajo agrupadas")}</span><strong>{model.groupedUnits.length}</strong></article><article><span>{tr(locale, "Total work units", "Unidades de trabajo totales")}</span><strong>{model.units.length}</strong></article>
      </section>
      {model.integrityErrors.length ? <section className={styles.integrityError} role="alert"><strong>{tr(locale, "Queue integrity check failed closed.", "La verificación de integridad de la cola falló de forma cerrada.")}</strong><p>{tr(locale, "No candidate or cluster content is displayed until exact candidate, cluster, identity, and workload parity is restored.", "No se muestra contenido de candidatos ni grupos hasta restablecer la paridad exacta de candidatos, grupos, identidad y carga de trabajo.")}</p><ul>{model.integrityErrors.map((item) => <li key={item}>{item}</li>)}</ul></section> : <>
        <section className={styles.integrityOk}><strong>{tr(locale, "Canonical parity verified.", "Paridad canónica verificada.")}</strong> {tr(locale, "Every retained candidate appears exactly once, deterministic cluster membership matches the canonical register, and the work-unit total reconciles with the report.", "Cada candidato conservado aparece exactamente una vez, la pertenencia a grupos deterministas coincide con el registro canónico y el total de unidades de trabajo coincide con el informe.")}</section>
        <section className={styles.queueSection}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{tr(locale, "FIRST", "PRIMERO")}</p><h2>{tr(locale, "Individual attention", "Atención individual")}</h2></div><strong>{model.individualUnits.length} {tr(locale, model.individualUnits.length === 1 ? "work unit" : "work units", model.individualUnits.length === 1 ? "unidad de trabajo" : "unidades de trabajo")}</strong></div>
          <p className={styles.sectionLead}>{tr(locale, "Each candidate expands into its complete retained canonical evidence and technical-triage record.", "Cada candidato se expande para mostrar su evidencia canónica completa conservada y su registro de triaje técnico.")}</p>
          <div className={styles.queue}>{model.individualUnits.map((unit) => <CandidateDisclosure key={unit.id} candidate={unit.representative} locale={locale} />)}</div>
        </section>
        <section className={styles.queueSection}>
          <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{tr(locale, "THEN", "DESPUÉS")}</p><h2>{tr(locale, "Deterministic grouped work units", "Unidades de trabajo deterministas agrupadas")}</h2></div><strong>{model.groupedUnits.length} {tr(locale, model.groupedUnits.length === 1 ? "work unit" : "work units", model.groupedUnits.length === 1 ? "unidad de trabajo" : "unidades de trabajo")}</strong></div>
          <p className={styles.sectionLead}>{tr(locale, "Expand a cluster to inspect its deterministic basis and then expand every underlying candidate. Groups are presentation-only and never replace candidate identities, evidence, or later human dispositions.", "Expande un grupo para inspeccionar su fundamento determinista y luego expande cada candidato subyacente. Los grupos solo sirven para presentación y nunca sustituyen las identidades, la evidencia ni las disposiciones humanas posteriores de los candidatos.")}</p>
          <div className={styles.queue}>{model.groupedUnits.map((unit) => <ClusterDisclosure key={unit.id} unit={unit} locale={locale} />)}</div>
        </section>
      </>}
    </> : null}
  </main>;
}
