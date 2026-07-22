"use client";

import {useEffect} from "react";
import "./assessment-runtime-truth.css";

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
  if (status === "green" || status === "verified") return spanish ? "Verificada" : "Verified";
  if (status === "yellow" || status === "review_limited_not_scored" || status === "review limited") {
    return spanish ? "Revisión limitada" : "Review limited";
  }
  if (status === "red" || status === "blocked") return spanish ? "Bloqueada" : "Blocked";
  if (status === "supplemental") return spanish ? "Complementaria" : "Supplemental";
  if (status === "gray" || status === "pending" || status === "human review pending") {
    return spanish ? "Revisión humana pendiente" : "Human review pending";
  }
  return spanish ? "No verificada" : "Unverified";
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

    if ((label === "durable record" || label === "registro durable")
      && /recorded, not durable|registrado, no durable/i.test(value.textContent || "")) {
      value.textContent = spanish
        ? "Almacenamiento no durable · requiere conexión a Postgres"
        : "Non-durable storage · Postgres connection required";
      value.classList.add("nico-storage-warning");
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
    const match = original.match(/^(green|yellow|red|gray|supplemental|review_limited_not_scored|review limited|verified|blocked|human review pending)\s*·\s*(.+)$/i);
    if (!match) return;

    const status = match[1].toLowerCase();
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
}

export default function AssessmentRuntimeTruthRepair() {
  useEffect(() => {
    reconcile();
    const observer = new MutationObserver(reconcile);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    return () => observer.disconnect();
  }, []);
  return null;
}
