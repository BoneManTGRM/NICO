"use client";

import {useEffect} from "react";

const CONTEXT_PREFIX = "nico:review-context:";
const REPORT_ACTIONS_SELECTOR = '[data-assessment-report-actions="true"]';
const SUCCESS_STATUSES = new Set(["complete", "completed", "passed", "verified", "review_required"]);

type ReviewContext = {
  run_id: string;
  service: "express" | "comprehensive";
  customer_id: string;
  project_id: string;
  review_ready: boolean;
  cross_format_status: string;
  cross_format_failed_checks: string[];
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizedStatus(value: unknown): string {
  return String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function serviceFrom(value: Record<string, unknown>): "express" | "comprehensive" {
  const raw = String(value.service_id || value.service_tier || value.assessment_type || value.workflow || "").toLowerCase();
  return raw.includes("comprehensive") || String(value.run_id || "").startsWith("comprun_")
    ? "comprehensive"
    : "express";
}

function stageResults(value: Record<string, unknown>): Record<string, unknown> {
  const direct = asRecord(value.stage_results);
  if (Object.keys(direct).length) return direct;
  return asRecord(asRecord(value.record).stage_results);
}

export function finalReviewReadiness(value: Record<string, unknown>): {
  ready: boolean;
  status: string;
  failedChecks: string[];
} {
  if (serviceFrom(value) !== "comprehensive") {
    return {ready: true, status: "legacy", failedChecks: []};
  }
  const stage = asRecord(stageResults(value).cross_format_truth_verification);
  const status = normalizedStatus(stage.status);
  const failedChecks = Array.isArray(stage.failed_checks)
    ? stage.failed_checks.map((item) => String(item)).filter(Boolean)
    : [];
  const passed = SUCCESS_STATUSES.has(status) && failedChecks.length === 0;
  const runStatus = normalizedStatus(value.status || asRecord(value.record).status);
  const reviewRequired = runStatus === "review_required" || runStatus === "approved";
  const deliveryBlocked = value.client_delivery_allowed !== true
    && asRecord(value.record).client_delivery_allowed !== true;
  return {
    ready: passed && reviewRequired && deliveryBlocked,
    status: status || "missing",
    failedChecks,
  };
}

function storeContext(value: Record<string, unknown>): void {
  const runId = String(value.run_id || asRecord(value.record).run_id || "").trim();
  if (!runId) return;
  const readiness = finalReviewReadiness(value);
  const context: ReviewContext = {
    run_id: runId,
    service: serviceFrom(value),
    customer_id: String(value.customer_id || asRecord(value.record).customer_id || "default_customer"),
    project_id: String(value.project_id || asRecord(value.record).project_id || "default_project"),
    review_ready: readiness.ready,
    cross_format_status: readiness.status,
    cross_format_failed_checks: readiness.failedChecks,
  };
  try {
    window.sessionStorage.setItem(`${CONTEXT_PREFIX}${runId}`, JSON.stringify(context));
  } catch {
    // The visible exact run ID still supports the default-scope fallback.
  }
}

function contextFor(runId: string): ReviewContext {
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(`${CONTEXT_PREFIX}${runId}`) || "{}") as Partial<ReviewContext>;
    if (stored.run_id === runId) {
      return {
        run_id: runId,
        service: stored.service === "comprehensive" ? "comprehensive" : "express",
        customer_id: stored.customer_id || "default_customer",
        project_id: stored.project_id || "default_project",
        review_ready: stored.review_ready === true,
        cross_format_status: stored.cross_format_status || "missing",
        cross_format_failed_checks: Array.isArray(stored.cross_format_failed_checks)
          ? stored.cross_format_failed_checks.map((item) => String(item))
          : [],
      };
    }
  } catch {
    // Use the route-derived fallback below.
  }
  const tier = new URLSearchParams(window.location.search).get("tier") || "";
  return {
    run_id: runId,
    service: tier === "comprehensive" || runId.startsWith("comprun_") ? "comprehensive" : "express",
    customer_id: "default_customer",
    project_id: "default_project",
    review_ready: false,
    cross_format_status: "missing",
    cross_format_failed_checks: [],
  };
}

function visibleRunId(actions: HTMLElement | null = null): string {
  const fromActions = String(actions?.dataset.runId || "").trim();
  if (fromActions.startsWith("express_run_") || fromActions.startsWith("comprun_")) return fromActions;

  const fromQuery = new URLSearchParams(window.location.search).get("run_id")?.trim() || "";
  if (fromQuery.startsWith("express_run_") || fromQuery.startsWith("comprun_")) return fromQuery;

  const candidates = Array.from(document.querySelectorAll<HTMLElement>(".nico-identifier-value code[title]"));
  for (const candidate of candidates) {
    const value = String(candidate.getAttribute("title") || "").trim();
    if (value.startsWith("express_run_") || value.startsWith("comprun_")) return value;
  }
  return "";
}

