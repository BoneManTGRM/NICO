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

let lastHeartbeatKey = "";
let lastHeartbeatAt = Date.now();

function normalizeText(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isSpanish(): boolean {
  return document.documentElement.lang.toLowerCase().startsWith("es");
}

function terminalRunVisible(): boolean {
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

function runningRunVisible(): boolean {
  const text = normalizeText(document.body.textContent);
  return text.includes("running automatically")
    || text.includes("running automatically")
    || text.includes("ejecutándose automáticamente")
    || text.includes("iniciando: express")
    || text.includes("starting: express")
    || text.includes("iniciando: integral")
    || text.includes("starting: comprehensive");
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
    return {
      text: spanish ? "Registrado · durabilidad no verificada" : "Recorded · durability not verified",
      warning: true,
    };
  }
  return {text: spanish ? "Persistencia no verificada" : "Persistence not verified", warning: true};
}

function setText(node: HTMLElement, text: string): void {
  if ((node.textContent || "").trim() !== text) node.textContent = text;
}

function assessmentMain(): HTMLElement | null {
  return document.querySelector<HTMLElement>('main.shell[data-assessment-service-count="2"]');
}

function assessmentPanels(): HTMLElement[] {
  return Array.from(assessmentMain()?.querySelectorAll<HTMLElement>("section.panel") || []);
}

function runPanel(): HTMLElement | null {
  return assessmentPanels().find((panel) => {
    const eyebrow = normalizeText(panel.querySelector(".section-head .eyebrow")?.textContent);
    return eyebrow.includes("automated run state") || eyebrow.includes("estado de ejecución automatizada");
  }) || null;
}

function valueForLabel(root: ParentNode, labels: string[]): string {
  for (const node of Array.from(root.querySelectorAll<HTMLElement>("span"))) {
    const label = normalizeText(node.querySelector("b")?.textContent);
    if (labels.includes(label)) {
      const clone = node.cloneNode(true) as HTMLElement;
      clone.querySelector("b")?.remove();
      return (clone.textContent || "").trim();
    }
  }
  return "";
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
    if (replacement) setText(node, replacement);
  });
}

function installCopyControl(card: HTMLElement, value: HTMLElement, spanish: boolean): void {
  if (card.querySelector(".nico-copy-control")) return;
  const raw = (value.textContent || "").trim();
  if (!raw || raw === "—") return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nico-copy-control";
  button.textContent = spanish ? "Copiar" : "Copy";
  button.setAttribute("aria-label", spanish ? "Copiar valor" : "Copy value");
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(raw);
      button.textContent = spanish ? "Copiado" : "Copied";
      window.setTimeout(() => { button.textContent = spanish ? "Copiar" : "Copy"; }, 1400);
    } catch {
      button.textContent = spanish ? "No disponible" : "Unavailable";
    }
  });
  card.appendChild(button);
}

function reconcileTargetCards(): void {
  const spanish = isSpanish();
  document.querySelectorAll<HTMLElement>(".target-grid article").forEach((card) => {
    const label = normalizeText(card.querySelector("b")?.textContent);
    const value = card.querySelector<HTMLElement>("span");
    if (!value) return;
    card.classList.add("nico-metadata-card");
    card.dataset.nicoMetric = label.replaceAll(" ", "-");

    if (["run id", "id de ejecución", "immutable commit", "commit inmutable"].includes(label)) {
      value.classList.add("nico-immutable-commit-value");
      value.title = value.textContent?.trim() || "";
      installCopyControl(card, value, spanish);
    }

    if (label === "durable record" || label === "registro durable") {
      const display = persistenceDisplay(spanish);
      if (display) {
        setText(value, display.text);
        value.classList.toggle("nico-storage-warning", display.warning);
        card.classList.toggle("nico-warning-card", display.warning);
        card.classList.toggle("nico-success-card", !display.warning);
        const title = window.__nicoPersistenceSnapshot?.warning
          || window.__nicoPersistenceSnapshot?.note
          || display.text;
        if (value.title !== title) value.title = title;
      } else if (/recorded, not durable|registrado, no durable/i.test(value.textContent || "")) {
        const fallback = spanish
          ? "Registro temporal · requiere Postgres o un volumen persistente"
          : "Temporary record · Postgres or a persistent volume required";
        setText(value, fallback);
        value.classList.add("nico-storage-warning");
        card.classList.add("nico-warning-card");
      }
    }

    if ((label === "human review" || label === "revisión humana")
      && terminalRunVisible()
      && /pending|pendiente/i.test(value.textContent || "")) {
      setText(value, spanish ? "Obligatoria" : "Required");
    }

    if ((label === "maturity signal" || label === "señal de madurez")
      && normalizeText(value.textContent) === "mid") {
      setText(value, spanish ? "Moderada" : "Moderate");
    }
  });
}

