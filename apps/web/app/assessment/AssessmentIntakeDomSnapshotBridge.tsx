"use client";

import {useEffect} from "react";

const COMPREHENSIVE_INTAKE_PATHS = new Set([
  "/assessment/comprehensive-intake",
  "/api/nico/assessment/comprehensive-intake",
]);
const CLIENT_LABELS = new Set([
  "Client name, optional",
  "Nombre del cliente, opcional",
]);
const PROJECT_LABELS = new Set([
  "Project name, optional",
  "Nombre del proyecto, opcional",
]);
const MOBILE_ENGAGEMENT_FIELDS = [
  "access_method",
  "primary_technical_contact",
  "authorized_scope",
] as const;

type MobileEngagementField = (typeof MOBILE_ENGAGEMENT_FIELDS)[number];
type IntakeDomSnapshot = {
  clientName: string | null;
  projectName: string | null;
  mobileEvidence: Record<MobileEngagementField, string[]> | null;
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function isComprehensiveIntake(input: RequestInfo | URL): boolean {
  try {
    const url = new URL(requestUrl(input), window.location.href);
    return COMPREHENSIVE_INTAKE_PATHS.has(url.pathname);
  } catch {
    return false;
  }
}

function normalizedLabelText(label: HTMLLabelElement): string {
  const clone = label.cloneNode(true) as HTMLLabelElement;
  clone
    .querySelectorAll("input, textarea, select, button, small")
    .forEach((node) => node.remove());
  return String(clone.textContent || "").replace(/\s+/g, " ").trim();
}

function inputForLabels(labels: ReadonlySet<string>): HTMLInputElement | null {
  for (const node of Array.from(document.querySelectorAll("label"))) {
    if (!(node instanceof HTMLLabelElement)) continue;
    if (!labels.has(normalizedLabelText(node))) continue;
    const input = node.querySelector("input");
    if (input instanceof HTMLInputElement) return input;
  }
  return null;
}

function evidenceLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 100);
}

function mobileEngagementSnapshot(): IntakeDomSnapshot["mobileEvidence"] {
  const section = document.querySelector(
    '[data-mobile-client-engagement-context="true"]',
  );
  if (!(section instanceof HTMLElement)) return null;

  const textareas = Array.from(section.querySelectorAll("textarea"));
  if (textareas.length !== MOBILE_ENGAGEMENT_FIELDS.length) return null;

  const output = {} as Record<MobileEngagementField, string[]>;
  for (let index = 0; index < MOBILE_ENGAGEMENT_FIELDS.length; index += 1) {
    const textarea = textareas[index];
    if (!(textarea instanceof HTMLTextAreaElement)) return null;
    output[MOBILE_ENGAGEMENT_FIELDS[index]] = evidenceLines(textarea.value);
  }
  return output;
}

function captureIntakeDomSnapshot(): IntakeDomSnapshot {
  const clientInput = inputForLabels(CLIENT_LABELS);
  const projectInput = inputForLabels(PROJECT_LABELS);
  return {
    clientName: clientInput ? clientInput.value : null,
    projectName: projectInput ? projectInput.value : null,
    mobileEvidence: mobileEngagementSnapshot(),
  };
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? {...(value as Record<string, unknown>)}
    : {};
}

export function rewriteComprehensiveIntakeBody(
  body: string,
  snapshot: IntakeDomSnapshot,
): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return body;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return body;
  }

  const payload = {...(parsed as Record<string, unknown>)};
  if (snapshot.clientName !== null) payload.client_name = snapshot.clientName;
  if (snapshot.projectName !== null) payload.project_name = snapshot.projectName;

  if (snapshot.mobileEvidence) {
    const humanEvidence = objectRecord(payload.human_evidence);
    const stakeholder = objectRecord(humanEvidence.stakeholder_context);
    const evidence = objectRecord(stakeholder.evidence);

    for (const field of MOBILE_ENGAGEMENT_FIELDS) {
      const values = snapshot.mobileEvidence[field];
      if (values.length) evidence[field] = values;
      else delete evidence[field];
    }

    stakeholder.evidence = evidence;
    humanEvidence.stakeholder_context = stakeholder;
    payload.human_evidence = humanEvidence;
  }

  return JSON.stringify(payload);
}

function isPrimaryAssessmentAction(target: EventTarget | null): boolean {
  return target instanceof Element
    && Boolean(target.closest('[data-assessment-primary-action="true"]'));
}

/**
 * Safari/iOS autofill, IME composition, and touch suggestion acceptance can update the
 * native control value before React's controlled state is committed. The mobile evidence
 * editor is then intentionally unmounted as soon as readiness checking begins. Capture
 * the actual controls during the native click capture phase and bind that exact snapshot
 * to the later Comprehensive intake request. No values are logged or persisted here.
 */
export default function AssessmentIntakeDomSnapshotBridge() {
  useEffect(() => {
    const originalFetch = window.fetch;
    let pendingSnapshot: IntakeDomSnapshot | null = null;

    const captureBeforeReactSubmit = (event: MouseEvent) => {
      if (!isPrimaryAssessmentAction(event.target)) return;
      pendingSnapshot = captureIntakeDomSnapshot();
    };

    const snapshotFetch: typeof window.fetch = async (input, init) => {
      if (
        !isComprehensiveIntake(input)
        || !init
        || typeof init.body !== "string"
      ) {
        return originalFetch.call(window, input, init);
      }

      const snapshot = pendingSnapshot || captureIntakeDomSnapshot();
      const response = await originalFetch.call(window, input, {
        ...init,
        body: rewriteComprehensiveIntakeBody(init.body, snapshot),
      });
      if (response.ok) pendingSnapshot = null;
      return response;
    };

    document.addEventListener("click", captureBeforeReactSubmit, true);
    window.fetch = snapshotFetch;
    return () => {
      document.removeEventListener("click", captureBeforeReactSubmit, true);
      if (window.fetch === snapshotFetch) window.fetch = originalFetch;
    };
  }, []);

  return null;
}
