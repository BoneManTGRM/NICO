"use client";

import {useEffect} from "react";

const CONTEXT_PREFIX = "nico:review-context:";

type ReviewContext = {
  run_id: string;
  service: "express" | "comprehensive";
  customer_id: string;
  project_id: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function serviceFrom(value: Record<string, unknown>): "express" | "comprehensive" {
  const raw = String(value.service_id || value.service_tier || value.assessment_type || value.workflow || "").toLowerCase();
  return raw.includes("comprehensive") || String(value.run_id || "").startsWith("comprun_")
    ? "comprehensive"
    : "express";
}

function storeContext(value: Record<string, unknown>): void {
  const runId = String(value.run_id || asRecord(value.record).run_id || "").trim();
  if (!runId) return;
  const context: ReviewContext = {
    run_id: runId,
    service: serviceFrom(value),
    customer_id: String(value.customer_id || asRecord(value.record).customer_id || "default_customer"),
    project_id: String(value.project_id || asRecord(value.record).project_id || "default_project"),
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
  };
}

function visibleRunId(): string {
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

function installAction(): void {
  if (!window.location.pathname.startsWith("/assessment") && !window.location.pathname.startsWith("/es/assessment")) return;
  const actions = document.querySelector<HTMLElement>(".report-actions");
  if (!actions || !reportExists(actions)) return;
  const runId = visibleRunId();
  if (!runId) return;

  const existing = actions.querySelector<HTMLAnchorElement>("[data-nico-final-review-action='true']");
  const context = contextFor(runId);
  const spanish = window.location.pathname.startsWith("/es/") || document.documentElement.lang.toLowerCase().startsWith("es");
  const query = new URLSearchParams({
    service: context.service,
    run_id: context.run_id,
    customer_id: context.customer_id,
    project_id: context.project_id,
  });
  if (spanish) query.set("lang", "es-MX");
  const label = spanish ? "Revisar y aceptar este informe" : "Review and accept this report";

  if (existing) {
    existing.href = `/operations/final-review?${query}`;
    existing.textContent = label;
    return;
  }

  const link = document.createElement("a");
  link.dataset.nicoFinalReviewAction = "true";
  link.className = "primary-link nico-final-review-action";
  link.href = `/operations/final-review?${query}`;
  link.textContent = label;
  link.setAttribute("aria-label", `${label}: ${runId}`);
  actions.appendChild(link);
}

export default function AssessmentFinalReviewAction() {
  useEffect(() => {
    const previousFetch = window.fetch;
    const trackedFetch: typeof window.fetch = async (input, init) => {
      const response = await previousFetch(input, init);
      try {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, window.location.href);
        if (url.pathname.includes("/assessment/") && response.headers.get("content-type")?.includes("application/json")) {
          const payload = await response.clone().json();
          storeContext(asRecord(payload));
          window.setTimeout(installAction, 0);
        }
      } catch {
        // Context capture is optional and must not affect assessment transport.
      }
      return response;
    };
    window.fetch = trackedFetch;

    const observer = new MutationObserver(() => window.requestAnimationFrame(installAction));
    observer.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["disabled"]});
    installAction();
    return () => {
      observer.disconnect();
      if (window.fetch === trackedFetch) window.fetch = previousFetch;
    };
  }, []);

  return null;
}
