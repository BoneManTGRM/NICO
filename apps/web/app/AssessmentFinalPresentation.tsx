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

function polishPersistence(root: ParentNode): void {
  root.querySelectorAll("article").forEach((article) => {
    const labelNode = article.querySelector("b");
    const originalLabel = String(labelNode?.textContent || "").trim().toLowerCase();
    if (!["durable record", "registro duradero", "persistence", "persistencia"].includes(originalLabel)) return;
    const value = article.querySelector("span");
    if (!value || !labelNode) return;

    const spanish = ["registro duradero", "persistencia"].includes(originalLabel);
    labelNode.textContent = spanish ? "Persistencia" : "Persistence";

    const current = String(value.textContent || "").trim();
    if (/^yes$/i.test(current) || /^sí$/i.test(current) || /durability verified/i.test(current) || /durabilidad verificada/i.test(current)) {
      value.textContent = spanish ? "Durabilidad verificada" : "Durability verified";
      return;
    }
    if (/recorded,?\s*not durable/i.test(current) || /^persisted$/i.test(current) || /^persistido$/i.test(current)) {
      value.textContent = spanish ? "Registrado" : "Recorded";
    }
  });
}

function applyPresentation(root: ParentNode = document): void {
  polishButtons(root);
  polishStatuses(root);
  polishPersistence(root);
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
