"use client";

import type {Decision, ReviewResponse, Service} from "./finalReviewModel";
import {compactRunId, humanStatus} from "./finalReviewModel";
import styles from "./final-review.module.css";

type Props = {
  service: Service;
  runId: string;
  rawStatus: string;
  deliveryAllowed: boolean;
  confirmed: boolean;
  note: string;
  loading: boolean;
  result: ReviewResponse;
  onConfirmedChange: (value: boolean) => void;
  onNoteChange: (value: string) => void;
  onApproveAndDownload: () => void;
  onDownloadApprovedPdf: () => void;
  onOtherDecision: (state: Decision) => void;
  onChooseAnotherReport: () => void;
};

export default function FinalReviewDecision({
  service,
  runId,
  rawStatus,
  deliveryAllowed,
  confirmed,
  note,
  loading,
  result,
  onConfirmedChange,
  onNoteChange,
  onApproveAndDownload,
  onDownloadApprovedPdf,
  onOtherDecision,
  onChooseAnotherReport,
}: Props) {
  const serviceLabel = service === "comprehensive" ? "Comprehensive assessment" : "Express assessment";

  return <>
    <header className={styles.panelHeader}>
      <div>
        <p className={styles.sectionLabel}>STEP 2 OF 2</p>
        <h2>Approve and receive the final report</h2>
        <p>Confirm the exact package, then approve and download it in one controlled action.</p>
      </div>
      <span className={deliveryAllowed ? styles.approvedBadge : styles.reviewBadge}>
        {deliveryAllowed ? "Approved" : "Review ready"}
      </span>
    </header>

    <div className={styles.reviewIdentity}>
      <div>
        <span>{serviceLabel}</span>
        <code title={runId.trim()}>{compactRunId(runId)}</code>
      </div>
      <button type="button" className={styles.textButton} onClick={onChooseAnotherReport}>
        Change report
      </button>
    </div>

    <div className={styles.statusGrid}>
      <article className={styles.statusCard}>
        <span>Review status</span>
        <strong>{humanStatus(rawStatus)}</strong>
      </article>
      <article className={`${styles.statusCard} ${deliveryAllowed ? styles.statusGood : styles.statusLocked}`}>
        <span>Client delivery</span>
        <strong>{deliveryAllowed ? "Authorized" : "Blocked"}</strong>
      </article>
    </div>

    <label className={styles.confirmCard}>
      <input
        type="checkbox"
        checked={confirmed}
        onChange={(event) => onConfirmedChange(event.target.checked)}
      />
      <span>
        <strong>I reviewed the exact report, scorecard, evidence limitations, and delivery boundary for this run.</strong>
        <small>This confirmation is recorded with the approval decision.</small>
      </span>
    </label>

    <details className={styles.secondaryDetails}>
      <summary>Add a note or choose another decision</summary>
      <div className={styles.secondaryBody}>
        <label>Review note
          <textarea
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="Optional approval context. Required only for other decisions."
          />
        </label>
        <div className={styles.decisionActions}>
          <button
            type="button"
            disabled={loading}
            onClick={() => onOtherDecision("needs_more_evidence")}
          >
            Request more evidence
          </button>
          <button
            className={styles.reject}
            type="button"
            disabled={loading}
            onClick={() => onOtherDecision("rejected")}
          >
            Reject delivery
          </button>
        </div>
      </div>
    </details>

    <div className={styles.actionBar}>
      {deliveryAllowed
        ? <button className={styles.approve} type="button" disabled={loading} onClick={onDownloadApprovedPdf}>
          <span>Download approved final PDF</span><span aria-hidden="true">↓</span>
        </button>
        : <button className={styles.approve} type="button" disabled={!confirmed || loading} onClick={onApproveAndDownload}>
          <span>{loading ? "Recording approval…" : "Approve and download final report"}</span>
          <span aria-hidden="true">✓</span>
        </button>}
      <div className={deliveryAllowed ? styles.deliveryReady : styles.deliveryBlocked}>
        <span aria-hidden="true">{deliveryAllowed ? "✓" : "⌁"}</span>
        <span>{deliveryAllowed
          ? "Approval is recorded for this exact run and the accepted report is available."
          : "Delivery stays locked until this exact package is approved."}</span>
      </div>
    </div>

    <details className={styles.record}>
      <summary>Exact review record</summary>
      <pre className={styles.code}>{JSON.stringify(result, null, 2)}</pre>
    </details>
  </>;
}
