"use client";

import {useMemo, useState} from "react";
import styles from "./assessment.module.css";

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

type Props = {
  sections?: Section[];
};

type Filter = "all" | "attention" | "verified" | "unscored";
type Tone = "critical" | "warning" | "healthy" | "neutral";

const TECHNICAL_IDS = new Set([
  "code_audit",
  "dependency_health",
  "secrets_review",
  "static_analysis",
  "ci_cd",
  "architecture_debt",
  "velocity_complexity",
]);

function unique(items: Array<string | undefined>): string[] {
  const seen = new Set<string>();
  return items.flatMap((item) => {
    const value = String(item || "").trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return [];
    seen.add(key);
    return [value];
  });
}

function statusText(section: Section): string {
  return String(section.truth_status || section.status || "unknown").replaceAll("_", " ");
}

function limitationItems(section: Section): string[] {
  return unique([
    ...(section.unavailable || []),
    ...(section.missing_evidence_sources || []),
    ...(section.failed_evidence_tools || []).map((tool) => `Evidence tool unavailable or failed: ${tool}`),
  ]);
}

function isUnscored(section: Section): boolean {
  const status = statusText(section).toLowerCase();
  return section.score == null || status.includes("gray") || status.includes("unavailable") || status.includes("not scored");
}

function sectionTone(section: Section): Tone {
  const status = statusText(section).toLowerCase();
  const score = typeof section.score === "number" ? section.score : null;
  const limitations = limitationItems(section).length;
  if (["red", "failed", "error", "blocked"].some((value) => status.includes(value))) return "critical";
  if (isUnscored(section)) return "neutral";
  if (score != null && score < 60) return "critical";
  if (["yellow", "limited", "pending", "review"].some((value) => status.includes(value)) || limitations > 0 || (score != null && score < 80)) return "warning";
  if (["green", "verified", "complete", "passed"].some((value) => status.includes(value)) && score != null && score >= 80) return "healthy";
  return score != null && score >= 80 ? "healthy" : "warning";
}

function sectionKey(section: Section, index: number): string {
  return String(section.id || section.label || `section-${index}`);
}

function scoreLabel(section: Section): string {
  return typeof section.score === "number" ? `${Math.round(section.score)}/100` : "Not scored";
}

function matchesFilter(section: Section, filter: Filter): boolean {
  const tone = sectionTone(section);
  if (filter === "attention") return tone === "critical" || tone === "warning";
  if (filter === "verified") return tone === "healthy";
  if (filter === "unscored") return isUnscored(section);
  return true;
}

function ListBlock({items, empty}: {items: string[]; empty: string}) {
  if (!items.length) return <p className={styles.emptyReviewState}>{empty}</p>;
  return <ul className={styles.reviewList}>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>;
}

function ReviewCard({section, itemKey, expanded, onToggle}: {section: Section; itemKey: string; expanded: boolean; onToggle: () => void}) {
  const tone = sectionTone(section);
  const evidence = unique(section.evidence || []);
  const findings = unique(section.findings || []);
  const limitations = limitationItems(section);
  const scope = unique([
    ...(section.scope_disclosures || []),
    section.confidence ? `Confidence: ${section.confidence}` : undefined,
    section.source_classification ? `Source classification: ${section.source_classification}` : undefined,
    typeof section.direct_repository_proof === "boolean" ? `Direct repository proof: ${section.direct_repository_proof ? "yes" : "no"}` : undefined,
  ]);
  const nextAction = findings[0] || limitations[0] || "Validate the retained evidence and record the reviewer disposition.";
  const score = typeof section.score === "number" ? Math.max(0, Math.min(100, section.score)) : 0;

  return <article className={`${styles.reviewCard} ${styles[tone]}`} data-section-id={itemKey}>
    <button type="button" className={styles.reviewToggle} aria-expanded={expanded} onClick={onToggle}>
      <span className={styles.reviewIdentity}>
        <span className={styles.reviewTitle}>{section.label || section.id || "Assessment section"}</span>
        <span className={styles.reviewStatus}>{statusText(section)}</span>
      </span>
      <span className={styles.reviewCounts} aria-label="Section evidence counts">
        <span>{evidence.length} evidence</span>
        <span>{findings.length} findings</span>
        <span>{limitations.length} gaps</span>
      </span>
      <span className={styles.reviewScore}>{scoreLabel(section)}</span>
      <span className={styles.reviewChevron} aria-hidden="true">{expanded ? "−" : "+"}</span>
    </button>

    <div className={styles.scoreTrack} aria-hidden="true"><span style={{width: `${score}%`}} /></div>
    <p className={styles.reviewSummary}>{section.summary || "No evidence-bound conclusion was returned."}</p>
    <p className={styles.nextAction}><b>Next review action:</b> {nextAction}</p>

    {expanded ? <div className={styles.reviewDetailGrid}>
      <section>
        <h4>Evidence reviewed <span>{evidence.length}</span></h4>
        <ListBlock items={evidence} empty="No direct evidence item was retained." />
      </section>
      <section>
        <h4>Findings <span>{findings.length}</span></h4>
        <ListBlock items={findings} empty="No specific finding was retained. Reviewer validation still applies." />
      </section>
      <section>
        <h4>Limitations and gaps <span>{limitations.length}</span></h4>
        <ListBlock items={limitations} empty="No section-specific limitation was retained." />
      </section>
      <section>
        <h4>Scope and confidence <span>{scope.length}</span></h4>
        <ListBlock items={scope} empty="The report-wide evidence and human-review boundaries apply." />
      </section>
    </div> : null}
  </article>;
}