function reconcileHeroAndServiceChoice(): void {
  const main = assessmentMain();
  if (!main) return;
  main.classList.add("nico-command-center");
  const hero = main.querySelector<HTMLElement>(".hero");
  if (hero && !hero.querySelector(".nico-trust-strip")) {
    const spanish = isSpanish();
    const strip = document.createElement("div");
    strip.className = "nico-trust-strip";
    const values = spanish
      ? ["Solo lectura", "Commit inmutable", "Revisión humana obligatoria"]
      : ["Read-only", "Immutable commit", "Human review required"];
    values.forEach((text) => {
      const chip = document.createElement("span");
      chip.textContent = text;
      strip.appendChild(chip);
    });
    hero.appendChild(strip);
  }

  const spanish = isSpanish();
  const detail = spanish
    ? {express: "Línea base rápida", comprehensive: "Diligencia completa", integral: "Diligencia completa"}
    : {express: "Fast technical baseline", comprehensive: "Complete technical diligence", integral: "Complete technical diligence"};
  main.querySelectorAll<HTMLButtonElement>('#assessment button[aria-pressed]').forEach((button) => {
    button.classList.add("nico-service-choice");
    if (button.querySelector(".nico-service-detail")) return;
    const key = normalizeText(button.textContent) as keyof typeof detail;
    const descriptor = detail[key];
    if (!descriptor) return;
    const span = document.createElement("span");
    span.className = "nico-service-detail";
    span.textContent = descriptor;
    button.appendChild(span);
  });
}

