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
  const explicit = normalize(button.getAttribute("aria-label"));
  const value = explicit || normalize(button.textContent);
  if (value.startsWith("express")) return "Express";
  if (value.startsWith("comprehensive")) return "Comprehensive";
  if (value.startsWith("integral")) return "Integral";
  return null;
}

export function reconcileServiceAccessibility(): number {
  const buttons = document.querySelectorAll<HTMLButtonElement>('#assessment button[aria-pressed]');
  buttons.forEach((button) => {
    const label = canonicalServiceLabel(button);
    if (label) button.setAttribute("aria-label", label);
    button.querySelectorAll<HTMLElement>(".nico-service-detail").forEach((detail) => {
      const descriptor = (detail.textContent || "").trim();
      if (descriptor) button.dataset.serviceDetail = descriptor;
      detail.textContent = "";
      detail.setAttribute("aria-hidden", "true");
    });
  });
  return buttons.length;
}

function scoreFromCard(card: HTMLElement): number | null {
  const original = card.querySelector<HTMLElement>(".nico-score-assurance-badge")?.dataset.originalStatus
    || card.querySelector<HTMLElement>(".result-head .status")?.textContent
    || "";
  const match = original.match(/(\d{1,3})\s*\/\s*100/);
  if (!match) return null;
  return Math.max(0, Math.min(100, Number(match[1])));
}

/**
 * Compatibility utility for completed, static report snapshots. It is never attached
 * to a live DOM observer because appending nodes inside React-owned result cards can
 * invalidate React's child tree during a long Comprehensive continuation sequence.
 */
export function reconcileScannerCoverage(): void {
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
      badge.appendChild(exclusion);
    }
  });
}

export default function AssessmentMetricDisplayV44() {
  useEffect(() => {
    let cancelled = false;
    let frame = 0;
    let attempts = 0;

    // Hydration can temporarily replace the server-rendered button nodes. Retry only
    // until both service buttons exist, then stop. React remains the sole owner of all
    // dynamic assessment nodes throughout the run.
    const reconcileUntilReady = () => {
      if (cancelled) return;
      const serviceButtonCount = reconcileServiceAccessibility();
      attempts += 1;
      if (serviceButtonCount < 2 && attempts < 120) {
        frame = window.requestAnimationFrame(reconcileUntilReady);
      }
    };

    reconcileUntilReady();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}
