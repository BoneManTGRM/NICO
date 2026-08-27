"use client";

import {useEffect, useRef, useState} from "react";
import {copyFor} from "./assessmentCopy";
import {AssessmentApiError, scopeId, terminal, wait} from "./assessmentModel";
import {preserveRunIdentity, type RunIdentityFallback} from "./assessmentRunIdentity";
import {
  clearPersistedRun,
  readPersistedRun,
  writePersistedRun,
  type PersistedRun,
} from "./assessmentRunPersistence";
import {
  issueFor,
  requestWithRetry,
  type AssessmentRunIssue,
} from "./assessmentRunRequests";
import {
  compactStrategicHumanEvidence,
  type StrategicHumanEvidenceInput,
} from "./strategicEvidence";
import {
  MAX_POLL_ATTEMPTS,
  POLL_INTERVAL_MS,
  type Locale,
  type Phase,
  type Result,
  type Scope,
  type Service,
} from "./assessmentTypes";

export type {AssessmentRunIssue} from "./assessmentRunRequests";

export type AssessmentRunController = {
  service: Service;
  repository: string;
  client: string;
  project: string;
  authorized: boolean;
  humanEvidence: StrategicHumanEvidenceInput;
  phase: Phase;
  result: Result | null;
  message: string;
  error: string;
  issue: AssessmentRunIssue | null;
  attempt: number;
  elapsed: number;
  running: boolean;
  setRepository: (value: string) => void;
  setClient: (value: string) => void;
  setProject: (value: string) => void;
  setAuthorized: (value: boolean) => void;
  setHumanEvidence: (value: StrategicHumanEvidenceInput) => void;
  setError: (value: string) => void;
  run: () => Promise<void>;
  retry: () => Promise<void>;
  startNew: () => void;
};

function exactRunId(value: Result | null | undefined): string {
  return String(
    value?.run_id || value?.record?.identity?.run_id || "",
  ).trim();
}

function urlBoundRunId(url: URL): string {
  const candidate = String(url.searchParams.get("run_id") || "").trim();
  return candidate.startsWith("comprun_") ? candidate : "";
}

function canonicalProgress(value: Result | null | undefined): number | null {
  const raw = value?.progress_percent ?? value?.record?.progress_percent;
  const numeric = Number(raw);
  return Number.isFinite(numeric)
    ? Math.max(0, Math.min(100, numeric))
    : null;
}

function canonicalStage(value: Result | null | undefined): string {
  return String(
    value?.current_stage || value?.record?.current_stage || "",
  ).trim();
}

function preferMonotonicVisibleResult(
  previous: Result | null,
  incoming: Result,
  service: Service,
): Result {
  if (!previous) {
    return incoming;
  }
  const previousRunId = exactRunId(previous);
  const incomingRunId = exactRunId(incoming);
  if (!previousRunId || !incomingRunId || previousRunId !== incomingRunId) {
    return incoming;
  }

  const previousTerminal = terminal(service, previous);
  const incomingTerminal = terminal(service, incoming);
  if (incomingTerminal) {
    return incoming;
  }
  if (previousTerminal) {
    return previous;
  }

  const previousProgress = canonicalProgress(previous);
  const incomingProgress = canonicalProgress(incoming);
  if (
    previousProgress != null &&
    (incomingProgress == null || incomingProgress < previousProgress)
  ) {
    return previous;
  }

  const previousStage = canonicalStage(previous);
  const incomingStage = canonicalStage(incoming);
  if (
    previousStage &&
    !incomingStage &&
    (incomingProgress == null || incomingProgress === previousProgress)
  ) {
    return previous;
  }
  return incoming;
}

