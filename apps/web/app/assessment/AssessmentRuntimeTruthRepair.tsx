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

declare global {
  interface Window {
    __nicoPersistenceSnapshot?: PersistenceSnapshot;
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

/**
 * Compatibility helper retained for source-level truth tests and bounded manual
 * diagnostics. It is deliberately not driven by a MutationObserver. React owns
 * the assessment DOM; external mutation of live result nodes previously caused
 * the Comprehensive page to fall into the root error boundary during long runs.
 */
export function terminalRunVisible(): boolean {
  const section = document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!section) return false;
  const phase = normalizeText(section.querySelector(".section-head > span")?.textContent);
  if (["complete", "human review required", "completo", "revisión humana obligatoria"].includes(phase)) {
    return true;
  }
  const message = normalizeText(section.querySelector(":scope > p")?.textContent);
  return message.includes("express completed its evidence")
    || message.includes("express completó las etapas")
    || message.includes("comprehensive completed every automated stage")
    || message.includes("integral completó todas las etapas automatizadas");
}

export function persistenceDisplay(spanish: boolean): {text: string; warning: boolean} | null {
  const persistence = window.__nicoPersistenceSnapshot;
  if (!persistence) return null;
  const adapter = normalizeText(persistence.adapter) || "unknown";
  const durable = persistence.durable === true || persistence.durability_verified === true;
  if (durable) {
    if (adapter === "postgres") {
      return {text: spanish ? "Durable · Postgres verificado" : "Durable · verified Postgres", warning: false};
    }
    if (adapter === "sqlite") {
      return {text: spanish ? "Durable · volumen SQLite persistente" : "Durable · persistent SQLite volume", warning: false};
    }
    return {text: `Durable · ${adapter}`, warning: false};
  }
  if (persistence.recorded) {
    if (adapter === "sqlite") {
      return {
        text: spanish
          ? "Registro temporal · volumen persistente no verificado"
          : "Temporary record · persistent volume not verified",
        warning: true,
      };
    }
    if (adapter === "memory") {
      return {
        text: spanish
          ? "Registro temporal en memoria · requiere Postgres o un volumen persistente"
          : "Temporary memory record · Postgres or a persistent volume required",
        warning: true,
      };
    }
    return {text: spanish ? "Registrado · durabilidad no verificada" : "Recorded · durability not verified", warning: true};
  }
  return {text: spanish ? "Persistencia no verificada" : "Persistence not verified", warning: true};
}

/** Retained as a bounded opt-in utility; it is never injected into React-owned nodes automatically. */
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
      await navigator.clipboard.writeText(raw);
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
    return path === "/api/nico/assessment/express-run"
      || path === "/api/nico/assessment/comprehensive-intake";
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

function transientStatus(status: number): boolean {
  return [429, 502, 503, 504].includes(status);
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

    // Only the small run-creation responses are cloned. Comprehensive continuation
    // responses accumulate stage evidence and report payloads; cloning and parsing
    // every one doubled browser memory at the exact point the prior release crashed.
    if (assessmentRequest && boundedPersistenceRequest(target)) capturePersistence(response);
    return response;
  };
  window.fetch = observedFetch;
  return () => {
    if (window.fetch === observedFetch) window.fetch = previousFetch;
  };
}

export default function AssessmentRuntimeTruthRepair() {
  useEffect(() => {
    const restoreFetch = installAssessmentFetchObserver();
    // One bounded localization pass preserves the Spanish route without observing
    // or mutating React-owned result nodes throughout a long assessment.
    localizeSpanishAssessmentDom(document);
    return () => {
      restoreFetch();
    };
  }, []);
  return null;
}
