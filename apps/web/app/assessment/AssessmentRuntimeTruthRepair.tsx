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

function normalizeText(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isSpanish(): boolean {
  return document.documentElement.lang.toLowerCase().startsWith("es");
}

function terminalRunVisible(): boolean {
  const text = normalizeText(document.body.textContent);
  return text.includes("express completed its evidence")
    || text.includes("express completó las etapas")
    || text.includes("human review required")
    || text.includes("revisión humana obligatoria");
}

function technicalBand(score: number | null, spanish: boolean): string {
  if (score === null) return spanish ? "Sin puntuación" : "Not scored";
  if (score >= 90) return spanish ? "Excepcional" : "Exceptional";
  if (score >= 80) return spanish ? "Fuerte" : "Strong";
  if (score >= 70) return spanish ? "Moderada" : "Moderate";
  if (score >= 55) return spanish ? "Débil" : "Weak";
  return spanish ? "Crítica" : "Critical";
}

function assuranceLabel(status: string, spanish: boolean): string {
  const value = normalizeText(status).replaceAll("_", " ");
  if (["green", "verified", "verificado", "verificada"].includes(value)) return spanish ? "Verificada" : "Verified";
  if (["yellow", "review limited", "review limited not scored", "revisión limitada"].includes(value)) {
    return spanish ? "Revisión limitada" : "Review limited";
  }
  if (["red", "blocked", "bloqueado", "bloqueada"].includes(value)) return spanish ? "Bloqueada" : "Blocked";
  if (["supplemental", "complementario", "complementaria"].includes(value)) return spanish ? "Complementaria" : "Supplemental";
  if (["gray", "pending", "human review pending", "pendiente", "revisión humana pendiente"].includes(value)) {
    return spanish ? "Revisión humana pendiente" : "Human review pending";
  }
  return spanish ? "No verificada" : "Unverified";
}

function persistenceDisplay(spanish: boolean): {text: string; warning: boolean} | null {
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
    return {text: spanish ? `Durable · ${adapter}` : `Durable · ${adapter}`, warning: false};
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
    return {
      text: spanish ? "Registrado · durabilidad no verificada" : "Recorded · durability not verified",
      warning: true,
    };
  }
  return {text: spanish ? "Persistencia no verificada" : "Persistence not verified", warning: true};
}

function reconcileLegacyServiceLabels(): void {
  const spanish = isSpanish();
  const replacements = new Map<string, string>([
    ["mid assessment", spanish ? "Evaluación Integral" : "Comprehensive Assessment"],
    ["full assessment", spanish ? "Evaluación Integral" : "Comprehensive Assessment"],
    ["mid report", spanish ? "Informe Integral" : "Comprehensive Report"],
    ["full report", spanish ? "Informe Integral" : "Comprehensive Report"],
  ]);
  document.querySelectorAll<HTMLElement>("button, h1, h2, h3, .eyebrow, .service-label").forEach((node) => {
    const replacement = replacements.get(normalizeText(node.textContent));
    if (replacement) node.textContent = replacement;
  });
}

function reconcileTargetCards(): void {
  const spanish = isSpanish();
  document.querySelectorAll<HTMLElement>(".target-grid article").forEach((card) => {
    const label = normalizeText(card.querySelector("b")?.textContent);
    const value = card.querySelector<HTMLElement>("span");
    if (!value) return;

    if (label === "immutable commit" || label === "commit inmutable") {
      value.classList.add("nico-immutable-commit-value");
      value.title = value.textContent?.trim() || "";
    }

    if (label === "durable record" || label === "registro durable") {
      const display = persistenceDisplay(spanish);
      if (display) {
        value.textContent = display.text;
        value.classList.toggle("nico-storage-warning", display.warning);
        value.title = window.__nicoPersistenceSnapshot?.warning
          || window.__nicoPersistenceSnapshot?.note
          || display.text;
      } else if (/recorded, not durable|registrado, no durable/i.test(value.textContent || "")) {
        value.textContent = spanish
          ? "Registro temporal · requiere Postgres o un volumen persistente"
          : "Temporary record · Postgres or a persistent volume required";
        value.classList.add("nico-storage-warning");
      }
    }

    if ((label === "human review" || label === "revisión humana")
      && terminalRunVisible()
      && /pending|pendiente/i.test(value.textContent || "")) {
      value.textContent = spanish ? "Obligatoria" : "Required";
    }

    if ((label === "maturity signal" || label === "señal de madurez")
      && normalizeText(value.textContent) === "mid") {
      value.textContent = spanish ? "Moderada" : "Moderate";
    }
  });
}

