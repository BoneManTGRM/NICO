"use client";

import {useEffect} from "react";
import "./assessment-metric-display-v44.css";

function normalize(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function spanish(): boolean {
  return document.documentElement.lang.toLowerCase().startsWith("es");
}

function canonicalServiceLabel(button: HTMLButtonElement): string | null {
  const value = normalize(button.textContent);
  if (value.startsWith("express")) return "Express";
  if (value.startsWith("comprehensive")) return "Comprehensive";
  if (value.startsWith("integral")) return "Integral";
  return null;
}

function reconcileServiceAccessibility(): void {
  document.querySelectorAll<HTMLButtonElement>('#assessment button[aria-pressed]').forEach((button) => {
    const label = canonicalServiceLabel(button);
    if (label) button.setAttribute("aria-label", label);
    button.querySelectorAll<HTMLElement>(".nico-service-detail").forEach((detail) => {
      detail.setAttribute("aria-hidden", "true");
    });
  });
}

function scoreFromCard(card: HTMLElement): number | null {
  const original = card.querySelector<HTMLElement>(".nico-score-assurance-badge")?.dataset.originalStatus
    || card.querySelector<HTMLElement>(".result-head .status")?.textContent
    || "";
  const match = original.match(/(\d{1,3})\s*\/\s*100/);
  if (!match) return null;
  return Math.max(0, Math.min(100, Number(match[1])));
}

function reconcileScannerCoverage(): void {
  const isSpanish = spanish();
  document.querySelectorAll<HTMLElement>(".results-grid .result-card").forEach((card) => {
    const heading = normalize(card.querySelector(".result-head b")?.textContent);
    const scanner = heading === "scanner worker evidence"
      || heading === "evidencia del conjunto de analizadores"
      || heading === "evidencia de los analizadores";
    if (!scanner) return;

    card.dataset.nicoMetricKind = "execution-coverage";
    const score = scoreFromCard(card);
    const pill = card.querySelector<HTMLElement>(".nico-technical-pill");
    if (pill && score !== null) {
      pill.textContent = `${isSpanish ? "Cobertura de ejecución" : "Execution coverage"}: ${score}/100`;
    }

    const badge = card.querySelector<HTMLElement>(".nico-score-assurance-badge");
    if (badge && !badge.querySelector(".nico-maturity-exclusion-pill")) {
      const exclusion = document.createElement("span");
      exclusion.className = "nico-maturity-exclusion-pill";
      exclusion.textContent = isSpanish ? "No se incluye en madurez" : "Excluded from maturity";
      exclusion.title = isSpanish
        ? "Los resultados de los analizadores ya alimentan los controles técnicos principales; incluirlos de nuevo duplicaría la evidencia."
        : "Scanner results already feed the core technical controls; including them again would double-count the evidence.";
      badge.appendChild(exclusion);
    }
  });
}

function reconcile(): void {
  reconcileServiceAccessibility();
  reconcileScannerCoverage();
}

export default function AssessmentMetricDisplayV44() {
  useEffect(() => {
    reconcile();
    const observer = new MutationObserver(reconcile);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    return () => observer.disconnect();
  }, []);
  return null;
}
