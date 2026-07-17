"use client";

import {useEffect} from "react";
import {isTerminalRun, reconcileRunSnapshot, truthGateHasStalled, type RunSnapshot} from "./assessment/runState";

const STATUS_PATH = /\/assessment\/(express|mid|full)-run\/[^/]+\/status(?:\?|$)/;
const TRUTH_GATE_TIMEOUT_MS = 5 * 60 * 1000;

type GuardedSnapshot = RunSnapshot & {
  blocking_gate?: string;
  terminal_reason?: string;
  last_successful_checkpoint?: string;
  human_review_required?: boolean;
};

type Watermark = {
  snapshot: GuardedSnapshot;
  fingerprint: string;
  unchangedSince: number;
};

function fingerprint(snapshot: GuardedSnapshot): string {
  const progress = Number(snapshot.progress_percent);
  return JSON.stringify({
    status: String(snapshot.status || ""),
    stage: String(snapshot.current_stage || ""),
    progress: Number.isFinite(progress) ? progress : null,
    steps: (snapshot.progress || []).map((item) => [item.step, item.status]),
  });
}

function lastSuccessfulCheckpoint(snapshot: GuardedSnapshot): string {
  const completed = [...(snapshot.progress || [])]
    .reverse()
    .find((item) => ["complete", "completed", "passed", "verified", "attached"].includes(String(item.status || "").toLowerCase()));
  return String(completed?.step || snapshot.current_stage || "request_accepted");
}

function terminalizeTruthGate(snapshot: GuardedSnapshot): GuardedSnapshot {
  return {
    ...snapshot,
    status: "blocked",
    current_stage: "truth_and_review_gates",
    progress_percent: Math.max(96, Number(snapshot.progress_percent) || 96),
    blocking_gate: "truth_and_review_gates_timeout",
    terminal_reason: "Truth and review gates did not reach a terminal decision within five minutes. The run was stopped to prevent indefinite polling and requires recovery review.",
    last_successful_checkpoint: lastSuccessfulCheckpoint(snapshot),
    human_review_required: true,
    updated_at: new Date().toISOString(),
  };
}

export default function AssessmentRunStateGuard() {
  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const watermarks = new Map<string, Watermark>();

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await originalFetch(input, init);
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (!STATUS_PATH.test(url) || !response.ok) return response;

      let incoming: GuardedSnapshot;
      try {
        incoming = await response.clone().json() as GuardedSnapshot;
      } catch {
        return response;
      }

      const runId = String(incoming.run_id || "");
      if (!runId) return response;

      const previous = watermarks.get(runId);
      let reconciled = reconcileRunSnapshot(previous?.snapshot || null, incoming) as GuardedSnapshot;
      const nextFingerprint = fingerprint(reconciled);
      const now = Date.now();
      const unchangedSince = previous && previous.fingerprint === nextFingerprint ? previous.unchangedSince : now;

      if (!isTerminalRun(reconciled) && truthGateHasStalled(reconciled, unchangedSince, now, TRUTH_GATE_TIMEOUT_MS)) {
        reconciled = terminalizeTruthGate(reconciled);
      }

      watermarks.set(runId, {
        snapshot: reconciled,
        fingerprint: fingerprint(reconciled),
        unchangedSince,
      });

      return new Response(JSON.stringify(reconciled), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    };

    return () => {
      window.fetch = originalFetch;
      watermarks.clear();
    };
  }, []);

  return null;
}
