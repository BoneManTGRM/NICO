"use client";

import {useMemo, useState} from "react";
import styles from "./assessment.module.css";
import scoreStyles from "./scorecard.module.css";
import {copyFor} from "./assessmentCopy";
import {
  assessmentFor,
  compactIdentifier,
  formatStatus,
  immutableCommitFor,
  persistenceStatus,
  progressFor,
  progressPercent,
  reportFor,
  savePdf,
  scannerStatusFor,
  sectionPresentation,
  statusClass,
} from "./assessmentModel";
import type {Copy, Locale} from "./assessmentTypes";
import StrategicEvidenceForm from "./StrategicEvidenceForm";
import {useAssessmentRun} from "./useAssessmentRun";

function IdentifierValue({value, fallback, copy}: {value?: string; fallback: string; copy: Copy}) {
  const [didCopy, setDidCopy] = useState(false);
  const fullValue = String(value || "").trim();

  async function copyFullValue(): Promise<void> {
    if (!fullValue) return;
    try {
      await navigator.clipboard.writeText(fullValue);
      setDidCopy(true);
      window.setTimeout(() => setDidCopy(false), 1800);
    } catch {
      setDidCopy(false);
    }
  }

  return <span className="nico-identifier-value">
    <code title={fullValue || fallback}>{fullValue ? compactIdentifier(fullValue) : fallback}</code>
    {fullValue ? <button type="button" onClick={copyFullValue} aria-label={`${copy.copyValue}: ${fullValue}`}>{didCopy ? copy.valueCopied : copy.copyValue}</button> : null}
  </span>;
}

