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
    const match = (badge.textContent || "").trim().match(/^(green|yellow|red|gray|supplemental|review_limited_not_scored)\s*·\s*(.+)$/i);
    if (!match) return;
    const status = match[1].toLowerCase();
    const score = match[2];
    const assurance = status === "green"
      ? (spanish ? "Verificada" : "Verified")
      : status === "yellow" || status === "review_limited_not_scored"
        ? (spanish ? "Revisión limitada" : "Review limited")
        : status === "red"
          ? (spanish ? "Bloqueada" : "Blocked")
          : status === "supplemental"
            ? (spanish ? "Complementaria" : "Supplemental")
            : (spanish ? "Pendiente" : "Pending");
    badge.textContent = `${spanish ? "Técnico" : "Technical"}: ${score} · ${assurance}`;
    badge.dataset.reconciled = "true";
  });
}

function reconcile(): void {
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
