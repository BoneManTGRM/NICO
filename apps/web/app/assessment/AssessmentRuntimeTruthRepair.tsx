"use client";

import {useEffect} from "react";
import {localizeSpanishAssessmentDom} from "./AssessmentSpanishLocalization";
import "./assessment-runtime-truth.css";

type PersistenceSnapshot = {
  recorded?: boolean;
  durable?: boolean;
  durability_verified?: boolean;
  adapter?: string;
};

type V2Snapshot = {
  assessment_state?: string;
  canonical_truth_sha256?: string;
  human_review_required?: boolean;
  human_review_completed?: boolean;
  client_delivery_allowed?: boolean;
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
  const phase = normalizeText(section?.querySelector(".section-head > span")?.textContent);
  return ["complete", "internal review required", "ready for internal review", "completo", "revisión interna requerida"].includes(phase);
}

export function persistenceDisplay(spanish: boolean): {text: string; warning: boolean} | null {
  const persistence = window.__nicoPersistenceSnapshot;
  if (!persistence) return null;
  const adapter = normalizeText(persistence.adapter) || "unknown";
  const durable = persistence.durable === true || persistence.durability_verified === true;
  if (durable) return {text: spanish ? `Durable · ${adapter} verificado` : `Durable · verified ${adapter}`, warning: false};
  if (persistence.recorded) return {text: spanish ? "Registrado · verificación pendiente" : "Recorded · verification pending", warning: true};
  return {text: spanish ? "Persistencia pendiente" : "Persistence pending", warning: true};
}

async function writeClipboardText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall through to the synchronous selection fallback used by iPhone Safari.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.readOnly = true;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus({preventScroll: true});
  textarea.select();
  textarea.setSelectionRange(0, value.length);
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard copy was not accepted by this browser.");
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

function captureSnapshot(payload: V2Snapshot): void {
  if (!payload || typeof payload !== "object") return;
  window.__nicoV2AssessmentSnapshot = payload;
  if ((payload as {persistence?: PersistenceSnapshot}).persistence) {
    window.__nicoPersistenceSnapshot = (payload as {persistence?: PersistenceSnapshot}).persistence;
  }
  window.requestAnimationFrame(projectAuthoritativeState);
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
      badge.textContent = spanish ? "REVISIÓN INTERNA REQUERIDA" : "INTERNAL REVIEW REQUIRED";
      badge.classList.remove("red", "green");
      badge.classList.add("yellow");
    }
    if (message) message.textContent = spanish
      ? "La evaluación automatizada y el paquete están completos. La revisión interna es el siguiente paso requerido."
      : "The automated assessment and package are complete. Internal review is the next required step.";
    if (reviewValue) reviewValue.textContent = spanish ? "Requerida" : "Required";
  }
}

function installAssessmentFetchObserver(): () => void {
  const previousFetch = window.fetch;
  const observedFetch: typeof window.fetch = async (input, init) => {
    const response = await previousFetch(input, init);
    const target = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (target.includes("/assessment/") || target.includes("/api/nico/assessment")) {
      const type = response.headers.get("content-type") || "";
      if (type.includes("application/json")) {
        response.clone().json().then(captureSnapshot).catch(() => undefined);
      }
    }
    return response;
  };
  window.fetch = observedFetch;
  return () => { if (window.fetch === observedFetch) window.fetch = previousFetch; };
}

export default function AssessmentRuntimeTruthRepair() {
  useEffect(() => {
    const restoreFetch = installAssessmentFetchObserver();
    localizeSpanishAssessmentDom(document);
    projectAuthoritativeState();
    const onPageShow = () => window.requestAnimationFrame(projectAuthoritativeState);
    const onState = () => window.requestAnimationFrame(projectAuthoritativeState);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("nico:v2-state", onState);
    return () => {
      restoreFetch();
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("nico:v2-state", onState);
    };
  }, []);
  return null;
}