export default function MidSectionReview({sections = []}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const rows = useMemo(() => sections.filter((section) => section && (section.id || section.label)), [sections]);
  const metrics = useMemo(() => {
    const tones = rows.map(sectionTone);
    return {
      attention: tones.filter((tone) => tone === "critical" || tone === "warning").length,
      verified: tones.filter((tone) => tone === "healthy").length,
      unscored: rows.filter(isUnscored).length,
      evidence: rows.reduce((total, section) => total + unique(section.evidence || []).length, 0),
      findings: rows.reduce((total, section) => total + unique(section.findings || []).length, 0),
      gaps: rows.reduce((total, section) => total + limitationItems(section).length, 0),
    };
  }, [rows]);

  const priorities = useMemo(() => rows
    .filter((section) => TECHNICAL_IDS.has(String(section.id || "")) && ["critical", "warning"].includes(sectionTone(section)))
    .sort((left, right) => {
      const leftScore = typeof left.score === "number" ? left.score : 101;
      const rightScore = typeof right.score === "number" ? right.score : 101;
      if (leftScore !== rightScore) return leftScore - rightScore;
      return limitationItems(right).length - limitationItems(left).length;
    })
    .slice(0, 3), [rows]);

  const visible = rows.filter((section) => matchesFilter(section, filter));
  const technical = visible.filter((section) => TECHNICAL_IDS.has(String(section.id || "")));
  const context = visible.filter((section) => !TECHNICAL_IDS.has(String(section.id || "")));

  function toggle(itemKey: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(itemKey)) next.delete(itemKey);
      else next.add(itemKey);
      return next;
    });
  }

  function expandAttention() {
    setExpanded(new Set(rows.flatMap((section, index) => {
      const tone = sectionTone(section);
      return tone === "critical" || tone === "warning" ? [sectionKey(section, index)] : [];
    })));
  }

  if (!rows.length) return null;

  return <section className={styles.sectionReview} aria-label="Mid assessment section review">
    <div className={styles.sectionReviewHead}>
      <div>
        <p className="eyebrow">MID REVIEW WORKBENCH</p>
        <h3>Review the result by exception, not by scrolling through twelve oversized cards</h3>
        <p>Technical controls and human-context modules are separated. Open only the sections that require evidence review or a decision.</p>
      </div>
      <span className={metrics.attention ? "status yellow" : "status green"}>{metrics.attention} need attention</span>
    </div>

    <div className={styles.reviewMetrics}>
      <article><b>Needs attention</b><span>{metrics.attention}</span><small>Scored controls with risk or limitations</small></article>
      <article><b>Verified strength</b><span>{metrics.verified}</span><small>Evidence-supported controls</small></article>
      <article><b>Unscored context</b><span>{metrics.unscored}</span><small>Requires human evidence</small></article>
      <article><b>Evidence units</b><span>{metrics.evidence}</span><small>{metrics.findings} findings · {metrics.gaps} gaps</small></article>
    </div>

    {priorities.length ? <div className={styles.priorityStrip}>
      <b>Review first</b>
      {priorities.map((section, index) => <button type="button" key={sectionKey(section, index)} onClick={() => {
        const key = sectionKey(section, rows.indexOf(section));
        setFilter("all");
        setExpanded((current) => new Set(current).add(key));
        window.setTimeout(() => document.querySelector(`[data-section-id="${CSS.escape(key)}"]`)?.scrollIntoView({behavior: "smooth", block: "center"}), 0);
      }}>
        <span>{index + 1}</span>{section.label || section.id}<strong>{scoreLabel(section)}</strong>
      </button>)}
    </div> : null}

    <div className={styles.reviewToolbar}>
      <div className={styles.filterGroup} role="group" aria-label="Filter assessment sections">
        {(["all", "attention", "verified", "unscored"] as Filter[]).map((value) => <button
          type="button"
          key={value}
          className={filter === value ? styles.activeFilter : ""}
          aria-pressed={filter === value}
          onClick={() => setFilter(value)}
        >{value === "all" ? "All sections" : value === "attention" ? "Needs attention" : value === "verified" ? "Verified" : "Unscored context"}</button>)}
      </div>
      <div className={styles.expandActions}>
        <button type="button" onClick={expandAttention}>Open attention areas</button>
        <button type="button" onClick={() => setExpanded(new Set())}>Collapse all</button>
      </div>
    </div>

    {technical.length ? <div className={styles.reviewGroup}>
      <div className={styles.reviewGroupHead}><h4>Scored technical controls</h4><span>{technical.length} shown</span></div>
      <div className={styles.reviewCardList}>{technical.map((section) => {
        const index = rows.indexOf(section);
        const key = sectionKey(section, index);
        return <ReviewCard key={key} section={section} itemKey={key} expanded={expanded.has(key)} onToggle={() => toggle(key)} />;
      })}</div>
    </div> : null}

    {context.length ? <div className={styles.reviewGroup}>
      <div className={styles.reviewGroupHead}><h4>Human-context modules</h4><span>{context.length} shown · excluded from technical score</span></div>
      <div className={styles.reviewCardList}>{context.map((section) => {
        const index = rows.indexOf(section);
        const key = sectionKey(section, index);
        return <ReviewCard key={key} section={section} itemKey={key} expanded={expanded.has(key)} onToggle={() => toggle(key)} />;
      })}</div>
    </div> : null}

    {!technical.length && !context.length ? <p className={styles.emptyReviewState}>No sections match the selected filter.</p> : null}
  </section>;
}
