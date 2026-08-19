"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./operations.module.css";

type ComprehensiveProjection = {
  run_id?: string;
  repository?: string;
  commit_sha?: string;
  status?: string;
  current_stage?: string;
  progress_percent?: number;
  terminal?: boolean;
  human_review_required?: boolean;
  client_delivery_allowed?: boolean;
  record?: {
    current_stage?: string;
    stage_results?: Record<string, Record<string, unknown>>;
  };
};

type Props = {
  apiUrl: string;
  refreshKey: string;
  targetRunId: string;
  returnPath?: string;
};

function detailMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return fallback;
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const nested = detail as Record<string, unknown>;
    const message = String(nested.message || nested.code || "").trim();
    if (message) return message;
  }
  return String(record.message || record.error || fallback);
}

function runStage(run: ComprehensiveProjection | null): string {
  return String(run?.current_stage || run?.record?.current_stage || "unknown").trim();
}

function failureReason(run: ComprehensiveProjection | null): string {
  if (!run?.record?.stage_results) return "Unavailable";
  const stage = runStage(run);
  const result = run.record.stage_results[stage];
  if (!result || typeof result !== "object") return "Unavailable";
  return String(
    result.technical_reason
      || result.reason
      || result.error
      || result.message
      || "Unavailable",
  );
}

function recoverable(run: ComprehensiveProjection | null): boolean {
  if (!run?.terminal) return false;
  return ["blocked", "failed", "error", "interrupted"].includes(
    String(run.status || "").trim().toLowerCase(),
  );
}

export default function ComprehensiveRecoveryPanel({
  apiUrl,
  refreshKey,
  targetRunId,
  returnPath = "/assessment",
}: Props) {
  const [run, setRun] = useState<ComprehensiveProjection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const stage = useMemo(() => runStage(run), [run]);
  const reason = useMemo(() => failureReason(run), [run]);

  async function loadExactRun(): Promise<ComprehensiveProjection | null> {
    if (!apiUrl || !targetRunId) return null;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}`,
        {
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "Cache-Control": "no-store",
          },
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(detailMessage(payload, `Comprehensive recovery lookup failed (${response.status}).`));
      }
      const exact = payload as ComprehensiveProjection;
      if (String(exact.run_id || "") !== targetRunId) {
        throw new Error("The recovery lookup returned a different Comprehensive run identity.");
      }
      setRun(exact);
      return exact;
    } catch (requestError) {
      setRun(null);
      setError(requestError instanceof Error ? requestError.message : "Comprehensive recovery lookup failed.");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function resumeExactRun() {
    if (!apiUrl || !targetRunId || !recoverable(run)) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}/continue`,
        {
          method: "POST",
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
          },
          body: JSON.stringify({max_stages: 1}),
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(detailMessage(payload, `Comprehensive recovery failed (${response.status}).`));
      }
      const recovered = payload as ComprehensiveProjection;
      if (String(recovered.run_id || "") !== targetRunId) {
        throw new Error("Comprehensive recovery changed the exact run identity.");
      }
      setRun(recovered);
      if (
        recovered.terminal === true
        && ["blocked", "failed", "error", "interrupted"].includes(
          String(recovered.status || "").trim().toLowerCase(),
        )
      ) {
        throw new Error(
          `The exact run remained blocked at ${runStage(recovered)}. Preserved evidence was not converted into a passing result.`,
        );
      }

      const target = new URL(returnPath, window.location.origin);
      target.searchParams.set("tier", "comprehensive");
      target.searchParams.set("run_id", targetRunId);
      window.location.assign(`${target.pathname}${target.search}${target.hash}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Comprehensive recovery failed.");
      setLoading(false);
    }
  }

  useEffect(() => {
    if (refreshKey && targetRunId) void loadExactRun();
  }, [refreshKey]);

  return (
    <section className={styles.panel} data-comprehensive-recovery="true">
      <div className={styles.sectionHead}>
        <div>
          <p className={styles.eyebrow}>Comprehensive recovery</p>
          <h2>Resume the preserved exact Comprehensive run</h2>
        </div>
        <span className={`${styles.pill} ${recoverable(run) ? styles.warn : run ? styles.good : styles.neutral}`}>
          {run?.status || "not loaded"}
        </span>
      </div>

      <div className={styles.nextAction}>
        <b>Exact run identity</b>
        <p>{targetRunId}. This control never creates a replacement run. It re-enters the same public exact-run continuation boundary used by the assessment workspace and preserves the durable record.</p>
      </div>

      <div className={styles.gridFour}>
        <article className={styles.detailCard}><span>Current stage</span><b>{run ? stage.replaceAll("_", " ") : "Not loaded"}</b><small>The failed stage remains authoritative until recovery succeeds.</small></article>
        <article className={styles.detailCard}><span>Progress</span><b>{run && Number.isFinite(Number(run.progress_percent)) ? `${Number(run.progress_percent).toFixed(2)}%` : "Not loaded"}</b><small>Recovery does not fabricate completed work.</small></article>
        <article className={styles.detailCard}><span>Repository</span><b>{run?.repository || "Not loaded"}</b><small>{run?.commit_sha ? `Exact commit ${run.commit_sha.slice(0, 12)}` : "Exact commit not loaded"}</small></article>
        <article className={styles.detailCard}><span>Client delivery</span><b>{run?.client_delivery_allowed === true ? "Allowed" : "Blocked"}</b><small>Human review remains required.</small></article>
      </div>

      {run ? <div className={styles.nextAction}>
        <b>Preserved failure reason</b>
        <p>{reason}</p>
      </div> : null}

      {error ? <div className={styles.error}>{error}</div> : null}

      <div className={styles.filters}>
        <button type="button" onClick={() => void loadExactRun()} disabled={loading}>
          {loading ? "Working..." : "Reload exact run state"}
        </button>
        <div />
        <button type="button" onClick={() => void resumeExactRun()} disabled={loading || !recoverable(run)}>
          Resume same Comprehensive run ID
        </button>
      </div>

      <p className={styles.helper}>No operator token is required for this bounded Comprehensive recovery because it uses the existing public exact-run status and continuation routes. Human review and client delivery remain fail closed. The first recovery continuation is limited to one stage; a repeated terminal failure remains blocked and visible.</p>
    </section>
  );
}
