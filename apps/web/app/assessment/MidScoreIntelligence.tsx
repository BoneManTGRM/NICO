"use client";

import styles from "./assessment.module.css";

type Section = {
  id?: string;
  label?: string;
  score?: number | null;
  status?: string;
  findings?: string[];
  unavailable?: string[];
};

type IntelligenceRow = {
  section_id?: string;
  label?: string;
  score?: number;
  status?: string;
  weight?: number;
  weighted_points?: number;
  maximum_weighted_points?: number;
  weighted_gap_to_100?: number;
  bounded_target_score?: number;
  projected_lift_if_verified?: number;
  finding_count?: number;
  unavailable_count?: number;
};

type ScoreIntelligence = {
  status?: string;
  score_contract?: {
    name?: string;
    reported_score?: number | null;
    calculated_score?: number | null;
    calculation_matches_reported_score?: boolean | null;
    express_directly_comparable?: boolean;
    express_comparison_note?: string;
  };
  weighted_sections?: IntelligenceRow[];
  top_constraints?: IntelligenceRow[];
  bounded_improvement_scenario?: {
    current_score?: number | null;
    projected_score?: number | null;
    projected_lift?: number;
    target_policy?: string;
    guaranteed?: boolean;
    requires_verified_reassessment?: boolean;
  };
  report_lifecycle?: {
    draft_generation_status?: string;
    markdown_available?: boolean;
    pdf_available?: boolean;
    human_review_status?: string;
    client_delivery_allowed?: boolean;
  };
};

type Props = {
  result: {
    mid_score_intelligence?: ScoreIntelligence;
    report_generation_status?: string;
    approval_request_status?: string;
    approval_request?: {status?: string};
    reports?: {markdown?: string; pdf_base64?: string};
  };
  document: {
    maturity_signal?: {score?: number};
    sections?: Section[];
  } | null;
};

const WEIGHTS: Record<string, number> = {
  code_audit: 20,
  dependency_health: 15,
  secrets_review: 10,
  static_analysis: 15,
  ci_cd: 15,
  architecture_debt: 15,
  velocity_complexity: 10,
};

function finite(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fallbackRows(sections: Section[] = []): IntelligenceRow[] {
  return sections.flatMap((section) => {
    const id = String(section.id || "");
    const weight = WEIGHTS[id];
    const score = finite(section.score);
    if (!weight || score == null || String(section.status || "").toLowerCase() === "gray") return [];
    const weighted = Math.round((score * weight / 100) * 100) / 100;
    const target = Math.max(Math.round(score), 80);
    return [{
      section_id: id,
      label: section.label || id.replaceAll("_", " "),
      score: Math.round(score),
      status: section.status || "unknown",
      weight,
      weighted_points: weighted,
      maximum_weighted_points: weight,
      weighted_gap_to_100: Math.round((weight - weighted) * 100) / 100,
      bounded_target_score: target,
      projected_lift_if_verified: Math.round(((target - score) * weight / 100) * 100) / 100,
      finding_count: section.findings?.length || 0,
      unavailable_count: section.unavailable?.length || 0,
    }];
  });
}

function statusText(value: unknown): string {
  return String(value || "pending").replaceAll("_", " ");
}

export default function MidScoreIntelligence({result, document}: Props) {
  const intelligence = result.mid_score_intelligence;
  const rows = intelligence?.weighted_sections?.length
    ? intelligence.weighted_sections
    : fallbackRows(document?.sections || []);
  if (!rows.length) return null;

  const calculated = finite(intelligence?.score_contract?.calculated_score)
    ?? finite(document?.maturity_signal?.score);
  const constraints = intelligence?.top_constraints?.length
    ? intelligence.top_constraints
    : [...rows].sort((a, b) => Number(b.weighted_gap_to_100 || 0) - Number(a.weighted_gap_to_100 || 0)).slice(0, 4);
  const fallbackLift = rows.reduce((total, row) => total + Number(row.projected_lift_if_verified || 0), 0);
  const projected = finite(intelligence?.bounded_improvement_scenario?.projected_score)
    ?? (calculated == null ? null : Math.min(100, Math.round(calculated + fallbackLift)));
  const lifecycle = intelligence?.report_lifecycle;
  const reportStatus = lifecycle?.draft_generation_status || result.report_generation_status || "pending";
  const reviewStatus = lifecycle?.human_review_status || result.approval_request?.status || result.approval_request_status || "pending";
  const pdfReady = lifecycle?.pdf_available ?? Boolean(result.reports?.pdf_base64);
  const markdownReady = lifecycle?.markdown_available ?? Boolean(result.reports?.markdown);

  return <section className={styles.scoreIntelligence} aria-label="Mid score intelligence">
    <div className={styles.scoreIntelligenceHead}>
      <div>
        <p className="eyebrow">MID SCORE INTELLIGENCE</p>
        <h3>What the score means and what constrains it</h3>
      </div>
      <span className="status yellow">{calculated == null ? "Pending" : `${Math.round(calculated)}/100`}</span>
    </div>

    <p className="summary-box">
      {intelligence?.score_contract?.express_comparison_note
        || "Express is a faster baseline. Mid is a different, stricter assessment built from an exact snapshot, scanner evidence, and seven fixed technical weights, so the two numbers are not the same test repeated."}
    </p>

    <div className={styles.scoreMetrics}>
      <article><b>Current Mid score</b><span>{calculated == null ? "Pending" : `${Math.round(calculated)}/100`}</span><small>Seven weighted technical sections</small></article>
      <article><b>Verified-fix scenario</b><span>{projected == null ? "Pending" : `${Math.round(projected)}/100`}</span><small>Scenario only; requires reassessment</small></article>
      <article><b>Draft report</b><span>{statusText(reportStatus)}</span><small>{pdfReady ? "PDF ready" : markdownReady ? "Markdown ready; PDF pending" : "Artifact pending"}</small></article>
      <article><b>Human review</b><span>{statusText(reviewStatus)}</span><small>Client delivery remains blocked</small></article>
    </div>

    <div className={styles.constraintGrid}>
      {constraints.map((row, index) => <article key={row.section_id || `${row.label}-${index}`}>
        <div><b>{index + 1}. {row.label || row.section_id}</b><span>{row.score}/100</span></div>
        <p>Weight {row.weight}% · contributes {Number(row.weighted_points || 0).toFixed(2)} of {row.maximum_weighted_points || row.weight} points.</p>
        <small>Verified improvement to {row.bounded_target_score || 80} could add about {Number(row.projected_lift_if_verified || 0).toFixed(2)} points. Findings: {row.finding_count || 0}; limitations: {row.unavailable_count || 0}.</small>
      </article>)}
    </div>

    <details className="help-details">
      <summary>Show all weighted score contributions</summary>
      <div className={styles.weightTable}>
        <div className={styles.weightHeader}><b>Section</b><b>Score</b><b>Weight</b><b>Contribution</b></div>
        {rows.map((row) => <div key={row.section_id || row.label}>
          <span>{row.label || row.section_id}</span>
          <span>{row.score}/100</span>
          <span>{row.weight}%</span>
          <span>{Number(row.weighted_points || 0).toFixed(2)}</span>
        </div>)}
      </div>
      <p className="muted">Gray, unscored business-context sections are excluded. Evidence readiness is tracked separately. Projections are bounded scenarios, not promises or automatic score changes.</p>
    </details>
  </section>;
}
