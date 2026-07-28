"use client";

import {useState} from "react";
import styles from "./midReview.module.css";

type JsonRecord = Record<string, unknown>;
type Filter = "all" | "attention" | "verified";
type Tone = "critical" | "warning" | "healthy" | "neutral";

type Section = {
  id?: unknown;
  label?: unknown;
  score?: unknown;
  status?: unknown;
  truth_status?: unknown;
  summary?: unknown;
  evidence?: unknown;
  findings?: unknown;
  unavailable?: unknown;
  missing_evidence_sources?: unknown;
  failed_evidence_tools?: unknown;
  scope_disclosures?: unknown;
  confidence?: unknown;
  source_classification?: unknown;
  direct_repository_proof?: unknown;
};

type WeightedRow = {
  section_id: string;
  label: string;
  score: number;
  weight: number;
  weighted_points: number;
  projected_lift_if_verified: number;
};

type Props = {payload: JsonRecord};

const WEIGHTS: Record<string, number> = {
  code_audit: 20,
  dependency_health: 15,
  secrets_review: 10,
  static_analysis: 15,
  ci_cd: 15,
  architecture_debt: 15,
  velocity_complexity: 10,
};

const TECHNICAL_IDS = Object.keys(WEIGHTS);
const REPORT_READY_STATUSES = new Set(["available", "complete", "completed", "generated", "ready"]);
const REVIEW_APPROVED_STATUSES = new Set(["accepted", "approved", "complete", "completed"]);
const REVIEW_BLOCKED_STATUSES = new Set(["blocked", "declined", "failed", "rejected"]);

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function finite(value: unknown): number | null {
  if (value == null || typeof value === "boolean") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function bounded(value: unknown, minimum = 0, maximum = 100): number | null {
  const parsed = finite(value);
  return parsed == null ? null : Math.max(minimum, Math.min(maximum, parsed));
}

function normalizedStatus(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function titleCase(value: unknown): string {
  const text = String(value || "pending").replaceAll("_", " ").replaceAll("-", " ").trim();
  return text ? text.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Pending";
}

function cleanText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value).replace(/\s+/g, " ").trim();
  if (isRecord(value)) return cleanText(value.summary ?? value.message ?? value.title ?? value.reason ?? value.name ?? value.label);
  return "";
}

function displayText(value: unknown, fallback: string): string {
  return cleanText(value) || fallback;
}

function unique(items: unknown[]): string[] {
  const seen = new Set<string>();
  return items.flatMap((item) => {
    const value = cleanText(item);
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return [];
    seen.add(key);
    return [value];
  });
}

function textItems(value: unknown): string[] {
  return unique(Array.isArray(value) ? value : []);
}

function readableToolGap(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "bandit") return "Bandit did not provide accepted exact-snapshot evidence for this run.";
  if (normalized === "gitleaks") return "Gitleaks did not provide accepted evidence for this exact snapshot; history coverage is stated separately.";
  if (/^[a-z0-9_.-]{2,30}$/.test(normalized)) return `${titleCase(normalized)} evidence is incomplete or unavailable for this run.`;
  return value;
}

function limitations(section: Section): string[] {
  return unique([
    ...textItems(section.unavailable),
    ...textItems(section.missing_evidence_sources),
    ...textItems(section.failed_evidence_tools).map(readableToolGap),
  ]).map(readableToolGap);
}

function sectionId(section: Section): string {
  return cleanText(section.id);
}

function sectionLabel(section: Section): string {
  const id = sectionId(section);
  return displayText(section.label, id ? titleCase(id) : "Assessment section");
}

function isUnscored(section: Section): boolean {
  const truth = normalizedStatus(section.truth_status || section.status);
  return finite(section.score) == null || truth.includes("gray") || truth.includes("unavailable") || truth.includes("not_scored");
}

function tone(section: Section): Tone {
  if (isUnscored(section)) return "neutral";
  const status = normalizedStatus(section.truth_status || section.status);
  const score = bounded(section.score);
  if (["red", "failed", "error", "blocked"].some((token) => status.includes(token)) || (score != null && score < 60)) return "critical";
  if ((score != null && score < 80) || textItems(section.findings).length > 0 || limitations(section).length > 0) return "warning";
  return score != null && score >= 80 ? "healthy" : "warning";
}