function reconcileTimeline(): void {
  if (!terminalRunVisible()) return;
  const spanish = isSpanish();
  document.querySelectorAll<HTMLElement>(".result-card").forEach((card) => {
    const heading = normalizeText(card.querySelector(".result-head b")?.textContent);
    const status = card.querySelector<HTMLElement>(".result-head .status");
    if (!status) return;
    if ((heading === "truth and review gates" || heading === "controles de veracidad y revisión")
      && /running|en ejecución|ejecutando/i.test(status.textContent || "")) {
      status.textContent = spanish ? "completo" : "complete";
      status.className = "status green";
      const message = card.querySelector<HTMLElement>(":scope > p");
      if (message) {
        message.textContent = spanish
          ? "Los controles automatizados de veracidad y revisión terminaron. La revisión humana sigue siendo obligatoria antes de la entrega."
          : "Automated truth and review gates completed. Human review remains required before delivery.";
      }
    }
  });
}

function reconcileCombinedSectionBadges(): void {
  const spanish = isSpanish();
  document.querySelectorAll<HTMLElement>(".results-grid .result-head .status").forEach((badge) => {
    if (badge.dataset.reconciled === "true") return;
    const original = (badge.textContent || "").trim();
    const match = original.match(/^(green|yellow|red|gray|supplemental|review_limited_not_scored|review limited|verified|blocked|human review pending|verificado|verificada|revisión limitada|bloqueado|bloqueada|complementario|complementaria|revisión humana pendiente)\s*·\s*(.+)$/i);
    if (!match) return;

    const status = match[1];
    const scoreText = match[2].trim();
    const scoreMatch = scoreText.match(/(\d{1,3})\s*\/\s*100/);
    const score = scoreMatch ? Math.max(0, Math.min(100, Number(scoreMatch[1]))) : null;
    const band = technicalBand(score, spanish);
    const assurance = assuranceLabel(status, spanish);

    const technical = document.createElement("span");
    technical.className = "nico-technical-pill";
    technical.textContent = score === null
      ? `${spanish ? "Técnico" : "Technical"}: ${band}`
      : `${spanish ? "Técnico" : "Technical"}: ${band} · ${score}/100`;

    const assurancePill = document.createElement("span");
    assurancePill.className = "nico-assurance-pill";
    assurancePill.textContent = `${spanish ? "Evidencia" : "Assurance"}: ${assurance}`;

    badge.textContent = "";
    badge.append(technical, assurancePill);
    badge.className = "status nico-score-assurance-badge";
    badge.dataset.reconciled = "true";
    badge.dataset.originalStatus = original;
  });
}

function reconcile(): void {
  reconcileLegacyServiceLabels();
  reconcileTargetCards();
  reconcileTimeline();
  reconcileCombinedSectionBadges();
  localizeSpanishAssessmentDom(document);
}

function assessmentTarget(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function capturePersistence(response: Response): void {
  response.clone().json().then((payload: {persistence?: PersistenceSnapshot}) => {
    if (!payload?.persistence || typeof payload.persistence !== "object") return;
    window.__nicoPersistenceSnapshot = payload.persistence;
    window.dispatchEvent(new CustomEvent("nico:persistence-updated", {detail: payload.persistence}));
    reconcile();
  }).catch(() => undefined);
}

function installAssessmentFetchObserver(): () => void {
  const previousFetch = window.fetch;
  const observedFetch: typeof window.fetch = async (input, init) => {
    const target = assessmentTarget(input);
    const assessmentRequest = target.includes("/assessment/") || target.includes("/api/nico/assessment");
    let nextInit = init;
    if (assessmentRequest && isSpanish()) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
      headers.set("Accept-Language", "es-MX,es;q=0.9");
      headers.set("X-NICO-Locale", "es-MX");
      nextInit = {...init, headers};
    }
    const response = await previousFetch(input, nextInit);
    if (assessmentRequest) capturePersistence(response);
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
    reconcile();
    const observer = new MutationObserver(reconcile);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    const persistenceListener = () => reconcile();
    window.addEventListener("nico:persistence-updated", persistenceListener);
    return () => {
      observer.disconnect();
      window.removeEventListener("nico:persistence-updated", persistenceListener);
      restoreFetch();
    };
  }, []);
  return null;
}
