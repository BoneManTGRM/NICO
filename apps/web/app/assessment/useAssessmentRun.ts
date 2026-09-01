"use client";

import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {copyFor} from "./assessmentCopy";
import {reportLanguageForRequest} from "./assessmentLocale";
import {AssessmentApiError, scopeId, terminal, wait} from "./assessmentModel";
import {preserveRunIdentity, type RunIdentityFallback} from "./assessmentRunIdentity";
import {
  clearPersistedRun,
  readPersistedRun,
  writePersistedRun,
  type PersistedRun,
} from "./assessmentRunPersistence";
import {
  isAmbiguousIntakeOutcome,
  issueFor,
  requestWithRetry,
  type AssessmentRunIssue,
} from "./assessmentRunRequests";
import {
  compactStrategicHumanEvidence,
  emptyStrategicEvidenceModule,
  type StrategicHumanEvidenceInput,
} from "./strategicEvidence";
import {
  emptyEngagementFieldStates,
  engagementValues,
  isEngagementFieldUnavailable,
  normalizeEngagementFieldStates,
  withEngagementState,
  withEngagementValue,
  type EngagementFieldKey,
  type EngagementFieldState,
  type EngagementFieldStates,
} from "./engagementFieldState";
import {
  isIntakeReservationPending,
  reserveComprehensiveRunId,
} from "./assessmentRecoveryIdentity";
import {
  detectRepositoryProvider,
  normalizeRepositorySelection,
  readRepositoryProvider,
} from "./repositoryProvider";
import {
  MAX_POLL_ATTEMPTS,
  POLL_INTERVAL_MS,
  type Locale,
  type EngagementMetadata,
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
  engagementFieldStates: EngagementFieldStates;
  phase: Phase;
  result: Result | null;
  message: string;
  error: string;
  issue: AssessmentRunIssue | null;
  attempt: number;
  elapsed: number;
  running: boolean;
  protectedRunId: string;
  setRepository: (value: string) => void;
  setClient: (value: string) => void;
  setProject: (value: string) => void;
  setAuthorized: (value: boolean) => void;
  setHumanEvidence: Dispatch<SetStateAction<StrategicHumanEvidenceInput>>;
  setEngagementFieldValue: (field: EngagementFieldKey, value: string) => void;
  setEngagementFieldState: (
    field: EngagementFieldKey,
    state: EngagementFieldState,
  ) => void;
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

function validEngagementMetadata(value: unknown): value is EngagementMetadata {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const metadata = value as Record<string, unknown>;
  return metadata.artifact_schema === "nico.comprehensive_engagement_metadata.v1"
    && /^[a-f0-9]{64}$/.test(String(metadata.engagement_metadata_sha256 || ""))
    && [
      "client_name",
      "project_name",
      "primary_technical_contact",
      "access_method",
      "authorized_scope",
    ].every((field) => typeof metadata[field] === "string");
}

function engagementMetadataFor(value: Result | null | undefined): EngagementMetadata | null {
  const direct = value?.engagement_metadata;
  if (validEngagementMetadata(direct)) return direct;
  const retained = value?.record?.engagement_metadata;
  return validEngagementMetadata(retained) ? retained : null;
}

function engagementEvidence(
  primaryTechnicalContact: string,
  accessMethod: string,
  authorizedScope: string,
): StrategicHumanEvidenceInput {
  if (![primaryTechnicalContact, accessMethod, authorizedScope].some((item) => item.trim())) {
    return {};
  }
  return {
    stakeholder_context: {
      evidence: {
        ...(primaryTechnicalContact.trim() ? {primary_technical_contact: [primaryTechnicalContact]} : {}),
        ...(accessMethod.trim() ? {access_method: [accessMethod]} : {}),
        ...(authorizedScope.trim() ? {authorized_scope: [authorizedScope]} : {}),
      },
      reviewer: "",
      observed_at: "",
      source_reference: "",
      excluded: false,
      exclusion_rationale: "",
    },
  };
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
  const [engagementFieldStates, setEngagementFieldStates] =
    useState<EngagementFieldStates>(emptyEngagementFieldStates);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [issue, setIssue] = useState<AssessmentRunIssue | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [protectedRunId, setProtectedRunId] = useState("");
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
      const persisted = readPersistedRun();
      if (persisted) {
        setProtectedRunId(persisted.runId);
        setRepository(persisted.repository);
        setClient(persisted.client);
        setProject(persisted.project);
        setHumanEvidence(engagementEvidence(
          persisted.primaryTechnicalContact,
          persisted.accessMethod,
          persisted.authorizedScope,
        ));
        setEngagementFieldStates(persisted.engagementFieldStates);
        setAuthorized(true);
        void resumePersistedRun(persisted);
      }
    }

    const restoreAfterPageResume = () => {
      // The exact URL-bound run is authoritative. A different tab may update the
      // shared active-run pointer, but it must never replace this page's run.
      const persisted = readPersistedRun();
      const visibleRunId = exactRunId(latestResult.current);
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
    const restoreAfterForeground = () => {
      if (document.visibilityState === "visible") restoreAfterPageResume();
    };
    document.addEventListener("visibilitychange", restoreAfterForeground);
    return () => {
      window.removeEventListener("pageshow", restoreAfterPageResume);
      window.removeEventListener("online", restoreAfterPageResume);
      document.removeEventListener("visibilitychange", restoreAfterForeground);
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

  function currentEngagementValue(field: EngagementFieldKey): string {
    if (field === "client_name") return client;
    if (field === "project_name") return project;
    const stakeholder = humanEvidence.stakeholder_context?.evidence || {};
    return String(stakeholder[field]?.[0] || "");
  }

  function setEngagementFieldValue(
    field: EngagementFieldKey,
    value: string,
  ): void {
    if (field === "client_name") setClient(value);
    else if (field === "project_name") setProject(value);
    else {
      setHumanEvidence((previous) => {
        const module = previous.stakeholder_context || emptyStrategicEvidenceModule();
        const evidence = {...module.evidence};
        if (value) evidence[field] = [value];
        else delete evidence[field];
        return {
          ...previous,
          stakeholder_context: {...module, evidence},
        };
      });
    }
    setEngagementFieldStates((previous) =>
      withEngagementValue(previous, field, value),
    );
  }

  function setEngagementFieldState(
    field: EngagementFieldKey,
    state: EngagementFieldState,
  ): void {
    const value = currentEngagementValue(field);
    setEngagementFieldStates((previous) =>
      withEngagementState(previous, field, state, value),
    );
    if (!isEngagementFieldUnavailable(state)) return;
    if (field === "client_name") setClient("");
    else if (field === "project_name") setProject("");
    else {
      setHumanEvidence((previous) => {
        const module = previous.stakeholder_context || emptyStrategicEvidenceModule();
        const evidence = {...module.evidence};
        delete evidence[field];
        return {
          ...previous,
          stakeholder_context: {...module, evidence},
        };
      });
    }
  }

  function persistedScope(value: PersistedRun): Scope {
    return {
      customerId: value.customerId || "default_customer",
      projectId: value.projectId || "default_project",
    };
  }

  function persistExactRun(
    runResult: Result,
    scope: Scope,
    startedAt: number,
    exactFallback?: PersistedRun,
  ): void {
    const runId = exactRunId(runResult);
    if (!runId) {
      return;
    }
    setProtectedRunId(runId);
    const engagement = engagementMetadataFor(runResult);
    const stored = exactFallback ?? readPersistedRun();
    const fallback = stored?.runId === runId ? stored : null;
    const stakeholder = humanEvidence.stakeholder_context?.evidence || {};
    const clientValue = engagement?.client_name ?? fallback?.client ?? client;
    const projectValue = engagement?.project_name ?? fallback?.project ?? project;
    const primaryTechnicalContact = engagement?.primary_technical_contact
      ?? fallback?.primaryTechnicalContact
      ?? stakeholder.primary_technical_contact?.[0]
      ?? "";
    const accessMethod = engagement?.access_method
      ?? fallback?.accessMethod
      ?? stakeholder.access_method?.[0]
      ?? "";
    const authorizedScope = engagement?.authorized_scope
      ?? fallback?.authorizedScope
      ?? stakeholder.authorized_scope?.[0]
      ?? "";
    const states = engagement
      ? normalizeEngagementFieldStates(
          engagement.field_states,
          engagementValues(
            clientValue,
            projectValue,
            primaryTechnicalContact,
            accessMethod,
            authorizedScope,
          ),
        )
      : fallback?.engagementFieldStates ?? engagementFieldStates;
    writePersistedRun({
      version: 1,
      runId,
      repository: String(runResult.repository || fallback?.repository || repository || ""),
      client: clientValue,
      project: projectValue,
      primaryTechnicalContact,
      accessMethod,
      authorizedScope,
      engagementFieldStates: states,
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

  function hydrateEngagementMetadata(value: Result): void {
    const engagement = engagementMetadataFor(value);
    if (!engagement) return;
    const clientValue = String(engagement.client_name ?? "");
    const projectValue = String(engagement.project_name ?? "");
    const primaryTechnicalContact = String(engagement.primary_technical_contact ?? "");
    const accessMethod = String(engagement.access_method ?? "");
    const authorizedScope = String(engagement.authorized_scope ?? "");
    setClient(clientValue);
    setProject(projectValue);
    setHumanEvidence(engagementEvidence(
      primaryTechnicalContact,
      accessMethod,
      authorizedScope,
    ));
    setEngagementFieldStates(normalizeEngagementFieldStates(
      engagement.field_states,
      engagementValues(
        clientValue,
        projectValue,
        primaryTechnicalContact,
        accessMethod,
        authorizedScope,
      ),
    ));
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
        hydrateEngagementMetadata(current);
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
            (currentStageId ? copy.unknownStage : "") ||
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
          const intakePending = isIntakeReservationPending(current);
          const continuationPath = intakePending
            ? `/assessment/comprehensive-run/${encodeURIComponent(runId)}`
            : `/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`;
          const continued = await requestWithRetry(
            continuationPath,
            intakePending
              ? {method: "GET"}
              : {
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
      persistExactRun(recovered, scope, persisted.startedAt, persisted);
      hydrateEngagementMetadata(recovered);
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
    if (
      issue &&
      !issue.runCreated &&
      isAmbiguousIntakeOutcome(issue.code)
    ) {
      setError(
        locale === "es-MX"
          ? "El resultado de la solicitud anterior es incierto. Restablece la solicitud antes de iniciar otra evaluación."
          : "The prior intake outcome is unknown. Reset the request before starting another assessment.",
      );
      return;
    }
    if (exactRunId(latestResult.current) || readPersistedRun()?.runId) {
      setError(
        locale === "es-MX"
          ? "La ejecución exacta está protegida. Usa «Iniciar una nueva evaluación» antes de crear otra."
          : "The exact run is protected. Use Start new assessment before creating another.",
      );
      setIssue(null);
      return;
    }
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

    const selectedProvider = detectRepositoryProvider(repository) || readRepositoryProvider();
    let normalizedRepository;
    try {
      normalizedRepository = normalizeRepositorySelection(selectedProvider, repository);
    } catch (caught) {
      setError(
        locale === "es-MX"
          ? "La URL o el identificador del repositorio no coincide con el proveedor seleccionado. Revisa el formato y vuelve a intentarlo."
          : "The repository URL or identifier does not match the selected provider. Check the format and try again.",
      );
      setIssue(null);
      return;
    }
    const reservedRunId = reserveComprehensiveRunId();
    const normalizedStates = normalizeEngagementFieldStates(
      engagementFieldStates,
      engagementValues(
        client,
        project,
        humanEvidence.stakeholder_context?.evidence.primary_technical_contact?.[0] || "",
        humanEvidence.stakeholder_context?.evidence.access_method?.[0] || "",
        humanEvidence.stakeholder_context?.evidence.authorized_scope?.[0] || "",
      ),
    );
    const body: Record<string, unknown> = {
      run_id: reservedRunId,
      repository: normalizedRepository.repository,
      provider: normalizedRepository.provider,
      provider_access_mode: "auto",
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
      report_language: reportLanguageForRequest(locale),
      human_evidence: compactStrategicHumanEvidence(humanEvidence),
      engagement_field_states: normalizedStates,
    };
    if (normalizedRepository.provider_organization) {
      body.provider_organization = normalizedRepository.provider_organization;
    }
    if (normalizedRepository.provider_project) {
      body.provider_project = normalizedRepository.provider_project;
    }

    let acceptedRun: Result | null = null;
    const startedAt = Date.now();
    try {
      await verifyRuntimePersistence();
      if (token !== sequence.current) {
        return;
      }
      const stakeholder = humanEvidence.stakeholder_context?.evidence || {};
      writePersistedRun({
        version: 1,
        runId: reservedRunId,
        repository: normalizedRepository.repository,
        client,
        project,
        primaryTechnicalContact: stakeholder.primary_technical_contact?.[0] || "",
        accessMethod: stakeholder.access_method?.[0] || "",
        authorizedScope: stakeholder.authorized_scope?.[0] || "",
        engagementFieldStates: normalizedStates,
        customerId: scope.customerId,
        projectId: scope.projectId,
        startedAt,
        locale,
      });
      setProtectedRunId(reservedRunId);
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
      if (!acceptedRun) {
        const recovered = await recoverRun(reservedRunId, {
          repository: normalizedRepository.repository,
          customerId: scope.customerId,
          projectId: scope.projectId,
        });
        if (recovered) {
          persistExactRun(recovered, scope, startedAt);
          hydrateEngagementMetadata(recovered);
          publishResult(recovered);
          await continueRun(recovered, scope, token, startedAt);
          return;
        }
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
    setProtectedRunId("");
    clearPersistedRun(false);
    setRepository("");
    setClient("");
    setProject("");
    setAuthorized(false);
    setHumanEvidence({});
    setEngagementFieldStates(emptyEngagementFieldStates());
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
      if (issue && isAmbiguousIntakeOutcome(issue.code)) {
        return;
      }
      await run();
      return;
    }
    const scope = currentScope();
    const stakeholder = humanEvidence.stakeholder_context?.evidence || {};
    await resumePersistedRun(
      persisted || {
        version: 1,
        runId,
        repository,
        client,
        project,
        primaryTechnicalContact: stakeholder.primary_technical_contact?.[0] || "",
        accessMethod: stakeholder.access_method?.[0] || "",
        authorizedScope: stakeholder.authorized_scope?.[0] || "",
        engagementFieldStates,
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
    engagementFieldStates,
    phase,
    result,
    message,
    error,
    issue,
    attempt,
    elapsed,
    running,
    protectedRunId,
    setRepository,
    setClient: (value) => setEngagementFieldValue("client_name", value),
    setProject: (value) => setEngagementFieldValue("project_name", value),
    setAuthorized,
    setHumanEvidence,
    setEngagementFieldValue,
    setEngagementFieldState,
    setError,
    run,
    retry,
    startNew,
  };
}

/* Compatibility routes remain implementation details: Express, Comprehensive, /assessment/express-run, /assessment/comprehensive-intake. */
