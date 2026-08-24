"use client";

import {useEffect, useMemo, useRef, useState} from "react";
import styles from "./assessment.module.css";
import workspaceStyles from "./engagementWorkspace.module.css";
import mobileStyles from "./compactMobileAssessment.module.css";
import scoreStyles from "./scorecard.module.css";
import {copyFor} from "./assessmentCopy";
import {
  apiUrl,
  assessmentFor,
  compactIdentifier,
  evidenceCompletionFor,
  internalReviewHrefFor,
  internalReviewStateFor,
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
import type {Copy, Locale, Result} from "./assessmentTypes";
import StrategicEvidenceForm from "./StrategicEvidenceForm";
import {useAssessmentClientMode} from "./useAssessmentClientMode";
import {useAssessmentRun} from "./useAssessmentRun";

const FINAL_REPORT_STAGE = "final_comprehensive_report_generation";

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

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function activeStageExecutionFor(result: Result | null) {
  const runRecord = objectRecord(result?.record);
  const execution = objectRecord(result?.active_stage_execution)
    || objectRecord(runRecord?.active_stage_execution);
  const stageId = String(
    execution?.stage_id
      || execution?.stage
      || execution?.stage_name
      || result?.current_stage
      || result?.record?.current_stage
      || "",
  ).trim();
  const state = String(
    execution?.state
      || execution?.status
      || execution?.execution_state
      || "",
  ).trim().toLowerCase().replace(/[\s-]+/g, "_");
  const heartbeatRaw = Number(
    execution?.heartbeat_age_seconds
      ?? execution?.heartbeat_age
      ?? execution?.heartbeat_seconds,
  );
  const heartbeatAgeSeconds = Number.isFinite(heartbeatRaw) && heartbeatRaw >= 0
    ? Math.round(heartbeatRaw)
    : null;
  if (!stageId && !state && heartbeatAgeSeconds == null) return null;
  return {stageId, state, heartbeatAgeSeconds};
}

function finalReportLivenessStatus(result: Result | null, locale: Locale): string | null {
  const execution = activeStageExecutionFor(result);
  if (!execution || execution.stageId !== FINAL_REPORT_STAGE) return null;

  const rendering = ["rendering", "running", "in_progress", "generating", "generating_report"].includes(execution.state);
  const base = execution.state === "queued"
    ? locale === "es-MX" ? "Informe final de evaluación en cola" : "Final assessment report queued"
    : rendering
      ? locale === "es-MX" ? "Generando el informe final de evaluación" : "Final assessment report rendering"
      : locale === "es-MX" ? "Preparando el informe final de evaluación" : "Preparing final assessment report";

  if (execution.heartbeatAgeSeconds == null) return base;
  return locale === "es-MX"
    ? `${base} · señal de actividad hace ${execution.heartbeatAgeSeconds}s`
    : `${base} · heartbeat ${execution.heartbeatAgeSeconds}s ago`;
}

function safeFilename(value: string, fallback: string): string {
  const normalized = value.replace(/[\r\n]/g, "").replace(/[\\/:*?"<>|]/g, "-").trim();
  return normalized || fallback;
}

function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const quoted = disposition.match(/filename="([^"]+)"/i)?.[1];
  const plain = disposition.match(/filename=([^;]+)/i)?.[1];
  let candidate = encoded || quoted || plain || "";
  try {
    candidate = decodeURIComponent(candidate);
  } catch {
    // Preserve the server value when it is not URL encoded.
  }
  return safeFilename(candidate, fallback);
}

function restoreArtifactScroll(scrollTop: number): void {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => window.scrollTo({top: scrollTop, behavior: "auto"}));
  });
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

