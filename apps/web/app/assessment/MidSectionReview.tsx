"use client";

import {useMemo, useState} from "react";
import styles from "./midReview.module.css";

type JsonRecord = Record<string, unknown>;
type Filter = "all" | "attention" | "verified";
type Tone = "critical" | "warning" | "healthy" | "neutral";

type Section = {
  id?: string;
  label?: string;
  score?: number | null;
  status?: string;
  truth_status?: string;
  summary?: string;
  evidence?: string[];
  findings?: string[];
  unavailable?: string[];
  missing_evidence_sources?: string[];
  failed_evidence_tools?: string[];
  scope_disclosures?: string[];
  confidence?: string;
  source_classification?: string;
  direct_repository_proof?: boolean;
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

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function finite(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function titleCase(value: unknown): string {
  const text = String(value || "pending").replaceAll("_", " ").trim();
  return text ? text.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Pending";
}

function unique(items: Array<string | undefined>): string[] {
  const seen = new Set<string>();
  return items.flatMap((item) => {
    const value = String(item || "").replace(/\s+/g, " ").trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return [];
    seen.add(key);
    return [value];
  });
}

function readableToolGap(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "bandit") return "Bandit did not provide accepted exact-snapshot evidence for this run.";
  if (normalized === "gitleaks") return "Gitleaks did not provide accepted same-run history evidence for this run.";
  if (/^[a-z0-9_.-]{2,30}$/.test(normalized)) return `${titleCase(normalized)} evidence is incomplete or unavailable for this run.`;
  return value;
}

function limitations(section: Section): string[] {
  return unique([
    ...(section.unavailable || []),
    ...(section.missing_evidence_sources || []),
    ...(section.failed_evidence_tools || []).map((tool) => readableToolGap(String(tool))),
  ]).map(readableToolGap);
}

function isUnscored(section: Section): boolean {
  const truth = String(section.truth_status || section.status || "").toLowerCase();
  return section.score == null || truth.includes("gray") || truth.includes("unavailable") || truth.includes("not scored");
}

function tone(section: Section): Tone {
  if (isUnscored(section)) return "neutral";
  const status = String(section.truth_status || section.status || "").toLowerCase();
  const score = finite(section.score);
  if (["red", "failed", "error", "blocked"].some((token) => status.includes(token)) || (score != null && score < 60)) return "critical";
  if ((score != null && score < 80) || (section.findings || []).length > 0) return "warning";
  return score != null && score >= 80 ? "healthy" : "warning";
}

function rowFromSection(section: Section): WeightedRow | null {
  const sectionId = String(section.id || "");
  const weight = WEIGHTS[sectionId];
  const score = finite(section.score);
  if (!weight || score == null) return null;
  const weighted = score * weight / 100;
  return {
    section_id: sectionId,
    label: section.label || titleCase(sectionId),
    score: Math.round(score),
    weight,
    weighted_points: Math.round(weighted * 100) / 100,
    projected_lift_if_verified: Math.round(Math.max(0, 80 - score) * weight) / 100,
  };
}

function weightedRows(payload: JsonRecord, sections: Section[]): WeightedRow[] {
  const intelligence = isRecord(payload.mid_score_intelligence) ? payload.mid_score_intelligence : {};
  const supplied = records(intelligence.weighted_sections).flatMap((row) => {
    const id = String(row.section_id || "");
    const score = finite(row.score);
    const weight = finite(row.weight) ?? WEIGHTS[id];
    if (!id || score == null || weight == null) return [];
    const weighted = finite(row.weighted_points) ?? score * weight / 100;
    return [{
      section_id: id,
      label: String(row.label || titleCase(id)),
      score: Math.round(score),
      weight,
      weighted_points: Math.round(weighted * 100) / 100,
      projected_lift_if_verified: finite(row.projected_lift_if_verified) ?? Math.max(0, 80 - score) * weight / 100,
    }];
  });
  if (supplied.length) return supplied;
  return sections.flatMap((section) => {
    const row = rowFromSection(section);
    return row ? [row] : [];
  });
}

function clickLegacyAction(labels: string[]) {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>('[data-nico-mid-legacy-hidden="true"] button, [data-nico-mid-legacy-hidden="true"] a'));
  const match = candidates.find((candidate) => {
    const text = String(candidate.textContent || "").toLowerCase();
    return labels.some((label) => text.includes(label));
  });
  match?.click();
}