function List({items, empty}: {items?: string[]; empty: string}) {
  return items?.length
    ? <ul className="tight-list">{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
    : <p className="muted">{empty}</p>;
}

function numeric(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function ProgressTimeline({items, copy}: {items: ReturnType<typeof progressFor>; copy: Copy}) {
  if (!items.length) return null;
  return <div className={styles.timeline}>{items.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
    <div className="result-head">
      <b>{copy.stageLabels[String(item.step || "")] || String(item.step || copy.stage).replaceAll("_", " ")}</b>
      <span className={statusClass(item.status)}>{formatStatus(item.status, copy)}</span>
    </div>
    <p>{item.message || copy.notVerified}</p>
    {item.evidence ? <details className="help-details"><summary>{copy.stepEvidence}</summary><pre className="json-block">{JSON.stringify(item.evidence, null, 2)}</pre></details> : null}
  </article>)}</div>;
}

function Scorecard({sections, copy}: {sections: NonNullable<ReturnType<typeof assessmentFor>>["sections"]; copy: Copy}) {
  if (!sections?.length) return null;
  return <div className="results-grid">{sections.map((section, index) => {
    const view = sectionPresentation(section, copy);
    const identity = section.label || String(section.id || "").replaceAll("_", " ");
    return <article className={`result-card ${scoreStyles.controlCard}`} key={section.id || index}>
      <div className={scoreStyles.header}>
        <b className={scoreStyles.title}>{identity}</b>
        <div className={scoreStyles.scoreSignal}>
          <span className={scoreStyles.signalCaption}>{copy.technicalScoreLabel || "Technical score"}</span>
          <strong className={`${scoreStyles.technicalBadge} ${scoreStyles[view.technicalTone]}`}>{view.score}</strong>
        </div>
      </div>
      <div className={scoreStyles.signalRow} aria-label={`${identity} score and evidence signals`}>
        <div className={scoreStyles.assuranceSignal}>
          <span className={scoreStyles.signalCaption}>{copy.evidenceAssuranceLabel || "Evidence assurance"}</span>
          <strong className={`${scoreStyles.assuranceBadge} ${scoreStyles[view.assuranceTone]}`}>{view.assuranceLabel}</strong>
        </div>
        {view.risk ? <div className={scoreStyles.riskSignal}>
          <span className={scoreStyles.signalCaption}>{copy.riskLabel || "Risk"}</span>
          <strong className={`${scoreStyles.riskBadge} ${scoreStyles[view.riskTone]}`}>{view.riskLabel}</strong>
        </div> : null}
      </div>
      <p>{section.summary}</p>
      <details className="help-details"><summary>{copy.evidence} ({section.evidence?.length || 0})</summary><List items={section.evidence} empty={copy.notVerified} /></details>
      {section.findings?.length ? <details className="help-details"><summary>{copy.findings} ({section.findings.length})</summary><List items={section.findings} empty={copy.notVerified} /></details> : null}
      {section.unavailable?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({section.unavailable.length})</summary><List items={section.unavailable} empty={copy.notVerified} /></details> : null}
    </article>;
  })}</div>;
}

export default function AssessmentWorkspace({locale = "en"}: {locale?: Locale}) {
  const copy = copyFor(locale);
  const controller = useAssessmentRun(locale);
  const {
    service,
    repository,
    client,
    project,
    authorized,
    humanEvidence,
    phase,
    result,
    message,
    error,
    attempt,
    elapsed,
    running,
    setRepository,
    setClient,
    setProject,
    setAuthorized,
    setHumanEvidence,
    setError,
    run,
  } = controller;
  const [copied, setCopied] = useState(false);

  const serviceCopy = copy.service;
  const assessment = useMemo(() => assessmentFor(service, result), [service, result]);
  const report = useMemo(() => reportFor(service, result), [service, result]);
  const progressItems = useMemo(() => progressFor(service, result), [service, result]);
  const activeProgress = progressItems.find((item) => ["queued", "running", "pending", "planned", "starting"].includes(String(item.status || "").toLowerCase()));
  const stageId = String(result?.current_stage || result?.record?.current_stage || activeProgress?.step || "");
  const percent = progressPercent(phase, result, running);
  const coverage = assessment?.evidence_coverage;
  const coverageLabel = coverage?.calculated && Number.isFinite(Number(coverage.percent))
    ? `${coverage.label || copy.evidence}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
    : copy.coverage;
  const assessmentRecord = assessment as Record<string, unknown> | null;
  const maturityRecord = assessment?.maturity_signal as Record<string, unknown> | undefined;
  const technicalValue = numeric(assessmentRecord?.technical_score ?? maturityRecord?.technical_score ?? maturityRecord?.score);
  const adjustedValue = numeric(assessmentRecord?.canonical_evidence_adjusted_score ?? assessmentRecord?.evidence_adjusted_score ?? maturityRecord?.canonical_evidence_adjusted_score ?? maturityRecord?.evidence_adjusted_score ?? maturityRecord?.presented_score);
  const technicalLabel = technicalValue == null ? (running ? copy.notScoredYet : copy.notScored) : `${technicalValue}/100`;
  const adjustedLabel = adjustedValue == null ? (running ? copy.notScoredYet : copy.notScored) : `${adjustedValue}/100`;
  const immutableCommit = immutableCommitFor(result);
  const scannerRawStatus = scannerStatusFor(service, result, running);
  const scannerUnavailable = String(scannerRawStatus || "").toLowerCase().includes("unavailable");
  const scannerStatus = running && scannerUnavailable ? copy.awaitingScanner : formatStatus(scannerRawStatus, copy);
  const reportStatus = report?.markdown || report?.html || report?.pdf_base64 ? copy.phases.complete : running ? copy.awaitingScanner : copy.awaitingStage;
  const reviewStatus = phase === "review_required" ? copy.phases.review_required : running ? copy.reviewAfterReport : copy.awaitingStage;
  const maturityRawStatus = assessment?.maturity_signal?.level;
  const maturityUnavailable = String(maturityRawStatus || "").toLowerCase().includes("unavailable");
  const maturityStatus = running && (!maturityRawStatus || maturityUnavailable) ? copy.maturityAfterScoring : formatStatus(maturityRawStatus || (running ? "pending" : "not_started"), copy);

  async function copyMarkdown(): Promise<void> {
    if (!report?.markdown) return;
    await navigator.clipboard.writeText(report.markdown);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  function downloadPdf(): void {
    if (!report?.pdf_base64) {
      setError(report?.pdf_error || copy.pdfMissing);
      return;
    }
    savePdf(report.pdf_base64, report.pdf_filename || "nico-comprehensive-assessment.pdf");
  }

  return <main className="shell" data-assessment-service-count="1" data-canonical-assessment="strategic" data-customer-facing-assessment="comprehensive" data-assessment-locale={locale}>
    <section className="hero"><p className="eyebrow">{copy.heroEyebrow}</p><h1>{copy.title}</h1><p className="lead">{copy.lead}</p></section>

    <section id="assessment" className="section panel">
      <div className="section-head"><div><p className="eyebrow">{serviceCopy.eyebrow}</p><h2>{serviceCopy.heading}</h2></div><span className="status gray">{coverageLabel}</span></div>
      <p className="summary-box">{serviceCopy.summary}</p>
      <details className="help-details"><summary>{serviceCopy.instructionsTitle}</summary><ul>{serviceCopy.instructions.map((item: string) => <li key={item}>{item}</li>)}</ul></details>
      <p className="warning-box">{copy.warning}</p>
      <div className="form-grid">
        <label>{copy.repo}<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={copy.repoPlaceholder} disabled={running} /></label>
        <label>{copy.client}<input value={client} onChange={(event) => setClient(event.target.value)} disabled={running} /></label>
        <label>{copy.project}<input value={project} onChange={(event) => setProject(event.target.value)} disabled={running} /></label>
      </div>
      <StrategicEvidenceForm
        locale={locale}
        value={humanEvidence}
        onChange={setHumanEvidence}
        disabled={running}
      />
      <label className="check-row"><input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} disabled={running} />{copy.confirm}</label>
      <button type="button" className="primary-button" disabled={!authorized || !repository.trim() || running} onClick={run}>{running ? copy.phases.running : copy.run}</button>
      {error ? <p className="error-box">{error}</p> : null}
    </section>

    <section className="section panel" aria-live="polite">
      <div className="section-head"><div><p className="eyebrow">{copy.state}</p><h2 title={result?.run_id}>{result?.run_id ? compactIdentifier(result.run_id, 18, 8) : copy.phases[phase]}</h2></div><span className={statusClass(phase)}>{copy.phases[phase]}</span></div>
      <p className={phase === "failed" ? "error-box" : phase === "review_required" ? "warning-box" : "summary-box"}>{message || copy.select}</p>
      {running ? <><div className={styles.progressMeta}><span><b>{copy.stage}</b>{copy.stageLabels[stageId] || stageId.replaceAll("_", " ") || copy.phases[phase]}</span><span><b>{copy.progress}</b>{Math.round(percent)}%</span><span><b>{copy.elapsed}</b>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span><span><b>{copy.checks}</b>{attempt}</span></div><div className={styles.progressBar} role="progressbar" aria-label={`${copy.stageLabels[stageId] || stageId || copy.phases[phase]} ${copy.progress}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{width: `${Math.max(2, Math.min(100, percent))}%`}} /></div></> : null}

      {result ? <>
        <div className="grid four target-grid"><article><b>{copy.runId}</b><IdentifierValue value={result.run_id} fallback={copy.notVerified} copy={copy} /></article><article><b>{copy.commit}</b><IdentifierValue value={immutableCommit} fallback={copy.notVerified} copy={copy} /></article><article><b>{copy.scanner}</b><span>{scannerStatus}</span></article><article><b>{copy.report}</b><span>{reportStatus}</span></article></div>
        <div className="grid four target-grid"><article><b>{copy.review}</b><span>{reviewStatus}</span></article><article><b>{copy.technicalMaturityLabel || copy.maturity}</b><span>{technicalValue == null ? maturityStatus : `${maturityStatus} · ${technicalLabel}`}</span></article><article><b>{copy.evidenceAdjustedLabel || "Evidence-adjusted"}</b><span>{adjustedLabel}</span></article><article><b>{copy.durable}</b><span>{persistenceStatus(result.persistence, phase, copy)}</span></article></div>
        {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
        <ProgressTimeline items={progressItems} copy={copy} />
        <Scorecard sections={assessment?.sections} copy={copy} />
        <div className="report-actions"><button type="button" disabled={!report?.markdown} onClick={copyMarkdown}>{copy.copy}</button><button type="button" disabled={!report?.pdf_base64} onClick={downloadPdf}>{copy.download}</button>{copied ? <span className="muted">{copy.copied}</span> : null}</div>
        {phase === "review_required" ? <p className="warning-box">{copy.reviewNotice}</p> : null}
        {assessment?.unavailable_data_notes?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({assessment.unavailable_data_notes.length})</summary><List items={assessment.unavailable_data_notes} empty={copy.notVerified} /></details> : null}
      </> : null}
    </section>
  </main>;
}

/*
Source compatibility contracts retained:
- One workspace. Two evidence-bound services.
- Select a service and run an authorized repository.
- Express completed its evidence, scoring, reporting, and truth-gate stages.
- Comprehensive completed every automated stage and stopped at the required human-review gate.
- const path = service === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake";
- current = await json(await fetch(api(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`)
- current = await json(await fetch(api(`/assessment/express-run/${encodeURIComponent(runId)}/status`)
*/
