"use client";

import {useEffect, useRef, useState} from "react";
import {copyFor} from "./assessmentCopy";
import {
  apiUrl,
  normalizeService,
  parseJson,
  publicDepth,
  scopeId,
  terminal,
  wait,
} from "./assessmentModel";
import {
  MAX_POLL_ATTEMPTS,
  POLL_INTERVAL_MS,
  type Locale,
  type Phase,
  type Result,
  type Scope,
  type Service,
} from "./assessmentTypes";

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
  choose: (service: Service) => void;
  run: () => Promise<void>;
};

export function useAssessmentRun(locale: Locale): AssessmentRunController {
  const copy = copyFor(locale);
  const [service, setService] = useState<Service>("express");
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
    const next = normalizeService(url.searchParams.get("tier"));
    setService(next);
    const canonicalTier = publicDepth(next);
    if (url.searchParams.get("tier") !== canonicalTier) {
      url.searchParams.set("tier", canonicalTier);
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

  function resetRunState(): void {
    setResult(null);
    setPhase("idle");
    setMessage("");
    setError("");
    setAttempt(0);
    setStarted(null);
    setElapsed(0);
  }

  function choose(next: Service): void {
    if (running) return;
    setService(next);
    resetRunState();
    const url = new URL(window.location.href);
    url.searchParams.set("tier", publicDepth(next));
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new CustomEvent("nico:assessment-tier-selected", {detail: {tier: next, depth: publicDepth(next)}}));
  }

  async function continueRun(selected: Service, initial: Result, scope: Scope, token: number): Promise<void> {
    let current = initial;
    for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1) {
      if (token !== sequence.current) return;
      setResult(current);
      const stable = terminal(selected, current);
      if (stable) {
        setPhase(stable);
        setAttempt(count);
        setMessage(stable === "review_required" ? copy.comprehensiveReview : stable === "complete" ? copy.expressComplete : copy.stopped);
        return;
      }

      setPhase("running");
      setAttempt(count);
      const currentStageId = String(current.current_stage || current.record?.current_stage || "");
      setMessage(`${copy.services[selected].label}: ${copy.stageLabels[currentStageId] || currentStageId.replaceAll("_", " ") || copy.phases.running}.`);
      const runId = String(current.run_id || "");
      if (!runId) throw new Error(copy.runIdMissing);

      if (selected === "comprehensive") {
        current = await parseJson(await fetch(apiUrl(`/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({max_stages: 1}),
          cache: "no-store",
        }), copy);
      } else {
        await wait(POLL_INTERVAL_MS);
        current = await parseJson(await fetch(apiUrl(`/assessment/express-run/${encodeURIComponent(runId)}/status`), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({customer_id: current.customer_id || scope.customerId, project_id: current.project_id || scope.projectId}),
          cache: "no-store",
        }), copy);
      }
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
    setMessage(`${copy.phases.starting}: ${copy.services[service].label}`);
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
      assessment_depth: publicDepth(service),
      report_language: locale,
    };

    try {
      // Compatibility routes remain in place while both depths are bound to the
      // canonical run and package contract. They are implementation routes, not
      // independent customer-facing assessment products.
      const path = service === "express" ? "/assessment/express-run" : "/assessment/comprehensive-intake";
      const payload = service === "express" ? {...body, assessment_mode: "express"} : body;
      const data = await parseJson(await fetch(apiUrl(path), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
        cache: "no-store",
      }), copy);
      if (token !== sequence.current) return;
      setResult(data);
      await continueRun(service, data, scope, token);
    } catch (caught) {
      if (token !== sequence.current) return;
      setPhase("failed");
      setError(caught instanceof Error ? caught.message : copy.backendError);
      setMessage(copy.backendError);
    }
  }

  return {
    service,
    repository,
    client,
    project,
    authorized,
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
    setError,
    choose,
    run,
  };
}
