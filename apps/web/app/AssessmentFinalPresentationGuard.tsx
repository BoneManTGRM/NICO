"use client";

import {useEffect} from "react";

const TERMINAL_PHASES = new Set([
  "human review required",
  "complete",
  "revisión humana obligatoria",
  "completo",
]);

function normalizeTerminalPresentation(): boolean {
  const section = document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!section) return false;

  const phase = (section.querySelector(".section-head .status")?.textContent || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
  if (!TERMINAL_PHASES.has(phase)) return false;

  section.querySelectorAll<HTMLElement>(".target-grid article").forEach((card) => {
    const label = (card.querySelector("b")?.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    const value = card.querySelector<HTMLElement>(":scope > span");
    if (!value) return;

    if (label === "durable record") {
      const raw = (value.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      card.querySelector("b")!.textContent = "Assessment record";
      if (raw.includes("recorded")) value.textContent = "Recorded";
    }

    if (label === "registro durable") {
      const raw = (value.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      card.querySelector("b")!.textContent = "Registro de evaluación";
      if (raw.includes("registrado")) value.textContent = "Registrado";
    }
  });

  section.querySelectorAll<HTMLElement>(".result-card .status, .target-grid article > span").forEach((node) => {
    const raw = (node.textContent || "").replace(/\s+/g, " ").trim();
    if (raw === "unavailable") node.textContent = "Unavailable";
    if (raw === "no disponible") node.textContent = "No disponible";
  });

  document.querySelectorAll<HTMLButtonElement>(".report-actions button").forEach((button) => {
    const label = (button.textContent || "").replace(/\s+/g, " ").trim();
    if (label === "Download draft PDF") button.textContent = "Download final PDF";
    if (label === "Descargar PDF borrador") button.textContent = "Descargar PDF final";
  });

  document.querySelectorAll<HTMLElement>("main.shell p, main.shell span").forEach((node) => {
    const text = node.textContent || "";
    if (text.includes("downloadable draft report")) {
      node.textContent = text.replace("downloadable draft report", "complete final report package");
    }
    if (text.includes("informe borrador descargable")) {
      node.textContent = text.replace("informe borrador descargable", "paquete de informe final completo");
    }
  });

  return true;
}

export default function AssessmentFinalPresentationGuard() {
  useEffect(() => {
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (normalizeTerminalPresentation() || attempts >= 1200) {
        window.clearInterval(timer);
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  return null;
}
