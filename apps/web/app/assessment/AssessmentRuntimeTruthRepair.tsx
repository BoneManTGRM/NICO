"use client";

import {useEffect} from "react";
import {localizeSpanishAssessmentDom} from "./AssessmentSpanishLocalization";
import "./assessment-runtime-truth.css";

type PersistenceSnapshot = {
  recorded?: boolean;
  durable?: boolean;
  durability_verified?: boolean;
  adapter?: string;
  note?: string;
  warning?: string;
};

type V2Snapshot = {
  assessment_state?: string;
  canonical_truth_sha256?: string;
  human_review_required?: boolean;
  human_review_completed?: boolean;
  client_delivery_allowed?: boolean;
  persistence?: PersistenceSnapshot;
  record?: V2Snapshot & {assessment_package_complete?: boolean};
};

declare global {
  interface Window {
    __nicoPersistenceSnapshot?: PersistenceSnapshot;
    __nicoV2AssessmentSnapshot?: V2Snapshot;
  }
}

export const SCANNER_STATUS_COPY = {
  en: "The scanner suite runs multiple tools and can remain on this stage for several minutes. NICO is still polling the backend automatically; do not restart the run.",
  es: "El conjunto de analizadores ejecuta varias herramientas y puede permanecer en esta etapa durante varios minutos. NICO continúa consultando el backend automáticamente; no reinicies la ejecución.",
};

function normalizeText(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isSpanish(): boolean {
  return document.documentElement.lang.toLowerCase().startsWith("es");
}

export function terminalRunVisible(): boolean {
  const state = window.__nicoV2AssessmentSnapshot?.assessment_state
    || window.__nicoV2AssessmentSnapshot?.record?.assessment_state;
  if (["review_required", "client_ready", "failed", "cancelled"].includes(String(state || ""))) return true;

  const section = document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!section) return false;
  const phase = normalizeText(section.querySelector(".section-head > span")?.textContent);
  if (["complete", "human review required", "ready for internal review", "internal review required", "completo", "revisión humana obligatoria", "listo para revisión interna", "revisión interna requerida"].includes(phase)) {
    return true;
  }
  const message = normalizeText(section.querySelector(":scope > p")?.textContent);
  return message.includes("express completed its evidence")
    || message.includes("express completó las etapas")
    || message.includes("comprehensive completed every automated stage")
    || message.includes("automated assessment complete")
    || message.includes("integral completó todas las etapas automatizadas");
}

export function persistenceDisplay(spanish: boolean): {text: string; warning: boolean} | null {
  const persistence = window.__nicoPersistenceSnapshot;
  if (!persistence) return null;
  const adapter = normalizeText(persistence.adapter) || "unknown";
  const durable = persistence.durable === true || persistence.durability_verified === true;
  if (durable) {
    if (adapter === "postgres") return {text: spanish ? "Durable · Postgres verificado" : "Durable · verified Postgres", warning: false};
    if (adapter === "sqlite") return {text: spanish ? "Durable · volumen SQLite persistente" : "Durable · persistent SQLite volume", warning: false};
    return {text: `Durable · ${adapter}`, warning: false};
  }
  if (persistence.recorded) {
    if (adapter === "sqlite") return {text: spanish ? "Registrado · verificación de almacenamiento pendiente" : "Recorded · storage verification pending", warning: true};
    if (adapter === "memory") return {
      text: spanish ? "Registro temporal en memoria · requiere Postgres o un volumen persistente" : "Temporary memory record · Postgres or a persistent volume required",
      warning: true,
    };
    return {text: spanish ? "Registrado · verificación de almacenamiento pendiente" : "Recorded · storage verification pending", warning: true};
  }
  return {text: spanish ? "Estado de persistencia pendiente" : "Persistence status pending", warning: true};
}

function legacyClipboardCopy(value: string): void {
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus({preventScroll: true});
  textarea.select();
  textarea.setSelectionRange(0, value.length);
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard copy was not accepted by this browser.");
}

export async function writeClipboardText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // iOS Safari can expose Clipboard but reject it outside its narrow permission path.
    }
  }
  legacyClipboardCopy(value);
}

/**
 * The React workspace calls navigator.clipboard.writeText directly. Install one
 * bounded wrapper so the same click keeps working on iPhone Safari when the
 * native Clipboard promise rejects. No report fetch or DOM event interception is
 * introduced, so the original user gesture remains intact.
 */
export function installNativeClipboardFallback(): () => void {
  const clipboard = navigator.clipboard;
  if (!clipboard?.writeText) return () => undefined;
  const nativeWrite = clipboard.writeText.bind(clipboard);
  const wrapped = async (value: string): Promise<void> => {
    try {
      await nativeWrite(value);
    } catch {
      legacyClipboardCopy(value);
    }
  };
  try {
    Object.defineProperty(clipboard, "writeText", {configurable: true, value: wrapped});
  } catch {
    return () => undefined;
  }
  return () => {
    try {
      Object.defineProperty(clipboard, "writeText", {configurable: true, value: nativeWrite});
    } catch {
      // The page is unloading; failure to restore a browser-owned property is harmless.
    }
  };
}