function scoreLabel(section: Section): string {
  const score = bounded(section.score);
  return score == null ? "—" : `${Math.round(score)}/100`;
}

function weightedRows(payload: JsonRecord, sections: Section[]): WeightedRow[] {
  const intelligence = isRecord(payload.mid_score_intelligence) ? payload.mid_score_intelligence : {};
  const suppliedById = new Map<string, JsonRecord>();
  for (const row of records(intelligence.weighted_sections)) {
    const id = cleanText(row.section_id);
    if (TECHNICAL_IDS.includes(id) && !suppliedById.has(id)) suppliedById.set(id, row);
  }
  const sectionById = new Map(sections.map((section) => [sectionId(section), section]));
  return TECHNICAL_IDS.flatMap((id) => {
    const supplied = suppliedById.get(id);
    const section = sectionById.get(id);
    const score = bounded(supplied?.score ?? section?.score);
    if (score == null) return [];
    const weight = WEIGHTS[id];
    const weightedPoints = score * weight / 100;
    return [{
      section_id: id,
      label: displayText(supplied?.label ?? section?.label, titleCase(id)),
      score,
      weight,
      weighted_points: Math.round(weightedPoints * 100) / 100,
      projected_lift_if_verified: Math.round(Math.max(0, 80 - score) * weight) / 100,
    }];
  });
}

function explicitTrue(value: unknown): boolean {
  if (value === true || value === 1) return true;
  if (typeof value !== "string") return false;
  return new Set(["1", "available", "complete", "completed", "generated", "ready", "true", "yes"]).has(normalizedStatus(value));
}

function hasArtifact(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  if (value instanceof Uint8Array) return value.byteLength > 0;
  if (value instanceof ArrayBuffer) return value.byteLength > 0;
  if (typeof Blob !== "undefined" && value instanceof Blob) return value.size > 0;
  if (!isRecord(value)) return false;
  return ["base64", "data", "content", "bytes"].some((key) => hasArtifact(value[key]));
}

function clickLegacyAction(labels: string[]): boolean {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>('[data-nico-mid-legacy-hidden="true"] button, [data-nico-mid-legacy-hidden="true"] a'));
  const match = candidates.find((candidate) => {
    if (candidate instanceof HTMLButtonElement && candidate.disabled) return false;
    const text = String(candidate.textContent || "").toLowerCase();
    return labels.some((label) => text.includes(label));
  });
  if (!match) return false;
  match.click();
  return true;
}