function reportExists(container: HTMLElement): boolean {
  return Array.from(container.querySelectorAll<HTMLButtonElement>("button"))
    .some((button) => !button.disabled && /markdown|pdf|informe/i.test(button.textContent || ""));
}

function removeReviewAction(actions: HTMLElement | null): void {
  actions?.querySelector<HTMLElement>("[data-nico-final-review-action='true']")?.remove();
}

function installAction(): void {
  const pathname = window.location.pathname;
  const assessmentRoute = pathname.startsWith("/assessment")
    || pathname.startsWith("/es/assessment")
    || pathname === "/es-mx"
    || pathname.startsWith("/es-mx/");
  if (!assessmentRoute) return;
  const actions = document.querySelector<HTMLElement>(REPORT_ACTIONS_SELECTOR);
  const runId = visibleRunId(actions);
  if (!actions || !runId || !reportExists(actions)) {
    removeReviewAction(actions);
    return;
  }

  const existing = actions.querySelector<HTMLAnchorElement>("[data-nico-final-review-action='true']");
  const context = contextFor(runId);
  if (context.service === "comprehensive" && !context.review_ready) {
    existing?.remove();
    actions.dataset.nicoReviewGate = "blocked";
    actions.dataset.nicoCrossFormatStatus = context.cross_format_status;
    actions.dataset.nicoCrossFormatFailedChecks = context.cross_format_failed_checks.join(",");
    return;
  }

  actions.dataset.nicoReviewGate = "ready";
  delete actions.dataset.nicoCrossFormatFailedChecks;
  const path = window.location.pathname.toLowerCase();
  const queryLocale = new URLSearchParams(window.location.search).get("lang")?.toLowerCase();
  const spanish = path === "/es-mx"
    || path.startsWith("/es-mx/")
    || path.startsWith("/es/")
    || queryLocale === "es-mx"
    || queryLocale === "es"
    || document.documentElement.lang.toLowerCase().startsWith("es");
  const query = new URLSearchParams({
    service: context.service,
    run_id: context.run_id,
    customer_id: context.customer_id,
    project_id: context.project_id,
  });
  if (spanish) query.set("lang", "es-MX");
  const label = spanish ? "Revisar y aceptar este informe" : "Review and accept this report";
  const href = `/operations/final-review?${query}`;
  const ariaLabel = `${label}: ${runId}`;

  // Keep the terminal action installation strictly idempotent. This function is
  // invoked from a DOM observer; unconditional textContent replacement here would
  // create a new childList mutation and can form a requestAnimationFrame mutation
  // loop on completed reports, particularly expensive in WebKit/iOS Safari.
  if (existing) {
    if (existing.getAttribute("href") !== href) existing.setAttribute("href", href);
    if (existing.textContent !== label) existing.textContent = label;
    if (existing.getAttribute("aria-label") !== ariaLabel) existing.setAttribute("aria-label", ariaLabel);
    return;
  }

  const link = document.createElement("a");
  link.dataset.nicoFinalReviewAction = "true";
  link.className = "primary-link nico-final-review-action";
  link.setAttribute("href", href);
  link.textContent = label;
  link.setAttribute("aria-label", ariaLabel);
  actions.appendChild(link);
}

export default function AssessmentFinalReviewAction() {
  useEffect(() => {
    let installFrame = 0;
    const scheduleInstall = () => {
      if (installFrame) return;
      installFrame = window.requestAnimationFrame(() => {
        installFrame = 0;
        installAction();
      });
    };

    const previousFetch = window.fetch;
    const trackedFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      try {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, window.location.href);
        if (url.pathname.includes("/assessment/") && response.headers.get("content-type")?.includes("application/json")) {
          const payload = await response.clone().json();
          storeContext(asRecord(payload));
          scheduleInstall();
        }
      } catch {
        // Context capture is optional and must not affect assessment transport.
      }
      return response;
    };
    window.fetch = trackedFetch;

    // Watch only structural changes and the attributes that can make the exact-run
    // action newly eligible. Character-data changes are deliberately excluded so the
    // action's own label cannot trigger another installation pass.
    const observer = new MutationObserver(scheduleInstall);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["disabled", "data-run-id", "data-assessment-report-ready"],
    });
    installAction();
    return () => {
      observer.disconnect();
      if (installFrame) window.cancelAnimationFrame(installFrame);
      if (window.fetch === trackedFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
