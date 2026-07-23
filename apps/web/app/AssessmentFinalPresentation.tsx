"use client";

import {useEffect} from "react";

const BUTTON_REPLACEMENTS: Record<string, string> = {
  "Download draft PDF": "Download final report",
  "Descargar PDF del borrador": "Descargar informe final",
  "Descargar PDF de borrador": "Descargar informe final",
};

function polishedStatus(value: string): string {
  return value
    .replace(/\bunavailable\b/gi, "Evidence limited")
    .replace(/\bevidence limited\b(?:\s*·\s*evidence limited)+/gi, "Evidence limited")
    .replace(/\s*·\s*/g, " · ")
    .trim();
}

function polishButtons(root: ParentNode): void {
  root.querySelectorAll("button").forEach((button) => {
    const current = String(button.textContent || "").trim();
    const replacement = BUTTON_REPLACEMENTS[current];
    if (replacement && current !== replacement) button.textContent = replacement;
  });
}

function polishStatuses(root: ParentNode): void {
  root.querySelectorAll("span.status").forEach((badge) => {
    const current = String(badge.textContent || "").trim();
    const replacement = polishedStatus(current);
    if (replacement && replacement !== current) badge.textContent = replacement;
  });
}

function polishDurability(root: ParentNode): void {
  root.querySelectorAll("article").forEach((article) => {
    const label = String(article.querySelector("b")?.textContent || "").trim().toLowerCase();
    if (!["durable record", "registro duradero"].includes(label)) return;
    const value = article.querySelector("span");
    if (!value) return;
    const current = String(value.textContent || "").trim();
    if (/^yes$/i.test(current) || /^sí$/i.test(current)) {
      value.textContent = label === "registro duradero" ? "Durabilidad verificada" : "Durability verified";
      return;
    }
    if (/recorded,?\s*not durable/i.test(current)) {
      value.textContent = label === "registro duradero" ? "Persistido" : "Persisted";
    }
  });
}

function applyPresentation(root: ParentNode = document): void {
  polishButtons(root);
  polishStatuses(root);
  polishDurability(root);
}

export default function AssessmentFinalPresentation() {
  useEffect(() => {
    applyPresentation();
    const observer = new MutationObserver(() => applyPresentation());
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    return () => observer.disconnect();
  }, []);

  return null;
}
