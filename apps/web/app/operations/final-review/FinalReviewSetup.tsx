"use client";

import type {FormEvent} from "react";

import type {Service} from "./finalReviewModel";
import {compactRunId} from "./finalReviewModel";
import styles from "./final-review.module.css";

type Props = {
  service: Service;
  runId: string;
  customerId: string;
  projectId: string;
  adminToken: string;
  reviewer: string;
  loading: boolean;
  ready: boolean;
  showIdentityEditor: boolean;
  onSubmit: (event: FormEvent) => void;
  onRunIdChange: (value: string) => void;
  onCustomerIdChange: (value: string) => void;
  onProjectIdChange: (value: string) => void;
  onAdminTokenChange: (value: string) => void;
  onReviewerChange: (value: string) => void;
  onIdentityEditorToggle: (open: boolean) => void;
};

export default function FinalReviewSetup({
  service,
  runId,
  customerId,
  projectId,
  adminToken,
  reviewer,
  loading,
  ready,
  showIdentityEditor,
  onSubmit,
  onRunIdChange,
  onCustomerIdChange,
  onProjectIdChange,
  onAdminTokenChange,
  onReviewerChange,
  onIdentityEditorToggle,
}: Props) {
  const serviceLabel = service === "comprehensive" ? "Comprehensive assessment" : "Express assessment";
  const exactRunLabel = runId.trim() ? compactRunId(runId) : "No report selected";

  return <>
    <header className={styles.panelHeader}>
      <div>
        <p className={styles.sectionLabel}>STEP 1 OF 2</p>
        <h2>Open the exact report</h2>
        <p>Run identity is filled automatically from the completed assessment.</p>
      </div>
      <span className={styles.lockBadge}>Read-only</span>
    </header>

    <div className={styles.identityCard}>
      <div className={styles.identityIcon} aria-hidden="true">◎</div>
      <div className={styles.identityCopy}>
        <span>Exact package</span>
        <strong>{serviceLabel}</strong>
        <code title={runId.trim()}>{exactRunLabel}</code>
      </div>
      <span className={runId.trim() ? styles.boundBadge : styles.missingBadge}>
        {runId.trim() ? "Bound" : "Needed"}
      </span>
    </div>

    <form className={styles.form} onSubmit={onSubmit}>
      <div className={styles.fieldGrid}>
        <label>Authorized reviewer
          <input
            value={reviewer}
            onChange={(event) => onReviewerChange(event.target.value)}
            placeholder="Name and role"
            autoComplete="name"
          />
          <small>Name recorded on the immutable approval.</small>
        </label>
        <label>Operator admin token
          <input
            type="password"
            value={adminToken}
            onChange={(event) => onAdminTokenChange(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            autoFocus={Boolean(runId.trim())}
          />
          <small>Used once in this open page and never stored.</small>
        </label>
      </div>

      <details
        className={styles.advanced}
        open={showIdentityEditor || !runId.trim()}
        onToggle={(event) => onIdentityEditorToggle(event.currentTarget.open)}
      >
        <summary>Use another report or advanced scope</summary>
        <div className={styles.advancedGrid}>
          <label className={styles.fullField}>Exact run ID
            <input
              value={runId}
              onChange={(event) => onRunIdChange(event.target.value)}
              placeholder="comprun_… or express_run_…"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
            />
            <small>Assessment type is detected from the run ID.</small>
          </label>
          <label>Customer ID
            <input value={customerId} onChange={(event) => onCustomerIdChange(event.target.value)} />
          </label>
          <label>Project ID
            <input value={projectId} onChange={(event) => onProjectIdChange(event.target.value)} />
          </label>
        </div>
      </details>

      <button className={styles.primary} type="submit" disabled={loading || !ready}>
        <span>{loading ? "Opening report…" : "Open report for review"}</span>
        <span aria-hidden="true">→</span>
      </button>
    </form>

    <p className={styles.securityNote}>
      The report remains unchanged. Approval is bound to this exact run, report package, evidence set, and disclosed limitations.
    </p>
  </>;
}