function DetailList({items, empty}: {items: string[]; empty: string}) {
  if (!items.length) return <p className={styles.empty}>{empty}</p>;
  return <ul className={styles.detailList}>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

function ControlRow({section, expanded, onToggle}: {section: Section; expanded: boolean; onToggle: () => void}) {
  const sectionTone = tone(section);
  const evidence = unique(section.evidence || []);
  const findings = unique(section.findings || []);
  const gaps = limitations(section);
  const scope = unique([
    ...(section.scope_disclosures || []),
    section.confidence ? `Confidence: ${section.confidence}` : undefined,
    section.source_classification ? `Source classification: ${section.source_classification}` : undefined,
    typeof section.direct_repository_proof === "boolean" ? `Direct repository proof: ${section.direct_repository_proof ? "yes" : "no"}` : undefined,
  ]);
  const nextAction = findings[0] || gaps[0] || "Retain the evidence and reviewer disposition for this exact snapshot.";

  return <article className={`${styles.controlRow} ${styles[sectionTone]}`} data-mid-section={section.id || section.label}>
    <button type="button" className={styles.controlToggle} aria-expanded={expanded} onClick={onToggle}>
      <span className={styles.controlIdentity}>
        <b>{section.label || titleCase(section.id)}</b>
        <small>{titleCase(section.truth_status || section.status || "Evidence bound")}</small>
      </span>
      <span className={styles.controlCounts}>{findings.length} findings · {gaps.length} gaps</span>
      <strong>{finite(section.score) == null ? "—" : `${Math.round(Number(section.score))}/100`}</strong>
      <span className={styles.chevron} aria-hidden="true">{expanded ? "−" : "+"}</span>
    </button>
    <p className={styles.controlSummary}>{section.summary || "No evidence-bound summary was returned."}</p>
    {sectionTone !== "healthy" ? <p className={styles.nextAction}><b>Next:</b> {nextAction}</p> : null}
    {expanded ? <div className={styles.detailGrid}>
      <section><h4>Evidence <span>{evidence.length}</span></h4><DetailList items={evidence} empty="No direct evidence item was retained." /></section>
      <section><h4>Findings <span>{findings.length}</span></h4><DetailList items={findings} empty="No specific repair finding was retained." /></section>
      <section><h4>Limitations <span>{gaps.length}</span></h4><DetailList items={gaps} empty="No section-specific limitation was retained." /></section>
      <section><h4>Scope <span>{scope.length}</span></h4><DetailList items={scope} empty="Report-wide human-review boundaries apply." /></section>
    </div> : null}
  </article>;
}

export default function MidSectionReview({payload}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const assessment = isRecord(payload.assessment) ? payload.assessment : {};
  const sections = records(assessment.sections) as Section[];
  const technical = TECHNICAL_IDS.flatMap((id) => {
    const match = sections.find((section) => section.id === id);
    return match ? [match] : [];
  });
  const context = sections.filter((section) => !TECHNICAL_IDS.includes(String(section.id || "")));
  const rows = useMemo(() => weightedRows(payload, technical), [payload, technical]);
  const weightedTotal = rows.reduce((total, row) => total + row.weight, 0);
  const weightedScore = weightedTotal === 100 ? Math.round(rows.reduce((total, row) => total + row.score * row.weight / 100, 0)) : null;
  const intelligence = isRecord(payload.mid_score_intelligence) ? payload.mid_score_intelligence : {};
  const scoreContract = isRecord(intelligence.score_contract) ? intelligence.score_contract : {};
  const maturity = isRecord(assessment.maturity_signal) ? assessment.maturity_signal : {};
  const score = weightedScore
    ?? finite(scoreContract.reported_score)
    ?? finite(scoreContract.calculated_score)
    ?? finite(maturity.score)
    ?? finite(payload.technical_score);
  const projected = score == null ? null : Math.min(100, Math.round(score + rows.reduce((total, row) => total + row.projected_lift_if_verified, 0)));

  const coverage = isRecord(assessment.evidence_coverage) ? assessment.evidence_coverage : isRecord(payload.evidence_coverage) ? payload.evidence_coverage : {};
  const readiness = finite(payload.evidence_readiness)
    ?? finite(assessment.evidence_readiness)
    ?? finite(assessment.evidence_readiness_score)
    ?? finite(payload.evidence_readiness_score);
  const evidenceUnits = technical.reduce((total, section) => total + unique(section.evidence || []).length, 0);

  const lifecycle = isRecord(intelligence.report_lifecycle) ? intelligence.report_lifecycle : {};
  const reports = isRecord(payload.reports) ? payload.reports : {};
  const pdfReady = Boolean(lifecycle.pdf_available ?? reports.pdf_base64);
  const markdownReady = Boolean(lifecycle.markdown_available ?? reports.markdown);
  const rawReportStatus = String(lifecycle.draft_generation_status || payload.report_generation_status || "pending");
  const reportReady = pdfReady || markdownReady || /complete|ready|generated/i.test(rawReportStatus);
  const approval = isRecord(payload.approval_request) ? payload.approval_request : {};
  const rawReviewStatus = String(lifecycle.human_review_status || approval.status || payload.approval_request_status || "pending");
  const reviewApproved = /approved|complete/i.test(rawReviewStatus);
  const reviewLabel = reviewApproved ? "Approved" : "Required";
  const maturityLabel = String(maturity.level || assessment.maturity || "Mid");

  const priority = [...technical]
    .filter((section) => !isUnscored(section) && (finite(section.score) == null || Number(section.score) < 80 || (section.findings || []).length > 0))
    .sort((left, right) => (finite(left.score) ?? 101) - (finite(right.score) ?? 101))
    .slice(0, 3);
  const visible = technical.filter((section) => filter === "all" || (filter === "attention" ? tone(section) !== "healthy" : tone(section) === "healthy"));
  const attentionCount = technical.filter((section) => tone(section) !== "healthy").length;
  const repository = String(payload.repository || assessment.repository || "Repository assessment");
  const runId = String(payload.run_id || assessment.run_id || "");
  const expressNote = String(scoreContract.express_comparison_note || "Express is a faster baseline. Mid uses an immutable snapshot, scanner evidence, and seven fixed technical weights, so the scores are not directly interchangeable.");

  function toggle(key: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function openPriority(section: Section) {
    const key = String(section.id || section.label || "section");
    setFilter("all");
    setExpanded((current) => new Set(current).add(key));
    window.setTimeout(() => document.querySelector(`[data-mid-section="${CSS.escape(key)}"]`)?.scrollIntoView({behavior: "smooth", block: "center"}), 0);
  }

  return <section className={styles.unifiedReview} aria-label="Mid assessment review">
    <header className={styles.header}>
      <div>
        <p className={styles.eyebrow}>NICO MID ASSESSMENT</p>
        <h2>Mid Assessment Review</h2>
        <p>One evidence-bound view of the technical score, priority controls, report artifact, and required human decision.</p>
      </div>
      <span className={styles.maturityBadge}>{maturityLabel}</span>
    </header>

    <div className={styles.identity}><b>{repository}</b>{runId ? <span>Run {runId}</span> : null}</div>

    <div className={styles.statusGrid}>
      <article><small>Technical score</small><strong>{score == null ? "Pending" : `${Math.round(score)}/100`}</strong><span>Seven weighted controls</span></article>
      <article><small>Evidence readiness</small><strong>{readiness == null ? `${evidenceUnits}` : `${Math.round(readiness)}/100`}</strong><span>{readiness == null ? "Retained evidence units" : "Separate from score"}</span></article>
      <article><small>Draft report</small><strong>{reportReady ? "Ready" : titleCase(rawReportStatus)}</strong><span>{pdfReady ? "PDF available" : markdownReady ? "Markdown available" : "Artifact pending"}</span></article>
      <article><small>Human review</small><strong>{reviewLabel}</strong><span>{reviewApproved ? "Review recorded" : "Client delivery blocked"}</span></article>
    </div>

    <div className={styles.actionBar} aria-label="Mid report actions">
      <button type="button" disabled={!pdfReady} onClick={() => clickLegacyAction(["download draft pdf", "download pdf"])}>Download draft PDF</button>
      <button type="button" disabled={!markdownReady} onClick={() => clickLegacyAction(["copy markdown"])}>Copy Markdown</button>
      <button type="button" onClick={() => clickLegacyAction(["open human review", "human review"])}>Open human review</button>
    </div>

    <section className={styles.priorityPanel} aria-label="Priority controls">
      <div className={styles.sectionHeading}><div><small>REVIEW FIRST</small><h3>Highest-value controls</h3></div><span>{attentionCount} require review</span></div>
      <div className={styles.priorityList}>{priority.map((section, index) => <button type="button" key={section.id || section.label} onClick={() => openPriority(section)}>
        <span>{index + 1}</span><b>{section.label || titleCase(section.id)}</b><strong>{Math.round(Number(section.score))}/100</strong>
      </button>)}</div>
    </section>

    <details className={styles.scoreDetails}>
      <summary><span><b>Score explanation</b><small>Current {score == null ? "pending" : `${Math.round(score)}/100`} · verified-fix scenario {projected == null ? "pending" : `${projected}/100`}</small></span><span aria-hidden="true">+</span></summary>
      <p>{expressNote}</p>
      <div className={styles.weightTable} role="table" aria-label="Weighted technical score">
        <div className={styles.weightHead} role="row"><b>Control</b><b>Score</b><b>Weight</b><b>Points</b></div>
        {rows.map((row) => <div role="row" key={row.section_id}><span>{row.label}</span><span>{row.score}</span><span>{row.weight}%</span><span>{row.weighted_points.toFixed(2)}</span></div>)}
      </div>
      <p className={styles.disclosure}>Evidence-unit coverage{finite(coverage.percent) == null ? "" : ` is ${Math.round(Number(coverage.percent))}% and`} does not directly change the technical score. Projections require verified repair evidence and a new immutable snapshot assessment.</p>
    </details>

    <div className={styles.toolbar}>
      <div className={styles.filterChips} role="group" aria-label="Filter technical controls">
        {(["all", "attention", "verified"] as Filter[]).map((value) => <button type="button" key={value} aria-pressed={filter === value} className={filter === value ? styles.activeFilter : ""} onClick={() => setFilter(value)}>{value === "all" ? "All controls" : value === "attention" ? "Needs review" : "Verified strength"}</button>)}
      </div>
      <button type="button" className={styles.collapseButton} onClick={() => setExpanded(new Set())}>Collapse all</button>
    </div>

    <div className={styles.controlList}>{visible.map((section) => {
      const key = String(section.id || section.label || "section");
      return <ControlRow key={key} section={section} expanded={expanded.has(key)} onToggle={() => toggle(key)} />;
    })}</div>

    {context.length ? <details className={styles.contextPanel}>
      <summary><span><b>Additional evidence requested</b><small>{context.length} human-context modules · excluded from technical score</small></span><span aria-hidden="true">+</span></summary>
      <div className={styles.contextList}>{context.map((section) => <article key={section.id || section.label}><b>{section.label || titleCase(section.id)}</b><p>{section.summary || limitations(section)[0] || "Validated external context is required."}</p></article>)}</div>
    </details> : null}

    <p className={styles.safety}>Human review is required before approval or client delivery. NICO did not modify the assessed repository, and recommendations do not prove repairs were completed.</p>
  </section>;
}
