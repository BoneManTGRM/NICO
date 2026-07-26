"use client";

import {useEffect} from "react";

const WORKSPACE_SELECTOR = 'main[data-workspace="assessment"][data-engagement-type="comprehensive"][data-canonical-assessment="strategic"]';
const ACTION_SELECTOR = '[data-assessment-primary-action="true"]';

const EXPECTED_COPY = {
  en: {
    action: "Create engagement and capture repository snapshot",
    heading: "Create assessment engagement",
  },
  "es-MX": {
    action: "Crear encargo y capturar instantánea del repositorio",
    heading: "Crear encargo de evaluación",
  },
} as const;

type Locale = keyof typeof EXPECTED_COPY;

type Props = {
  locale: Locale;
  releaseSha: string;
  clientCopyContract: string;
};

function compact(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function replaceText(node: HTMLElement, value: string): void {
  if (compact(node.textContent) === value) return;
  node.replaceChildren(document.createTextNode(value));
}

export default function AssessmentHydrationContract({locale, releaseSha, clientCopyContract}: Props) {
  useEffect(() => {
    let cancelled = false;
    let observer: MutationObserver | null = null;
    let attempts = 0;

    const evaluate = (): boolean => {
      if (cancelled) return true;
      const workspace = document.querySelector<HTMLElement>(WORKSPACE_SELECTOR);
      if (!workspace) return false;

      const action = workspace.querySelector<HTMLElement>(ACTION_SELECTOR);
      const heading = workspace.querySelector<HTMLElement>("#assessment .section-head h2");
      if (!action || !heading) return false;

      const expected = EXPECTED_COPY[locale];
      const originalAction = compact(action.textContent);
      const originalHeading = compact(heading.textContent);
      let repaired = false;

      // The exact server release can occasionally be paired with a stale client
      // chunk during a deployment transition. Repair only the idle engagement copy
      // before any run state exists; never overwrite live progress labels.
      const runStateExists = Boolean(workspace.querySelector('[data-assessment-run-state="true"]'));
      if (!runStateExists) {
        if (originalAction !== expected.action) {
          replaceText(action, expected.action);
          action.setAttribute("aria-label", expected.action);
          repaired = true;
        }
        if (originalHeading !== expected.heading) {
          replaceText(heading, expected.heading);
          repaired = true;
        }
      }

      const observedAction = compact(action.textContent);
      const observedHeading = compact(heading.textContent);
      const verified = observedAction === expected.action && observedHeading === expected.heading;

      workspace.dataset.assessmentHydrated = "true";
      workspace.dataset.assessmentClientCopyContract = clientCopyContract;
      workspace.dataset.assessmentClientReleaseSha = compact(releaseSha) || "unknown";
      workspace.dataset.assessmentClientCopyVerified = verified ? "true" : "false";
      workspace.dataset.assessmentClientCopyRepaired = repaired ? "true" : "false";
      workspace.dataset.assessmentClientOriginalAction = originalAction || "missing";
      workspace.dataset.assessmentClientOriginalHeading = originalHeading || "missing";
      workspace.dataset.assessmentClientObservedAction = observedAction || "missing";
      workspace.dataset.assessmentClientObservedHeading = observedHeading || "missing";

      if (verified) {
        observer?.disconnect();
        observer = null;
        return true;
      }
      return false;
    };

    const retry = (): void => {
      if (cancelled || evaluate()) return;
      attempts += 1;
      if (attempts < 120) window.setTimeout(retry, 100);
    };

    retry();
    observer = new MutationObserver(() => evaluate());
    observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true});

    return () => {
      cancelled = true;
      observer?.disconnect();
    };
  }, [clientCopyContract, locale, releaseSha]);

  return null;
}