export function installCopyControl(card: HTMLElement, value: HTMLElement, spanish: boolean): void {
  if (card.querySelector(".nico-copy-control")) return;
  const raw = (value.textContent || "").trim();
  if (!raw || raw === "—") return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nico-copy-control";
  button.textContent = spanish ? "Copiar" : "Copy";
  button.addEventListener("click", async () => {
    try {
      await writeClipboardText(raw);
      button.textContent = spanish ? "Copiado" : "Copied";
    } catch {
      button.textContent = spanish ? "No disponible" : "Unavailable";
    }
  });
  card.appendChild(button);
}

function assessmentTarget(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function boundedPersistenceRequest(target: string): boolean {
  try {
    const path = new URL(target, window.location.origin).pathname;
    return path === "/api/nico/assessment/express-run" || path === "/api/nico/assessment/comprehensive-intake";
  } catch {
    return false;
  }
}

function statusProjectionRequest(target: string): boolean {
  try {
    return /\/status$/.test(new URL(target, window.location.origin).pathname);
  } catch {
    return false;
  }
}

function capturePersistence(response: Response): void {
  response.clone().json().then((payload: {persistence?: PersistenceSnapshot}) => {
    if (!payload?.persistence || typeof payload.persistence !== "object") return;
    window.__nicoPersistenceSnapshot = payload.persistence;
    window.dispatchEvent(new CustomEvent("nico:persistence-updated", {detail: payload.persistence}));
  }).catch(() => undefined);
}

function captureSnapshot(payload: V2Snapshot): void {
  if (!payload || typeof payload !== "object") return;
  window.__nicoV2AssessmentSnapshot = payload;
  if (payload.persistence && typeof payload.persistence === "object") {
    window.__nicoPersistenceSnapshot = payload.persistence;
  }
  window.dispatchEvent(new CustomEvent("nico:v2-state", {detail: payload}));
}

function captureAssessmentSnapshot(response: Response): void {
  const type = response.headers.get("content-type") || "";
  if (!type.includes("application/json")) return;
  response.clone().json().then((payload: V2Snapshot) => captureSnapshot(payload)).catch(() => undefined);
}

function transientStatus(status: number): boolean {
  return [429, 502, 503, 504].includes(status);
}

function projectAuthoritativeState(): void {
  const snapshot = window.__nicoV2AssessmentSnapshot;
  const state = String(snapshot?.assessment_state || snapshot?.record?.assessment_state || "");
  if (!state) return;
  const panel = document.querySelector<HTMLElement>('section[data-assessment-run-state="true"]');
  if (!panel) return;
  const spanish = isSpanish();
  const badge = panel.querySelector<HTMLElement>(".section-head > span");
  const message = panel.querySelector<HTMLElement>(":scope > p");
  const cards = Array.from(panel.querySelectorAll<HTMLElement>("article"));
  const reviewCard = cards.find((item) => normalizeText(item.querySelector("b")?.textContent) === (spanish ? "revisión interna" : "internal review"));
  const reviewValue = reviewCard?.querySelector<HTMLElement>("span");

  if (state === "review_required") {
    if (badge) {
      badge.textContent = spanish ? "LISTO PARA REVISIÓN INTERNA" : "READY FOR INTERNAL REVIEW";
      badge.classList.remove("red", "green");
      badge.classList.add("yellow");
    }
    if (message) message.textContent = spanish
      ? "La evaluación automatizada terminó. La revisión interna es el siguiente paso requerido antes de la entrega."
      : "The automated assessment is complete. Internal review is the next required step before delivery.";
    if (reviewValue) reviewValue.textContent = spanish ? "Requerida" : "Required";
  }
}

function installAssessmentFetchObserver(): () => void {
  const previousFetch = window.fetch;
  const observedFetch: typeof window.fetch = async (input, init) => {
    const target = assessmentTarget(input);
    const assessmentRequest = target.includes("/assessment/") || target.includes("/api/nico/assessment");
    const statusRequest = /\/status(?:\?|$)/.test(target);
    let nextInit = init;
    if (assessmentRequest) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
      headers.set("X-NICO-Client", "assessment-command-center-v42");
      if (isSpanish()) {
        headers.set("Accept-Language", "es-MX,es;q=0.9");
        headers.set("X-NICO-Locale", "es-MX");
      }
      nextInit = {...init, headers, cache: "no-store"};
    }
    let response = await previousFetch(input, nextInit);
    if (statusRequest && transientStatus(response.status)) {
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      response = await previousFetch(input, nextInit);
    }
    if (assessmentRequest && boundedPersistenceRequest(target)) capturePersistence(response);
    if (assessmentRequest && (boundedPersistenceRequest(target) || statusProjectionRequest(target))) {
      captureAssessmentSnapshot(response);
    }
    if (assessmentRequest) window.requestAnimationFrame(repairReviewWaitingPresentation);
    return response;
  };
  window.fetch = observedFetch;
  return () => {
    if (window.fetch === observedFetch) window.fetch = previousFetch;
  };
}