function reconcileTimeline(): void {
  const spanish = isSpanish();
  document.querySelectorAll<HTMLElement>(".result-card").forEach((card) => {
    card.classList.add("nico-result-card");
    const heading = normalizeText(card.querySelector(".result-head b")?.textContent);
    const status = card.querySelector<HTMLElement>(".result-head .status");
    if (!status) return;
    const state = normalizeText(status.textContent);
    card.dataset.nicoState = state.replaceAll(" ", "-");
    if (state.includes("running") || state.includes("ejecución") || state.includes("ejecutando")) {
      card.classList.add("nico-active-stage");
    }
    if (terminalRunVisible()
      && (heading === "truth and review gates" || heading === "controles de veracidad y revisión")
      && /running|en ejecución|ejecutando/i.test(status.textContent || "")) {
      setText(status, spanish ? "completo" : "complete");
      status.className = "status green";
      const message = card.querySelector<HTMLElement>(":scope > p");
      if (message) {
        setText(message, spanish
          ? "Los controles automatizados de veracidad y revisión terminaron. La revisión humana sigue siendo obligatoria antes de la entrega."
          : "Automated truth and review gates completed. Human review remains required before delivery.");
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

    const card = badge.closest<HTMLElement>(".result-card");
    if (card && !card.querySelector(".nico-section-meter")) {
      const meter = document.createElement("div");
      meter.className = "nico-section-meter";
      meter.setAttribute("aria-hidden", "true");
      const fill = document.createElement("span");
      fill.style.width = `${score ?? 0}%`;
      fill.dataset.band = score === null ? "not-scored" : score >= 90 ? "exceptional" : score >= 80 ? "strong" : score >= 70 ? "moderate" : score >= 55 ? "weak" : "critical";
      meter.appendChild(fill);
      card.querySelector(".result-head")?.insertAdjacentElement("afterend", meter);
    }
  });
}

function reconcileRunningExperience(): void {
  const panel = runPanel();
  if (!panel) return;
  panel.classList.add("nico-run-panel");
  const progress = panel.querySelector<HTMLElement>('[role="progressbar"]');
  if (!progress || !runningRunVisible()) {
    panel.querySelector(".nico-live-heartbeat")?.remove();
    return;
  }

  const spanish = isSpanish();
  const stage = valueForLabel(panel, ["current stage", "etapa actual"])
    || progress.getAttribute("aria-label")
    || (spanish ? "Etapa activa" : "Active stage");
  const checks = valueForLabel(panel, ["status checks", "comprobaciones de estado"]);
  const percent = progress.getAttribute("aria-valuenow") || "";
  const key = `${stage}|${checks}|${percent}`;
  if (key !== lastHeartbeatKey) {
    lastHeartbeatKey = key;
    lastHeartbeatAt = Date.now();
  }
  const seconds = Math.max(0, Math.floor((Date.now() - lastHeartbeatAt) / 1000));
  const scannerStage = /scanner|anali[sz]adores/i.test(stage);
  let message = spanish
    ? `Estado activo verificado hace ${seconds} s.`
    : `Live status verified ${seconds}s ago.`;
  if (scannerStage) {
    message += spanish
      ? " El conjunto de analizadores ejecuta varias herramientas y puede permanecer en esta etapa durante varios minutos."
      : " The scanner suite runs multiple tools and can remain on this stage for several minutes.";
  }
  if (seconds >= 75) {
    message = spanish
      ? "Esta etapa está tardando más de lo habitual. NICO continúa consultando el backend automáticamente; no reinicies la ejecución."
      : "This stage is taking longer than usual. NICO is still polling the backend automatically; do not restart the run.";
  }

  let heartbeat = panel.querySelector<HTMLElement>(".nico-live-heartbeat");
  if (!heartbeat) {
    heartbeat = document.createElement("div");
    heartbeat.className = "nico-live-heartbeat";
    heartbeat.innerHTML = '<span class="nico-live-dot" aria-hidden="true"></span><span class="nico-live-copy"></span>';
    progress.insertAdjacentElement("afterend", heartbeat);
  }
  const copyNode = heartbeat.querySelector<HTMLElement>(".nico-live-copy");
  if (copyNode) setText(copyNode, message);
  progress.classList.add("nico-progress-live");
}

function reconcileReportActions(): void {
  document.querySelectorAll<HTMLElement>(".report-actions").forEach((actions) => {
    actions.classList.add("nico-report-actions");
    if (actions.querySelector(".nico-report-gate-note")) return;
    const note = document.createElement("span");
    note.className = "nico-report-gate-note";
    note.textContent = isSpanish()
      ? "Borrador vinculado a evidencia · requiere revisión humana"
      : "Evidence-bound draft · human review required";
    actions.appendChild(note);
  });
}

function reconcile(): void {
  reconcileLegacyServiceLabels();
  reconcileHeroAndServiceChoice();
  reconcileTargetCards();
  reconcileTimeline();
  reconcileCombinedSectionBadges();
  reconcileRunningExperience();
  reconcileReportActions();
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
    const next = JSON.stringify(payload.persistence);
    const previous = JSON.stringify(window.__nicoPersistenceSnapshot || {});
    if (next === previous) return;
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
    const heartbeat = window.setInterval(reconcile, 5000);
    const persistenceListener = () => reconcile();
    window.addEventListener("nico:persistence-updated", persistenceListener);
    return () => {
      observer.disconnect();
      window.clearInterval(heartbeat);
      window.removeEventListener("nico:persistence-updated", persistenceListener);
      restoreFetch();
    };
  }, []);
  return null;
}
