"use client";

import {useEffect, useState} from "react";
import {
  ASSESSMENT_FAILURE_EVENT,
  ASSESSMENT_FAILURE_STORAGE_KEY,
  type AssessmentFailureEvidence,
} from "./AssessmentApiTransportBridge";

function isFailureEvidence(value: unknown): value is AssessmentFailureEvidence {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.http_status === "number"
    && typeof record.route === "string"
    && typeof record.code === "string"
    && typeof record.message === "string"
    && Array.isArray(record.progress);
}

export default function AssessmentFailureEvidencePanel() {
  const [failure, setFailure] = useState<AssessmentFailureEvidence | null>(null);

  useEffect(() => {
    if (!window.location.pathname.startsWith("/assessment")) return;

    try {
      const stored = window.sessionStorage.getItem(ASSESSMENT_FAILURE_STORAGE_KEY);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (isFailureEvidence(parsed)) setFailure(parsed);
      }
    } catch {
      // Invalid or unavailable browser storage must not invent failure evidence.
    }

    const handleFailure = (event: Event) => {
      const detail = (event as CustomEvent<AssessmentFailureEvidence | null>).detail;
      setFailure(isFailureEvidence(detail) ? detail : null);
    };
    window.addEventListener(ASSESSMENT_FAILURE_EVENT, handleFailure);
    return () => window.removeEventListener(ASSESSMENT_FAILURE_EVENT, handleFailure);
  }, []);

  if (!failure) return null;

  return <section className="section panel" aria-live="assertive">
    <div className="section-head">
      <div>
        <p className="eyebrow">ASSESSMENT FAILURE EVIDENCE</p>
        <h2>{failure.run_id ? `Run ${failure.run_id} stopped` : "Assessment request stopped before a run ID was returned"}</h2>
      </div>
      <span className="status red">{failure.code}</span>
    </div>
    <p className="error-box">{failure.message}</p>
    <div className="grid four target-grid">
      <article><b>HTTP status</b><span>{failure.http_status}</span></article>
      <article><b>Canonical route</b><span>{failure.route}</span></article>
      <article><b>Assessment type</b><span>{failure.assessment_type || "not returned"}</span></article>
      <article><b>Run identity</b><span>{failure.run_id || "not returned"}</span></article>
    </div>
    {failure.progress.length ? <div className="results-grid">
      {failure.progress.map((item, index) => <article className="result-card" key={`${item.step}-${index}`}>
        <div className="result-head"><b>{item.step.replaceAll("_", " ")}</b><span className={`status ${["failed", "blocked", "error"].includes(item.status.toLowerCase()) ? "red" : "gray"}`}>{item.status}</span></div>
        <p>{item.message}</p>
      </article>)}
    </div> : <p className="warning-box">The backend did not return bounded step evidence for this failure.</p>}
    <p className="warning-box">
      This panel preserves only bounded status evidence. It does not convert the failed or unavailable stage into a passing result.
      {failure.run_id ? <> Review the same run in <a href="/operations/recovery">Recovery</a> before starting a duplicate.</> : null}
    </p>
  </section>;
}
