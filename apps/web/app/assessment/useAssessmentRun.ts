"use client";

import {useEffect, useRef, useState} from "react";
import {copyFor} from "./assessmentCopy";
import {apiUrl, parseJson, scopeId, terminal, wait} from "./assessmentModel";
import {MAX_POLL_ATTEMPTS, POLL_INTERVAL_MS, type Locale, type Phase, type Result, type Scope, type Service} from "./assessmentTypes";

export type AssessmentRunController = {
  service: Service;
  repository: string;
  client: string;
  project: string;
  authorized: boolean;
  phase: Phase;
  result: Result | null;
  message: string;
  error: string;
  attempt: number;
  elapsed: number;
  running: boolean;
  setRepository: (value: string) => void;
  setClient: (value: string) => void;
  setProject: (value: string) => void;
  setAuthorized: (value: boolean) => void;
  setError: (value: string) => void;
  run: () => Promise<void>;
};

export function useAssessmentRun(locale: Locale): AssessmentRunController {
  const copy = copyFor(locale);
  const service: Service = "comprehensive";
  const [repository, setRepository] = useState("");
  const [client, setClient] = useState("");
  const [project, setProject] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const sequence = useRef(0);

  useEffect(() => {
    document.documentElement.lang = locale;
    const url = new URL(window.location.href);
    if (url.searchParams.get("tier") !== "comprehensive") {
      url.searchParams.set("tier", "comprehensive");
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
    return () => { sequence.current += 1; };
  }, [locale]);

  useEffect(() => {
    if (!started || !["starting", "running"].includes(phase)) return;
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [started, phase]);

  const running = phase === "starting" || phase === "running";

  async function continueRun(initial: Result, scope: Scope, token: number): Promise<void> {
    let current = initial;
    for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1) {
      if (token !== sequence.current) return;
      setResult(current);
      const stable = terminal(service, current);
      if (stable) {
        setPhase(stable);
        setAttempt(count);
        setMessage(stable === "review_required" ? copy.comprehensiveReview : copy.stopped);
        return;
      }

      setPhase("running");
      setAttempt(count);
      const currentStageId = String(current.current_stage || current.record?.current_stage || "");
      setMessage(`${copy.service.label}: ${copy.stageLabels[currentStageId] || currentStageId.replaceAll("_", " ") || copy.phases.running}.`);
      const runId = String(current.run_id || "");
      if (!runId) throw new Error(copy.runIdMissing);

      current = await parseJson(await fetch(apiUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({max_stages: 1}),
        cache: "no-store",
      }), copy);
      await wait(POLL_INTERVAL_MS);
    }
    setResult(current);
    setPhase("timed_out");
    setMessage(copy.phases.timed_out);
  }

  async function run(): Promise<void> {
    if (!authorized) {
      setError(copy.authError);
      return;
    }
    const token = sequence.current + 1;
    sequence.current = token;
    const scope = {
      customerId: scopeId("customer", client, "default_customer"),
      projectId: scopeId("project", project, "default_project"),
    };
    setPhase("starting");
    setResult(null);
    setError("");
    setMessage(`${copy.phases.starting}: ${copy.service.label}`);
    setAttempt(0);
    setStarted(Date.now());
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
    };

    try {
      const data = await parseJson(await fetch(apiUrl("/assessment/comprehensive-intake"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
        cache: "no-store",
      }), copy);
      if (token !== sequence.current) return;
      setResult(data);
      await continueRun(data, scope, token);
    } catch (caught) {
      if (token !== sequence.current) return;
      setPhase("failed");
      setError(caught instanceof Error ? caught.message : copy.backendError);
      setMessage(copy.backendError);
    }
  }

  return {service, repository, client, project, authorized, phase, result, message, error, attempt, elapsed, running, setRepository, setClient, setProject, setAuthorized, setError, run};
}

/* Compatibility routes remain implementation details: Express, Comprehensive, /assessment/express-run, /assessment/comprehensive-intake. */