function runIdFromPage(): string {
  const fromUrl = new URL(window.location.href).searchParams.get("run_id")?.trim();
  if (fromUrl) return fromUrl;
  const identity = Array.from(document.querySelectorAll<HTMLElement>("code[title]")).find((node) => /^comprun_[a-z0-9]+$/i.test(node.title));
  return identity?.title || "";
}

export async function copyCurrentMarkdown(button: HTMLButtonElement): Promise<void> {
  const runId = runIdFromPage();
  if (!runId) throw new Error("Run ID is unavailable.");
  const response = await fetch(`/api/nico/assessment/comprehensive-run/${encodeURIComponent(runId)}/report/markdown`, {
    method: "GET",
    cache: "no-store",
    headers: {Accept: "text/markdown"},
  });
  if (!response.ok) throw new Error(`Markdown report is unavailable (${response.status}).`);
  const markdown = await response.text();
  if (!markdown.trim()) throw new Error("Markdown report is empty.");
  await writeClipboardText(markdown);
  const original = button.textContent || (isSpanish() ? "Copiar Markdown" : "Copy Markdown");
  button.textContent = isSpanish() ? "Markdown copiado" : "Markdown copied";
  window.setTimeout(() => { button.textContent = original; }, 1800);
}

export function installMarkdownCopyRepair(): () => void {
  const handler = (event: MouseEvent) => {
    const button = (event.target as Element | null)?.closest("button");
    if (!(button instanceof HTMLButtonElement)) return;
    const label = normalizeText(button.textContent);
    if (!label.includes("copy markdown") && !label.includes("copiar markdown")) return;
    if (button.disabled) return;
    button.disabled = true;
    void copyCurrentMarkdown(button).catch((error) => {
      button.textContent = isSpanish() ? "No se pudo copiar" : "Copy failed";
      button.title = error instanceof Error ? error.message : String(error);
    }).finally(() => {
      window.setTimeout(() => { button.disabled = false; }, 300);
    });
  };
  document.addEventListener("click", handler, false);
  return () => document.removeEventListener("click", handler, false);
}

function repairReviewWaitingPresentation(): void {
  if ((window.__nicoV2AssessmentSnapshot?.assessment_state || window.__nicoV2AssessmentSnapshot?.record?.assessment_state) === "review_required") {
    projectAuthoritativeState();
    return;
  }
  const panel = document.querySelector<HTMLElement>('section[data-assessment-run-state="true"]');
  if (!panel) return;
  const cards = Array.from(panel.querySelectorAll<HTMLElement>("article"));
  const cardValue = (label: string) => {
    const card = cards.find((item) => normalizeText(item.querySelector("b")?.textContent) === label);
    return normalizeText(card?.querySelector("span")?.textContent);
  };
  const packageComplete = ["complete", "completo"].includes(cardValue(isSpanish() ? "paquete de evaluación" : "assessment package"));
  const reviewWaiting = cardValue(isSpanish() ? "revisión interna" : "internal review").includes(isSpanish() ? "esper" : "await");
  const clientBlockedForApproval = cardValue(isSpanish() ? "listo para cliente" : "client-ready").includes(isSpanish() ? "aprobación" : "approval");
  if (!packageComplete || !reviewWaiting || !clientBlockedForApproval) return;

  const badge = panel.querySelector<HTMLElement>(".section-head > span");
  if (badge && ["assessment requires attention", "la evaluación requiere atención"].includes(normalizeText(badge.textContent))) {
    badge.textContent = isSpanish() ? "LISTO PARA REVISIÓN INTERNA" : "READY FOR INTERNAL REVIEW";
    badge.classList.remove("red");
    badge.classList.add("yellow");
  }
  const message = panel.querySelector<HTMLElement>(":scope > p");
  if (message && normalizeText(message.textContent).includes(isSpanish() ? "se detuvo" : "stopped")) {
    message.textContent = isSpanish()
      ? "La evaluación automatizada terminó. La revisión interna es el siguiente paso requerido antes de la entrega."
      : "The automated assessment is complete. Internal review is the next required step before delivery.";
  }
}

export default function AssessmentRuntimeTruthRepair() {
  useEffect(() => {
    const restoreFetch = installAssessmentFetchObserver();
    const restoreClipboard = installNativeClipboardFallback();
    localizeSpanishAssessmentDom(document);
    projectAuthoritativeState();
    repairReviewWaitingPresentation();
    const onPageShow = () => window.requestAnimationFrame(repairReviewWaitingPresentation);
    const onState = () => window.requestAnimationFrame(projectAuthoritativeState);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("nico:v2-state", onState);
    return () => {
      restoreFetch();
      restoreClipboard();
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("nico:v2-state", onState);
    };
  }, []);
  return null;
}