export function useAssessmentRun(locale: Locale): AssessmentRunController {
  const copy = copyFor(locale);
  const service: Service = "comprehensive";
  const [repository, setRepository] = useState("");
  const [client, setClient] = useState("");
  const [project, setProject] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [humanEvidence, setHumanEvidence] =
    useState<StrategicHumanEvidenceInput>({});
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [issue, setIssue] = useState<AssessmentRunIssue | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const sequence = useRef(0);
  const bootstrapped = useRef(false);
  const recoveryInFlight = useRef(false);
  const activeContinuationRunId = useRef("");
  const latestResult = useRef<Result | null>(null);

  function publishResult(next: Result | null): Result | null {
    const visible = next
      ? preferMonotonicVisibleResult(latestResult.current, next, service)
      : null;
    latestResult.current = visible;
    setResult(visible);
    return visible;
  }

  useEffect(() => {
    document.documentElement.lang = locale;
    const url = new URL(window.location.href);
    if (url.searchParams.get("tier") !== "comprehensive") {
      url.searchParams.set("tier", "comprehensive");
      window.history.replaceState(
        window.history.state,
        "",
        `${url.pathname}${url.search}${url.hash}`,
      );
    }

    if (!bootstrapped.current) {
      bootstrapped.current = true;
      const boundRunId = urlBoundRunId(url);
      const persisted = readPersistedRun();
      if (boundRunId) {
        // The explicit exact-run URL is authoritative over any shared local active-run
        // pointer. Terminal runs intentionally clear that pointer, so direct reopening
        // must recover from durable backend state rather than silently showing intake.
        if (persisted?.runId === boundRunId) {
          setRepository(persisted.repository);
          setClient(persisted.client);
          setProject(persisted.project);
          setAuthorized(true);
          void resumePersistedRun(persisted);
        } else {
          void resumeUrlBoundRun(boundRunId);
        }
      } else if (persisted) {
        setRepository(persisted.repository);
        setClient(persisted.client);
        setProject(persisted.project);
        setAuthorized(true);
        void resumePersistedRun(persisted);
      }
    }

    const restoreAfterPageResume = () => {
      const resumedUrl = new URL(window.location.href);
      const boundRunId = urlBoundRunId(resumedUrl);
      const visibleRunId = exactRunId(latestResult.current);
      if (boundRunId) {
        if (
          recoveryInFlight.current ||
          activeContinuationRunId.current === boundRunId ||
          visibleRunId === boundRunId
        ) {
          return;
        }
        void resumeUrlBoundRun(boundRunId);
        return;
      }

      const persisted = readPersistedRun();
      if (
        !persisted ||
        recoveryInFlight.current ||
        activeContinuationRunId.current === persisted.runId
      ) {
        return;
      }
      if (visibleRunId && visibleRunId !== persisted.runId) {
        return;
      }
      void resumePersistedRun(persisted);
    };
    window.addEventListener("pageshow", restoreAfterPageResume);
    window.addEventListener("online", restoreAfterPageResume);
    return () => {
      window.removeEventListener("pageshow", restoreAfterPageResume);
      window.removeEventListener("online", restoreAfterPageResume);
      sequence.current += 1;
    };
  }, [locale]);

  useEffect(() => {
    if (!started || !["starting", "running"].includes(phase)) {
      return;
    }
    const update = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [started, phase]);

  const running =
    phase === "checking" || phase === "starting" || phase === "running";

  function currentScope(): Scope {
    return {
      customerId: scopeId("customer", client, "default_customer"),
      projectId: scopeId("project", project, "default_project"),
    };
  }

  function persistedScope(value: PersistedRun): Scope {
    return {
      customerId: value.customerId || "default_customer",
      projectId: value.projectId || "default_project",
    };
  }

  function resultScope(value: Result): Scope {
    return {
      customerId: String(
        value.customer_id || value.record?.identity?.customer_id || "default_customer",
      ),
      projectId: String(
        value.project_id || value.record?.identity?.project_id || "default_project",
      ),
    };
  }

  function persistExactRun(
    runResult: Result,
    scope: Scope,
    startedAt: number,
  ): void {
    const runId = exactRunId(runResult);
    if (!runId) {
      return;
    }
    writePersistedRun({
      version: 1,
      runId,
      repository: String(runResult.repository || repository || ""),
      client,
      project,
      customerId: String(
        runResult.customer_id || scope.customerId || "default_customer",
      ),
      projectId: String(
        runResult.project_id || scope.projectId || "default_project",
      ),
      startedAt,
      locale,
    });
  }

  async function verifyRuntimePersistence(): Promise<void> {
    const diagnostics = await requestWithRetry(
      "/diagnostics/comprehensive-runtime",
      {method: "GET"},
      copy,
    );
    const replacementSafe =
      diagnostics.survives_container_replacement_verified === true ||
      diagnostics.persistence?.survives_container_replacement_verified === true;
    if (
      String(diagnostics.status || "").toLowerCase() !== "ready" ||
      !replacementSafe
    ) {
      const reason = String(
        diagnostics.reason ||
          "comprehensive_storage_not_container_replacement_safe",
      );
      throw new AssessmentApiError("Assessment persistence is not ready.", {
        status: 503,
        code: reason,
        retryable: true,
      });
    }
  }

  async function recoverRun(
    runId: string,
    fallback: Partial<RunIdentityFallback> = {},
  ): Promise<Result | null> {
    try {
      const recovered = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(runId)}`,
        {method: "GET"},
        copy,
      );
      return preserveRunIdentity(recovered, {
        runId,
        repository: fallback.repository,
        customerId: fallback.customerId,
        projectId: fallback.projectId,
        commitSha: fallback.commitSha,
        evidenceLedgerId: fallback.evidenceLedgerId,
      });
    } catch {
      return null;
    }
  }

  async function continueRun(
    initial: Result,
    scope: Scope,
    token: number,
    startedAt = Date.now(),
  ): Promise<void> {
    let current = preserveRunIdentity(initial, {
      runId: String(initial.run_id || initial.record?.identity?.run_id || ""),
      repository: initial.repository,
      customerId: initial.customer_id || scope.customerId,
      projectId: initial.project_id || scope.projectId,
      commitSha: initial.commit_sha || initial.repository_snapshot?.commit_sha,
      evidenceLedgerId: initial.evidence_ledger_id,
    });
    const continuationRunId = exactRunId(current);
    if (!continuationRunId) {
      throw new AssessmentApiError(copy.runIdMissing, {
        status: 500,
        code: "assessment_run_id_missing",
        retryable: false,
      });
    }
    if (activeContinuationRunId.current === continuationRunId) {
      return;
    }
    activeContinuationRunId.current = continuationRunId;

    try {
      for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1) {
        if (token !== sequence.current) {
          return;
        }
        persistExactRun(current, scope, startedAt);
        publishResult(current);
        const stable = terminal(service, current);
        if (stable) {
          clearPersistedRun(true);
          setPhase(stable);
          setAttempt(count);
          setStarted(null);
          setMessage(
            stable === "review_required" ? copy.comprehensiveReview : copy.stopped,
          );
          return;
        }

        setPhase("running");
        setAttempt(count);
        setError("");
        setIssue(null);
        const currentStageId = String(
          current.current_stage || current.record?.current_stage || "",
        );
        setMessage(
          `${copy.service.label}: ${
            copy.stageLabels[currentStageId] ||
            currentStageId.replaceAll("_", " ") ||
            copy.phases.running
          }.`,
        );
        const runId = exactRunId(current);
        if (!runId) {
          throw new AssessmentApiError(copy.runIdMissing, {
            status: 500,
            code: "assessment_run_id_missing",
            retryable: false,
          });
        }

        try {
          const continued = await requestWithRetry(
            `/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`,
            {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({max_stages: 1}),
            },
            copy,
          );
          current = preserveRunIdentity(continued, {
            runId,
            repository: current.repository,
            customerId: current.customer_id || scope.customerId,
            projectId: current.project_id || scope.projectId,
            commitSha:
              current.commit_sha || current.repository_snapshot?.commit_sha,
            evidenceLedgerId: current.evidence_ledger_id,
          });
        } catch (requestError) {
          const recovered = await recoverRun(runId, {
            repository: current.repository,
            customerId: current.customer_id || scope.customerId,
            projectId: current.project_id || scope.projectId,
            commitSha:
              current.commit_sha || current.repository_snapshot?.commit_sha,
            evidenceLedgerId: current.evidence_ledger_id,
          });
          if (!recovered) {
            throw requestError;
          }
          current = recovered;
          setMessage(`${copy.service.label}: ${copy.recoveredRunState}`);
        }
        await wait(POLL_INTERVAL_MS);
      }
      persistExactRun(current, scope, startedAt);
      publishResult(current);
      setPhase("timed_out");
      setStarted(null);
      setMessage(copy.phases.timed_out);
    } finally {
      if (activeContinuationRunId.current === continuationRunId) {
        activeContinuationRunId.current = "";
      }
    }
  }

  function applyIssue(caught: unknown, runCreated: boolean): void {
    const normalized = issueFor(caught, copy, runCreated);
    setPhase(normalized.kind === "run_failed" ? "failed" : "unavailable");
    setStarted(null);
    setIssue(normalized);
    setError("");
    setMessage("");
  }

  async function resumeUrlBoundRun(runId: string): Promise<void> {
    const boundRunId = String(runId || "").trim();
    if (!boundRunId.startsWith("comprun_")) {
      return;
    }
    const visibleRunId = exactRunId(latestResult.current);
    if (
      recoveryInFlight.current ||
      activeContinuationRunId.current === boundRunId ||
      visibleRunId === boundRunId
    ) {
      return;
    }

    recoveryInFlight.current = true;
    const token = sequence.current + 1;
    sequence.current = token;
    setPhase("checking");
    setIssue(null);
    setError("");
    setMessage(copy.readinessCheckingMessage);
    setStarted(null);
    try {
      const recoveredResponse = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(boundRunId)}`,
        {method: "GET"},
        copy,
      );
      const recovered = preserveRunIdentity(recoveredResponse, {runId: boundRunId});
      if (token !== sequence.current) {
        return;
      }
      setRepository(String(recovered.repository || recovered.record?.identity?.repository || ""));
      publishResult(recovered);
      const stable = terminal(service, recovered);
      if (stable) {
        clearPersistedRun(true);
        setPhase(stable);
        setStarted(null);
        setMessage(
          stable === "review_required" ? copy.comprehensiveReview : copy.stopped,
        );
        return;
      }

      const startedAt = Date.now();
      const scope = resultScope(recovered);
      persistExactRun(recovered, scope, startedAt);
      await continueRun(recovered, scope, token, startedAt);
    } catch (caught) {
      if (token !== sequence.current) {
        return;
      }
      applyIssue(caught, true);
    } finally {
      recoveryInFlight.current = false;
    }
  }

  async function resumePersistedRun(persisted: PersistedRun): Promise<void> {
    const visibleRunId = exactRunId(latestResult.current);
    if (activeContinuationRunId.current === persisted.runId) {
      return;
    }
    if (visibleRunId && visibleRunId !== persisted.runId) {
      return;
    }
    if (recoveryInFlight.current) {
      return;
    }
    recoveryInFlight.current = true;
    const token = sequence.current + 1;
    sequence.current = token;
    const scope = persistedScope(persisted);
    setPhase("checking");
    setIssue(null);
    setError("");
    setMessage(copy.readinessCheckingMessage);
    setStarted(persisted.startedAt);
    try {
      const recoveredResponse = await requestWithRetry(
        `/assessment/comprehensive-run/${encodeURIComponent(persisted.runId)}`,
        {method: "GET"},
        copy,
      );
      const recovered = preserveRunIdentity(recoveredResponse, {
        runId: persisted.runId,
        repository: persisted.repository,
        customerId: persisted.customerId,
        projectId: persisted.projectId,
      });
      if (token !== sequence.current) {
        return;
      }
      persistExactRun(recovered, scope, persisted.startedAt);
      publishResult(recovered);
      const stable = terminal(service, recovered);
      if (stable) {
        clearPersistedRun(true);
        setPhase(stable);
        setStarted(null);
        setMessage(
          stable === "review_required" ? copy.comprehensiveReview : copy.stopped,
        );
        return;
      }
      await continueRun(recovered, scope, token, persisted.startedAt);
    } catch (caught) {
      if (token !== sequence.current) {
        return;
      }
      applyIssue(caught, true);
    } finally {
      recoveryInFlight.current = false;
    }
  }

  async function run(): Promise<void> {
    clearPersistedRun(false);
    if (!authorized) {
      setError(copy.authError);
      setIssue(null);
      return;
    }
    const token = sequence.current + 1;
    sequence.current = token;
    const scope = currentScope();
    setPhase("checking");
    publishResult(null);
    setError("");
    setIssue(null);
    setMessage(copy.readinessCheckingMessage);
    setAttempt(0);
    setStarted(null);
    setElapsed(0);

    const body = {
      repository,
      customer_id: scope.customerId,
      project_id: scope.projectId,
      client_name: client,
      project_name: project,
      authorized_by: "public_assessment_requester",
      authorization_scope: "authorized defensive repository assessment",
      authorization_confirmed: true,
      authorized: true,
      timeframe_days: 180,
      assessment_depth: "strategic",
      report_language: locale,
      human_evidence: compactStrategicHumanEvidence(humanEvidence),
    };

    let acceptedRun: Result | null = null;
    const startedAt = Date.now();
    try {
      await verifyRuntimePersistence();
      if (token !== sequence.current) {
        return;
      }
      setPhase("starting");
      setMessage(`${copy.phases.starting}: ${copy.service.label}`);
      setStarted(startedAt);
      const data = await requestWithRetry(
        "/assessment/comprehensive-intake",
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body),
        },
        copy,
      );
      acceptedRun = data;
      if (token !== sequence.current) {
        return;
      }
      persistExactRun(data, scope, startedAt);
      publishResult(data);
      await continueRun(data, scope, token, startedAt);
    } catch (caught) {
      if (token !== sequence.current) {
        return;
      }
      const runCreated = Boolean(acceptedRun?.run_id);
      applyIssue(caught, runCreated);
      if (acceptedRun) {
        persistExactRun(acceptedRun, scope, startedAt);
        publishResult(acceptedRun);
      }
    }
  }

  function startNew(): void {
    sequence.current += 1;
    recoveryInFlight.current = false;
    activeContinuationRunId.current = "";
    clearPersistedRun(false);
    const url = new URL(window.location.href);
    if (url.searchParams.has("run_id")) {
      url.searchParams.delete("run_id");
      window.history.replaceState(
        window.history.state,
        "",
        `${url.pathname}${url.search}${url.hash}`,
      );
    }
    setRepository("");
    setClient("");
    setProject("");
    setAuthorized(false);
    setHumanEvidence({});
    setPhase("idle");
    publishResult(null);
    setMessage("");
    setError("");
    setIssue(null);
    setAttempt(0);
    setStarted(null);
    setElapsed(0);
    window.requestAnimationFrame(() =>
      window.scrollTo({top: 0, behavior: "auto"}),
    );
  }

  async function retry(): Promise<void> {
    const persisted = readPersistedRun();
    const runId = String(result?.run_id || persisted?.runId || "").trim();
    if (!runId) {
      await run();
      return;
    }
    const scope = currentScope();
    await resumePersistedRun(
      persisted || {
        version: 1,
        runId,
        repository,
        client,
        project,
        customerId: scope.customerId,
        projectId: scope.projectId,
        startedAt: Date.now(),
        locale,
      },
    );
  }

  return {
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
  };
}

/* Compatibility routes remain implementation details: Express, Comprehensive, /assessment/express-run, /assessment/comprehensive-intake. */