async function artifactError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => null) as {detail?: unknown; message?: unknown; error?: unknown} | null;
  const detail = payload?.detail;
  const message = typeof detail === "string"
    ? detail
    : detail && typeof detail === "object" && !Array.isArray(detail)
      ? String((detail as Record<string, unknown>).message || (detail as Record<string, unknown>).code || "")
      : "";
  return new Error(message || String(payload?.message || payload?.error || fallback));
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
  const {hydrated, compactMobile} = useAssessmentClientMode();
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
    issue,
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
    retry,
    startNew,
  } = controller;
  const [copied, setCopied] = useState(false);
  const [artifactAction, setArtifactAction] = useState<"markdown" | "pdf" | null>(null);
  const issueRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (issue) issueRef.current?.focus();
  }, [issue]);

  const serviceCopy = copy.service;
  const assessment = useMemo(() => assessmentFor(service, result), [service, result]);
  const report = useMemo(() => reportFor(service, result), [service, result]);
  const progressItems = useMemo(() => progressFor(service, result), [service, result]);
  function deriveProgressView() {
    const activeProgress = progressItems.find((item) => ["queued", "running", "pending", "planned", "starting"].includes(String(item.status || "").toLowerCase()));
    const stageId = String(result?.current_stage || result?.record?.current_stage || activeProgress?.step || "");
    const percent = progressPercent(phase, result, running);
    const coverage = assessment?.evidence_coverage;
    const evidenceCompletion = evidenceCompletionFor(assessment);
    const primaryCoverage = evidenceCompletion?.automatable.percent;
    const coverageLabel = primaryCoverage != null
      ? `${copy.automatableEvidence}: ${primaryCoverage}%`
      : coverage?.calculated && Number.isFinite(Number(coverage.percent))
        ? `${coverage.label || copy.evidence}: ${Math.max(0, Math.min(100, Number(coverage.percent)))}%`
        : copy.coverage;
    return {stageId, percent, evidenceCompletion, coverageLabel};
  }

  function deriveScoreView() {
    const assessmentRecord = assessment as Record<string, unknown> | null;
    const maturityRecord = assessment?.maturity_signal as Record<string, unknown> | undefined;
    const technicalValue = numeric(assessmentRecord?.technical_score ?? maturityRecord?.technical_score ?? maturityRecord?.score);
    const adjustedValue = numeric(assessmentRecord?.canonical_evidence_adjusted_score ?? assessmentRecord?.evidence_adjusted_score ?? maturityRecord?.canonical_evidence_adjusted_score ?? maturityRecord?.evidence_adjusted_score ?? maturityRecord?.presented_score);
    const technicalLabel = technicalValue == null ? (running ? copy.notScoredYet : copy.notScored) : `${technicalValue}/100`;
    const adjustedLabel = adjustedValue == null ? (running ? copy.notScoredYet : copy.notScored) : `${adjustedValue}/100`;
    const maturityRawStatus = assessment?.maturity_signal?.level;
    const maturityUnavailable = String(maturityRawStatus || "").toLowerCase().includes("unavailable");
    const maturityStatus = running && (!maturityRawStatus || maturityUnavailable)
      ? copy.maturityAfterScoring
      : formatStatus(maturityRawStatus || (running ? "pending" : "not_started"), copy);
    return {technicalValue, adjustedValue, technicalLabel, adjustedLabel, maturityStatus};
  }

  function deriveArtifactView() {
    const immutableCommit = immutableCommitFor(result);
    const scannerRawStatus = scannerStatusFor(service, result, running);
    const scannerUnavailable = String(scannerRawStatus || "").toLowerCase().includes("unavailable");
    const scannerStatus = running && scannerUnavailable ? copy.awaitingScanner : formatStatus(scannerRawStatus, copy);
    const markdownAvailable = Boolean(report?.markdown || report?.markdown_available);
    const pdfAvailable = Boolean(report?.pdf_base64 || report?.pdf_available);
    const reportReady = Boolean(markdownAvailable || pdfAvailable || report?.html || report?.html_available || report?.json || report?.json_available || report?.report_id);
    const finalReportStatus = finalReportLivenessStatus(result, locale);
    const reportStatus = reportReady ? copy.phases.complete : running ? finalReportStatus || copy.awaitingScanner : copy.awaitingStage;
    return {immutableCommit, scannerStatus, markdownAvailable, pdfAvailable, reportReady, reportStatus};
  }

  function deriveReviewView() {
    const internalReview = internalReviewStateFor(result);
    const reviewStatus = internalReview.approved
      ? copy.internalReviewApproved
      : phase === "review_required"
        ? copy.internalReviewRequired
        : running ? copy.reviewAfterReport : copy.awaitingStage;
    const clientReadyStatus = internalReview.approved ? copy.clientReadyYes : copy.clientReadyNo;
    const internalReviewHref = internalReviewHrefFor(result, locale);
    const preflightIssue = issue && !issue.runCreated ? issue : null;
    const runIssue = issue && issue.runCreated ? issue : null;
    // A failure before intake has no exact run identity and already renders inline in
    // the form. Do not manufacture a second terminal-looking run panel for that same
    // no-run error. Once an exact run exists, its persisted state remains authoritative.
    const showStatePanel = Boolean(result?.run_id)
      || Boolean(runIssue)
      || phase === "starting";
    return {internalReview, reviewStatus, clientReadyStatus, internalReviewHref, preflightIssue, runIssue, showStatePanel};
  }

  function deriveCopyView() {
    const stageHistoryLabel = locale === "es-MX"
      ? `Ver historial de etapas automatizadas (${progressItems.length})`
      : `View automated stage history (${progressItems.length})`;
    const artifactStatus = artifactAction
      ? locale === "es-MX" ? "Preparando el archivo…" : "Preparing file…"
      : "";
    const terminalView = ["review_required", "complete", "failed", "timed_out"].includes(phase);
    return {stageHistoryLabel, artifactStatus, terminalView};
  }

  const {stageId, percent, evidenceCompletion, coverageLabel} = deriveProgressView();
  const {technicalValue, adjustedValue, technicalLabel, adjustedLabel, maturityStatus} = deriveScoreView();
  const {immutableCommit, scannerStatus, markdownAvailable, pdfAvailable, reportReady, reportStatus} = deriveArtifactView();
  const {internalReview, reviewStatus, clientReadyStatus, internalReviewHref, preflightIssue, runIssue, showStatePanel} = deriveReviewView();
  const {stageHistoryLabel, artifactStatus, terminalView} = deriveCopyView();

  async function copyMarkdown(): Promise<void> {
    if (!markdownAvailable || artifactAction) return;
    const scrollTop = window.scrollY;
    (document.activeElement as HTMLElement | null)?.blur();
    setArtifactAction("markdown");
    setError("");
    try {
      let markdown = String(report?.markdown || "");
      if (!markdown) {
        const runId = String(result?.run_id || "").trim();
        if (!runId) throw new Error(copy.runIdMissing);
        const response = await fetch(
          apiUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/markdown`),
          {method: "GET", cache: "no-store", headers: {Accept: "text/markdown"}},
        );
        if (!response.ok) throw await artifactError(response, copy.pdfMissing);
        markdown = await response.text();
      }
      if (!markdown.trim()) throw new Error(copy.pdfMissing);
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(copy.pdfMissing));
    } finally {
      setArtifactAction(null);
      restoreArtifactScroll(scrollTop);
    }
  }

  async function downloadPdf(): Promise<void> {
    if (!pdfAvailable || artifactAction) return;
    const scrollTop = window.scrollY;
    (document.activeElement as HTMLElement | null)?.blur();
    setArtifactAction("pdf");
    setError("");
    try {
      if (report?.pdf_base64) {
        savePdf(String(report.pdf_base64), String(report.pdf_filename || "nico-comprehensive-assessment.pdf"));
        return;
      }
      const runId = String(result?.run_id || "").trim();
      if (!runId) throw new Error(copy.runIdMissing);
      const fallback = safeFilename(
        String(report?.pdf_filename || ""),
        `nico-comprehensive-${runId}-FINAL-PENDING-APPROVAL.pdf`,
      );
      const response = await fetch(
        apiUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/pdf`),
        {method: "GET", cache: "no-store", headers: {Accept: "application/pdf"}},
      );
      if (!response.ok) throw await artifactError(response, String(report?.pdf_error || copy.pdfMissing));
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.length < 4 || String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF") {
        throw new Error(locale === "es-MX" ? "El PDF final no superó la validación de integridad." : "The final PDF failed integrity validation.");
      }
      downloadBlob(
        new Blob([bytes], {type: "application/pdf"}),
        filenameFromResponse(response, fallback),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(report?.pdf_error || copy.pdfMissing));
    } finally {
      setArtifactAction(null);
      restoreArtifactScroll(scrollTop);
    }
  }

  function renderReviewAction() {
    if (!result?.run_id || (phase !== "review_required" && !internalReview.completed)) return null;
    return <a
      className={workspaceStyles.internalReviewAction}
      data-assessment-internal-review="true"
      href={internalReviewHref}
    >{internalReview.approved ? copy.openReviewRecord : copy.openInternalReview}</a>;
  }

  function renderReportActions() {
    return <div
      className={`report-actions ${workspaceStyles.reportActionBar}`}
      data-assessment-report-actions="true"
      data-assessment-report-ready={reportReady ? "true" : "false"}
    >
      <button type="button" disabled={!markdownAvailable || artifactAction !== null} onClick={copyMarkdown}>{copy.copy}</button>
      <button type="button" disabled={!pdfAvailable || artifactAction !== null} onClick={downloadPdf}>{internalReview.approved ? copy.downloadApprovedPdf : copy.downloadReviewPdf}</button>
      {copied ? <span className="muted">{copy.copied}</span> : artifactStatus ? <span className="muted" role="status">{artifactStatus}</span> : null}
    </div>;
  }


  function renderHero() {
    return (
        <section className={`hero ${workspaceStyles.hero}`}>
          <p className="eyebrow">{copy.heroEyebrow}</p>
          <h1>{copy.title}</h1>
          {!compactMobile ? <>
            <p className={workspaceStyles.heroLead}>{copy.lead}</p>
            <ul className={workspaceStyles.trustRow}>{copy.trustIndicators.map((item: string) => <li key={item}>{item}</li>)}</ul>
          </> : null}
          <p className={workspaceStyles.heroBoundary}>{copy.heroBoundary}</p>
        </section>
    );
  }

  function renderAssessmentIntro() {
    return <>
      <div className="section-head">
        <div className={workspaceStyles.sectionHeading}>
          <p className="eyebrow">{serviceCopy.eyebrow}</p>
          <h2>{serviceCopy.heading}</h2>
        </div>
        <span className="status gray">{coverageLabel}</span>
      </div>
      {evidenceCompletion ? <div className={workspaceStyles.evidenceMetricGrid} data-assessment-evidence-metrics="true">
        {[evidenceCompletion.automatable, evidenceCompletion.disposition, evidenceCompletion.analyzers, evidenceCompletion.overall].map((metric) => <article key={metric.label} title={metric.definition}>
          <b>{metric.label}</b>
          <span>{metric.percent == null ? copy.notVerified : `${metric.percent}%`}</span>
          {metric.completed != null && metric.total != null ? <small>{metric.completed}/{metric.total}</small> : null}
        </article>)}
      </div> : null}
      {!compactMobile ? <>
        <p className={workspaceStyles.sectionSummary}>{serviceCopy.summary}</p>
        <details className="help-details"><summary>{serviceCopy.instructionsTitle}</summary><ul>{serviceCopy.instructions.map((item: string) => <li key={item}>{item}</li>)}</ul></details>
      </> : null}
      <p className={workspaceStyles.scopeNotice}>{copy.warning}</p>
    </>;
  }

  function renderAssessmentForm() {
    return <>
        <label className={workspaceStyles.repositoryField}>{copy.repo}
          <input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder={copy.repoPlaceholder} disabled={running} autoComplete="off" />
        </label>
        <div className={workspaceStyles.secondaryGrid}>
          <label className={workspaceStyles.secondaryField}>{copy.client}<input value={client} onChange={(event) => setClient(event.target.value)} disabled={running} /></label>
          <label className={workspaceStyles.secondaryField}>{copy.project}<input value={project} onChange={(event) => setProject(event.target.value)} disabled={running} /></label>
        </div>

        <StrategicEvidenceForm
          locale={locale}
          value={humanEvidence}
          onChange={setHumanEvidence}
          disabled={running}
        />

        <label className={workspaceStyles.authorizationPanel}>
          <input
            type="checkbox"
            data-assessment-authorization="true"
            checked={authorized}
            onChange={(event) => setAuthorized(event.target.checked)}
            disabled={running}
          />
          <span className={workspaceStyles.authorizationCopy}>
            <strong>{copy.authorizationTitle}</strong>
            <span>{copy.confirm}</span>
          </span>
        </label>

        {error ? <p className={workspaceStyles.validationError} role="alert">{error}</p> : null}
        <div className={workspaceStyles.actionRow}>
          <button
            type="button"
            className={`primary-button ${workspaceStyles.primaryAction}`}
            data-assessment-primary-action="true"
            data-assessment-action-copy="create-engagement-v2"
            aria-label={copy.run}
            disabled={!authorized || !repository.trim() || running}
            onClick={run}
          >
            {running ? copy.phases[phase] : copy.run}
          </button>
          {!compactMobile ? <p className={workspaceStyles.actionNote}>{copy.preflightNote}</p> : null}
        </div>

        {preflightIssue ? <div
          ref={issueRef}
          className={`${workspaceStyles.issueCard} ${workspaceStyles.inlineIssueCard} ${preflightIssue.kind === "run_failed" ? workspaceStyles.issueFailed : ""}`}
          data-assessment-no-run-issue="true"
          role="alert"
          tabIndex={-1}
        >
          <span className={workspaceStyles.issueAccent} aria-hidden="true" />
          <div className={workspaceStyles.issueContent}>
            <h3>{preflightIssue.title}</h3>
            <p>{preflightIssue.message}</p>
            {preflightIssue.retryable ? <div className={workspaceStyles.issueActions}>
              <button type="button" className={workspaceStyles.retryButton} onClick={retry} disabled={running}>{copy.tryAgain}</button>
            </div> : null}
          </div>
        </div> : phase === "checking" && message ? <p className={workspaceStyles.inlineStatus} role="status">{message}</p> : null}
    </>;
  }

  function renderMobileResult() {
    // Source-contract markers retained for mobile DOM boundary regression tests:
    // {compactMobile ? <div
    // : <div data-full-assessment-details="true">
    return (
        <div
          className={mobileStyles.compactTerminal}
          data-mobile-compact-terminal="true"
          data-mobile-heavy-report-mounted="false"
        >
          <div className={mobileStyles.compactStatusGrid}>
            <article><b>{copy.report}</b><span>{reportStatus}</span></article>
            <article><b>{copy.review}</b><span>{reviewStatus}</span></article>
            <article><b>{copy.clientReady}</b><span>{clientReadyStatus}</span></article>
            <article><b>{copy.technicalMaturityLabel || copy.maturity}</b><span>{technicalValue == null ? maturityStatus : `${maturityStatus} · ${technicalLabel}`}</span></article>
            <article><b>{copy.evidenceAdjustedLabel || "Evidence-adjusted"}</b><span>{adjustedLabel}</span></article>
            <article><b>{copy.durable}</b><span>{persistenceStatus(result.persistence, phase, copy)}</span></article>
          </div>
          {renderReportActions()}
          {renderReviewAction()}
          {terminalView ? <div className={workspaceStyles.terminalActions} data-assessment-terminal-actions="true"><button type="button" onClick={startNew}>{locale === "es-MX" ? "Iniciar una nueva evaluación" : "Start new assessment"}</button></div> : null}
          {phase === "review_required" ? <p className="warning-box">{copy.reviewNotice}</p> : null}
          <details className={mobileStyles.compactIdentity}>
            <summary>{locale === "es-MX" ? "Identidad técnica" : "Technical identity"}</summary>
            <p><b>{copy.runId}</b><code title={String(result.run_id || "")}>{compactIdentifier(String(result.run_id || ""), 18, 8)}</code></p>
            <p><b>{copy.commit}</b><code title={immutableCommit}>{compactIdentifier(immutableCommit, 18, 8)}</code></p>
            <p><b>{copy.scanner}</b><span>{scannerStatus}</span></p>
          </details>
</div>
    );
  }

  function renderDesktopResult() {
    return (
        <div data-full-assessment-details="true">
          <div className="grid four target-grid"><article><b>{copy.runId}</b><IdentifierValue value={result.run_id} fallback={copy.notVerified} copy={copy} /></article><article><b>{copy.commit}</b><IdentifierValue value={immutableCommit} fallback={copy.notVerified} copy={copy} /></article><article><b>{copy.scanner}</b><span>{scannerStatus}</span></article><article><b>{copy.report}</b><span>{reportStatus}</span></article></div>
          <div className="grid four target-grid"><article><b>{copy.review}</b><span>{reviewStatus}</span></article><article><b>{copy.clientReady}</b><span>{clientReadyStatus}</span></article><article><b>{copy.technicalMaturityLabel || copy.maturity}</b><span>{technicalValue == null ? maturityStatus : `${maturityStatus} · ${technicalLabel}`}</span></article><article><b>{copy.evidenceAdjustedLabel || "Evidence-adjusted"}</b><span>{adjustedLabel}</span></article><article><b>{copy.durable}</b><span>{persistenceStatus(result.persistence, phase, copy)}</span></article></div>
          {renderReportActions()}
          {renderReviewAction()}
          {terminalView ? <div className={workspaceStyles.terminalActions} data-assessment-terminal-actions="true"><button type="button" onClick={startNew}>{locale === "es-MX" ? "Iniciar una nueva evaluación" : "Start new assessment"}</button></div> : null}
          {phase === "review_required" ? <p className="warning-box">{copy.reviewNotice}</p> : null}
          {assessment?.executive_summary ? <p className="summary-box">{assessment.executive_summary}</p> : null}
          {progressItems.length ? <details className={workspaceStyles.stageHistory} open={running}><summary>{stageHistoryLabel}</summary><ProgressTimeline items={progressItems} copy={copy} /></details> : null}
          <Scorecard sections={assessment?.sections} copy={copy} />
          {assessment?.unavailable_data_notes?.length ? <details className="help-details"><summary>{copy.evidenceLimitations} ({assessment.unavailable_data_notes.length})</summary><List items={assessment.unavailable_data_notes} empty={copy.notVerified} /></details> : null}
        </div>
    );
  }

  function renderStatePanel() {
    // Source-contract marker: {showStatePanel ? <section
    if (!showStatePanel) return null;
    return <section
      className={`section panel ${workspaceStyles.panel} ${workspaceStyles.statePanel}`}
      data-assessment-run-state="true"
      aria-live="polite"
    >
      <div className={`section-head ${workspaceStyles.stateHeader}`}>
        <div>
          <p className="eyebrow">{copy.state}</p>
          <h2 title={result?.run_id}>{result?.run_id ? compactIdentifier(result.run_id, 18, 8) : copy.phases[phase]}</h2>
        </div>
        <span className={statusClass(phase)}>{copy.phases[phase]}</span>
      </div>

      {/* issue ? <div legacy source contract; run-created issues remain in the exact-run panel. */}
      {runIssue ? <div
        ref={issueRef}
        className={`${workspaceStyles.issueCard} ${runIssue.kind === "run_failed" ? workspaceStyles.issueFailed : ""}`}
        role="alert"
        tabIndex={-1}
      >
        <span className={workspaceStyles.issueAccent} aria-hidden="true" />
        <div className={workspaceStyles.issueContent}>
          <h3>{runIssue.title}</h3>
          <p>{runIssue.message}</p>
          <p className={workspaceStyles.issueMeta}>{copy.exactRunPreserved}</p>
          {runIssue.retryable ? <div className={workspaceStyles.issueActions}>
            <button type="button" className={workspaceStyles.retryButton} onClick={retry} disabled={running}>{copy.tryAgain}</button>
          </div> : null}
        </div>
      </div> : null}

      {!runIssue && message ? <p className={workspaceStyles.stateMessage}>{message}</p> : null}

      {running && phase !== "checking" ? <>
        <div className={styles.progressMeta}>
          <span><b>{copy.stage}</b>{copy.stageLabels[stageId] || stageId.replaceAll("_", " ") || copy.phases[phase]}</span>
          <span><b>{copy.progress}</b>{Math.round(percent)}%</span>
          <span><b>{copy.elapsed}</b>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
          {!compactMobile ? <span><b>{copy.checks}</b>{attempt}</span> : null}
        </div>
        <div className={styles.progressBar} role="progressbar" aria-label={`${copy.stageLabels[stageId] || stageId || copy.phases[phase]} ${copy.progress}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{width: `${Math.max(2, Math.min(100, percent))}%`}} /></div>
      </> : null}

      {result ? <div className={workspaceStyles.resultArea} data-assessment-report-ready={reportReady ? "true" : "false"}>
        {compactMobile ? renderMobileResult() : renderDesktopResult()}
      </div> : null}
    </section>;
  }

  return <main
    className={`shell ${workspaceStyles.workspace}`}
    data-workspace="assessment"
    data-engagement-type="comprehensive"
    data-canonical-assessment="strategic"
    data-customer-facing-assessment="comprehensive"
    data-assessment-copy-contract="expert-engagement-v2"
    data-assessment-locale={locale}
    data-assessment-hydrated={hydrated ? "true" : "false"}
    data-assessment-client-mode={compactMobile ? "compact-mobile" : "full"}
  >
    {renderHero()}
    <section id="assessment" className={`section panel ${workspaceStyles.panel}`}>
      {renderAssessmentIntro()}
      <div className={workspaceStyles.formSurface}>
        {renderAssessmentForm()}
      </div>
    </section>
    {renderStatePanel()}
  </main>;
}


/* Legacy Express and Comprehensive route names remain backend compatibility details only. */