function DetailList({items, empty}: {items: string[]; empty: string}) {
  if (!items.length) return <p className={styles.empty}>{empty}</p>;
  return <ul className={styles.detailList}>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

function ControlRow({section, expanded, onToggle}: {section: Section; expanded: boolean; onToggle: () => void}) {
  const sectionTone = tone(section);
  const evidence = textItems(section.evidence);
  const findings = textItems(section.findings);
  const gaps = limitations(section);
  const scope = unique([
    ...textItems(section.scope_disclosures),
    cleanText(section.confidence) ? `Confidence: ${cleanText(section.confidence)}` : undefined,
    cleanText(section.source_classification) ? `Source classification: ${cleanText(section.source_classification)}` : undefined,
    typeof section.direct_repository_proof === "boolean" ? `Direct repository proof: ${section.direct_repository_proof ? "yes" : "no"}` : undefined,
  ]);
  const nextAction = findings[0] || gaps[0] || "Retain the evidence and reviewer disposition for this exact snapshot.";
  const label = sectionLabel(section);
  const truth = titleCase(displayText(section.truth_status || section.status, "Evidence bound"));
  const summary = displayText(section.summary, "No evidence-bound summary was returned.");
  return <article className={`${styles.controlRow} ${styles[sectionTone]}`} data-mid-section={sectionId(section) || label}>
    <button type="button" className={styles.controlToggle} aria-expanded={expanded} onClick={onToggle}>
      <span className={styles.controlIdentity}><b>{label}</b><small>{truth}</small></span>
      <span className={styles.controlCounts}>{findings.length} findings · {gaps.length} gaps</span>
      <strong>{scoreLabel(section)}</strong>
      <span className={styles.chevron} aria-hidden="true">{expanded ? "−" : "+"}</span>
    </button>
    <p className={styles.controlSummary}>{summary}</p>
    {sectionTone !== "healthy" ? <p className={styles.nextAction}><b>Next:</b> {nextAction}</p> : null}
    {expanded ? <div className={styles.detailGrid}>
      <section><h4>Evidence <span>{evidence.length}</span></h4><DetailList items={evidence} empty="No direct evidence item was retained." /></section>
      <section><h4>Findings <span>{findings.length}</span></h4><DetailList items={findings} empty="No specific repair finding was retained." /></section>
      <section><h4>Limitations <span>{gaps.length}</span></h4><DetailList items={gaps} empty="No section-specific limitation was retained." /></section>
      <section><h4>Scope <span>{scope.length}</span></h4><DetailList items={scope} empty="Report-wide human-review boundaries apply." /></section>
    </div> : null}
  </article>;
}

function deriveSections(payload: JsonRecord) {
  const assessment = isRecord(payload.assessment) ? payload.assessment : {};
  const sections = records(assessment.sections) as Section[];
  const technical = TECHNICAL_IDS.flatMap((id) => {
    const match = sections.find((section) => sectionId(section) === id);
    return match ? [match] : [];
  });
  return {assessment, technical, context: sections.filter((section) => !TECHNICAL_IDS.includes(sectionId(section)))};
}

function deriveScores(payload: JsonRecord, assessment: JsonRecord, technical: Section[]) {
  const rows = weightedRows(payload, technical);
  const completeScorecard = rows.length === TECHNICAL_IDS.length && rows.reduce((total, row) => total + row.weight, 0) === 100;
  const weightedScore = completeScorecard ? Math.round(rows.reduce((total, row) => total + row.score * row.weight / 100, 0)) : null;
  const intelligence = isRecord(payload.mid_score_intelligence) ? payload.mid_score_intelligence : {};
  const scoreContract = isRecord(intelligence.score_contract) ? intelligence.score_contract : {};
  const maturity = isRecord(assessment.maturity_signal) ? assessment.maturity_signal : {};
  const score = bounded(weightedScore ?? finite(scoreContract.final_report_score) ?? finite(scoreContract.reported_score) ?? finite(scoreContract.calculated_score) ?? finite(maturity.score) ?? finite(payload.technical_score));
  const lift = rows.reduce((total, row) => total + row.projected_lift_if_verified, 0);
  return {rows, completeScorecard, intelligence, scoreContract, maturity, score, projected: score == null || !completeScorecard ? null : Math.max(0, Math.min(100, Math.round(score + lift)))};
}

function deriveEvidence(payload: JsonRecord, assessment: JsonRecord, technical: Section[]) {
  const coverage = isRecord(assessment.evidence_coverage) ? assessment.evidence_coverage : isRecord(payload.evidence_coverage) ? payload.evidence_coverage : {};
  return {
    readiness: bounded(finite(payload.evidence_readiness) ?? finite(assessment.evidence_readiness) ?? finite(assessment.evidence_readiness_score) ?? finite(payload.evidence_readiness_score)),
    coveragePercent: bounded(coverage.percent),
    evidenceUnits: technical.reduce((total, section) => total + textItems(section.evidence).length, 0),
  };
}

function deriveArtifacts(payload: JsonRecord, intelligence: JsonRecord) {
  const lifecycle = isRecord(intelligence.report_lifecycle) ? intelligence.report_lifecycle : {};
  const reports = isRecord(payload.reports) ? payload.reports : {};
  const pdfReady = (explicitTrue(lifecycle.pdf_available) && (hasArtifact(reports.pdf_base64) || hasArtifact(reports.pdf))) || hasArtifact(reports.pdf_base64) || hasArtifact(reports.pdf);
  const markdownReady = (explicitTrue(lifecycle.markdown_available) && hasArtifact(reports.markdown)) || hasArtifact(reports.markdown);
  const rawStatus = displayText(lifecycle.draft_generation_status || payload.report_generation_status, "pending");
  const claimsReady = REPORT_READY_STATUSES.has(normalizedStatus(rawStatus));
  return {
    lifecycle,
    pdfReady,
    markdownReady,
    reportLabel: pdfReady || markdownReady ? "Ready" : claimsReady ? "Artifact unavailable" : titleCase(rawStatus),
    reportDetail: pdfReady ? "PDF available" : markdownReady ? "Markdown available" : claimsReady ? "Refresh or regenerate the artifact" : "Artifact pending",
  };
}

function deriveReview(payload: JsonRecord, lifecycle: JsonRecord) {
  const approval = isRecord(payload.approval_request) ? payload.approval_request : {};
  const status = normalizedStatus(displayText(lifecycle.human_review_status || approval.status || payload.approval_request_status, "pending"));
  const reviewApproved = REVIEW_APPROVED_STATUSES.has(status);
  const reviewBlocked = REVIEW_BLOCKED_STATUSES.has(status);
  return {reviewApproved, reviewBlocked, reviewLabel: reviewApproved ? "Approved" : reviewBlocked ? "Blocked" : "Required"};
}

function derivePriority(technical: Section[]) {
  const priority = technical
    .filter((section) => !isUnscored(section) && ((bounded(section.score) ?? 101) < 80 || textItems(section.findings).length > 0 || limitations(section).length > 0))
    .sort((left, right) => (bounded(left.score) ?? 101) - (bounded(right.score) ?? 101))
    .slice(0, 3);
  return {priority, attentionCount: technical.filter((section) => tone(section) !== "healthy").length};
}

function buildView(payload: JsonRecord) {
  const sectionView = deriveSections(payload);
  const scores = deriveScores(payload, sectionView.assessment, sectionView.technical);
  const evidence = deriveEvidence(payload, sectionView.assessment, sectionView.technical);
  const artifacts = deriveArtifacts(payload, scores.intelligence);
  const review = deriveReview(payload, artifacts.lifecycle);
  const priority = derivePriority(sectionView.technical);
  return {
    ...sectionView,
    ...scores,
    ...evidence,
    ...artifacts,
    ...review,
    ...priority,
    maturityLabel: displayText(scores.maturity.level || sectionView.assessment.maturity, "Assessment"),
    repository: displayText(payload.repository || sectionView.assessment.repository, "Repository assessment"),
    runId: cleanText(payload.run_id || sectionView.assessment.run_id),
    methodologyNote: displayText(scores.scoreContract.score_methodology_note, "Technical score and evidence readiness are independent measures. This view uses an immutable snapshot, retained scanner evidence, and seven fixed technical weights."),
  };
}

export default function MidSectionReview({payload}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [actionNotice, setActionNotice] = useState("");
  const view = buildView(payload);
  const visible = view.technical.filter((section) => filter === "all" || (filter === "attention" ? tone(section) !== "healthy" : tone(section) === "healthy"));

  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function openPriority(section: Section) {
    const key = sectionId(section) || sectionLabel(section);
    setExpanded((current) => new Set(current).add(key));
    document.querySelector<HTMLElement>(`[data-mid-section="${CSS.escape(key)}"]`)?.scrollIntoView({behavior: "smooth", block: "center"});
  }

  function requestReview() {
    const clicked = clickLegacyAction(["request approval", "submit for approval", "send for review", "request review"]);
    setActionNotice(clicked ? "Review request opened." : "The review request becomes available when the exact report package is ready.");
  }

  function openReport() {
    const clicked = clickLegacyAction(["open report", "download pdf", "download report", "view report"]);
    setActionNotice(clicked ? "Report action opened." : "The report artifact is not available yet.");
  }

  return <section className={styles.workspace} data-nico-mid-review="true" aria-label="Comprehensive assessment review">
    <header className={styles.header}>
      <div><span className={styles.eyebrow}>COMPREHENSIVE ASSESSMENT</span><h2>Engineering decision review</h2><p>{view.repository}{view.runId ? ` · ${view.runId}` : ""}</p></div>
      <div className={styles.headerActions}>
        <button type="button" className={styles.secondaryAction} onClick={requestReview} disabled={view.reviewApproved}>{view.reviewApproved ? "Review approved" : "Request review"}</button>
        <button type="button" className={styles.primaryAction} onClick={openReport} disabled={!view.pdfReady && !view.markdownReady}>Open report</button>
      </div>
    </header>
    {actionNotice ? <p className={styles.actionNotice} role="status">{actionNotice}</p> : null}

    <div className={styles.summaryGrid}>
      <article><span>Technical score</span><strong>{view.score == null ? "—" : `${Math.round(view.score)}/100`}</strong><small>{view.completeScorecard ? "Seven-control weighted score" : "Complete scorecard pending"}</small></article>
      <article><span>Evidence readiness</span><strong>{view.readiness == null ? "—" : `${Math.round(view.readiness)}%`}</strong><small>{view.coveragePercent == null ? `${view.evidenceUnits} retained evidence items` : `${Math.round(view.coveragePercent)}% repository evidence coverage`}</small></article>
      <article><span>Report package</span><strong>{view.reportLabel}</strong><small>{view.reportDetail}</small></article>
      <article><span>Human review</span><strong>{view.reviewLabel}</strong><small>{view.reviewApproved ? "Exact package accepted" : view.reviewBlocked ? "Reviewer action required" : "Mandatory before delivery"}</small></article>
    </div>

    <p className={styles.scoreNote}>{view.methodologyNote}</p>

    {view.priority.length ? <section className={styles.priorityPanel}><div><span className={styles.eyebrow}>PRIORITY</span><h3>What should change first</h3></div><div className={styles.priorityGrid}>{view.priority.map((section) => <button type="button" key={sectionId(section)} onClick={() => openPriority(section)}><span>{sectionLabel(section)}</span><strong>{scoreLabel(section)}</strong><small>{textItems(section.findings)[0] || limitations(section)[0] || "Evidence disposition required"}</small></button>)}</div></section> : null}

    <section className={styles.controlsPanel}>
      <div className={styles.controlsHeader}><div><span className={styles.eyebrow}>TECHNICAL CONTROLS</span><h3>Seven-control scorecard</h3><p>{view.attentionCount} of {view.technical.length} controls need attention.</p></div><div className={styles.filterGroup} role="group" aria-label="Filter technical controls">{(["all", "attention", "verified"] as Filter[]).map((item) => <button type="button" key={item} aria-pressed={filter === item} className={filter === item ? styles.activeFilter : ""} onClick={() => setFilter(item)}>{titleCase(item)}</button>)}</div></div>
      <div className={styles.controlList}>{visible.map((section) => {const key = sectionId(section) || sectionLabel(section); return <ControlRow key={key} section={section} expanded={expanded.has(key)} onToggle={() => toggle(key)} />;})}</div>
    </section>

    <section className={styles.scorePanel}>
      <div><span className={styles.eyebrow}>WEIGHTED SCORE</span><h3>How the score is calculated</h3></div>
      <div className={styles.scoreTable} role="table"><div className={styles.scoreTableHeader} role="row"><span>Control</span><span>Weight</span><span>Score</span><span>Points</span></div>{view.rows.map((row) => <div role="row" key={row.section_id}><span>{row.label}</span><span>{row.weight}%</span><span>{Math.round(row.score)}</span><span>{row.weighted_points.toFixed(2)}</span></div>)}</div>
      <div className={styles.scoreFooter}><p><b>Current:</b> {view.score == null ? "Not scored" : `${Math.round(view.score)}/100`}</p><p><b>Projected after verified remediation:</b> {view.projected == null ? "Requires complete weighted evidence" : `${view.projected}/100`}</p></div>
    </section>

    {view.context.length ? <section className={styles.contextPanel}><div><span className={styles.eyebrow}>CONTEXT</span><h3>Additional evidence and scope</h3></div><div className={styles.contextGrid}>{view.context.map((section) => <article key={sectionId(section) || sectionLabel(section)}><span>{sectionLabel(section)}</span><strong>{scoreLabel(section)}</strong><p>{displayText(section.summary, "No contextual summary was returned.")}</p></article>)}</div></section> : null}

    <footer className={styles.footer}><span>{view.maturityLabel}</span><p>Scores, evidence readiness, and approval status remain separate. Human review is required before client delivery.</p></footer>
  </section>;
}
