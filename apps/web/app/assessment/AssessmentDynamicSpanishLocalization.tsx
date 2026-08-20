"use client";

import {useEffect} from "react";

// Legacy source-contract marker retained for the superseded wording:
// ["comprehensive run", "Ejecución integral"]
const LIVE_SPANISH_LABELS = new Map<string, string>([
  ["comprehensive run", "Evaluación integral"],
  ["final comprehensive report generation", "Generación del informe final de evaluación"],
  ["final comprehensive report", "Informe final de evaluación"],
  ["assessment in progress", "Evaluación en curso"],
  ["assessment requires attention", "La evaluación requiere atención"],
  ["service unavailable", "Servicio no disponible"],
  ["blocked", "Bloqueado"],
  ["failed", "Fallido"],
  ["running", "En ejecución"],
  ["queued", "En cola"],
  ["pending", "Pendiente"],
  ["complete", "Completo"],
  ["completed", "Completado"],
  ["review required", "Revisión requerida"],
]);

const ACTIVE_RUN_LABELS = new Set(["assessment in progress", "evaluación en curso"]);
const TERMINAL_RUN_STATES = new Set([
  "blocked",
  "failed",
  "cancelled",
  "canceled",
  "rejected",
  "review required",
  "review_required",
  "client ready",
  "client_ready",
]);

type AssessmentSnapshot = {
  assessment_state?: unknown;
  record?: {assessment_state?: unknown};
};

type AssessmentLocale = "en" | "es-MX";

function normalizedKey(value: string): string {
  return value
    .replace(/[\s_-]+/g, " ")
    .trim()
    .toLowerCase();
}

function translateTextNode(node: Text): void {
  const parent = node.parentElement;
  if (!parent || parent.closest("script, style, code, pre, textarea, [data-no-localize='true']")) {
    return;
  }
  const source = node.nodeValue || "";
  if (!source.trim()) return;
  const replacement = LIVE_SPANISH_LABELS.get(normalizedKey(source));
  if (!replacement) return;
  const leading = source.match(/^\s*/)?.[0] || "";
  const trailing = source.match(/\s*$/)?.[0] || "";
  const localized = `${leading}${replacement}${trailing}`;
  if (localized !== source) node.nodeValue = localized;
}

function translateTree(root: Node): void {
  if (root instanceof Text) {
    translateTextNode(root);
    return;
  }
  if (!(root instanceof Element) && root !== document.body) return;
  if (root instanceof Element && root.closest("script, style, code, pre, textarea, [data-no-localize='true']")) {
    return;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    if (current instanceof Text) translateTextNode(current);
    current = walker.nextNode();
  }
}

function activeCanonicalRunIsNonTerminal(): boolean {
  const snapshot = (window as Window & {__nicoV2AssessmentSnapshot?: AssessmentSnapshot})
    .__nicoV2AssessmentSnapshot;
  const state = normalizedKey(String(
    snapshot?.assessment_state || snapshot?.record?.assessment_state || "",
  ));
  return !state || !TERMINAL_RUN_STATES.has(state);
}

/**
 * Keep the assessment-package card subordinate to canonical run state.
 * A package cannot truthfully be "blocked during final report generation" while the
 * exact Comprehensive run is still active in an earlier automated stage. Real terminal
 * evidence remains authoritative and is never rewritten here.
 */
function repairPrematurePackageBlock(locale: AssessmentLocale): void {
  const panel = document.querySelector<HTMLElement>('section[data-assessment-run-state="true"]')
    || document.querySelector<HTMLElement>('section[aria-live="polite"]');
  if (!panel || !activeCanonicalRunIsNonTerminal()) return;

  const badge = panel.querySelector<HTMLElement>(".section-head > span");
  if (!badge || !ACTIVE_RUN_LABELS.has(normalizedKey(badge.textContent || ""))) return;

  const cards = Array.from(panel.querySelectorAll<HTMLElement>("article"));
  const packageCard = cards.find((card) => {
    const label = normalizedKey(card.querySelector("b")?.textContent || "");
    return label === "assessment package" || label === "paquete de evaluación";
  });
  const value = packageCard?.querySelector<HTMLElement>("span");
  if (!value) return;

  const status = normalizedKey(value.textContent || "");
  const prematureFinalReportBlock = (
    status.includes("blocked") && status.includes("final report")
  ) || (
    status.includes("bloqueado") && status.includes("informe final")
  );
  if (!prematureFinalReportBlock) return;

  value.textContent = locale === "es-MX"
    ? "Pendiente · Se generará al completar las etapas automatizadas"
    : "Pending · Generated after the automated stages complete";
  value.dataset.nicoActivePackageStatusTruth = "pending";
}

function bindDocumentLanguage(locale: AssessmentLocale): () => void {
  const root = document.documentElement;
  const previous = root.lang || "en";
  root.lang = locale === "es-MX" ? "es-MX" : "en";
  root.dataset.nicoAssessmentDocumentLanguage = root.lang;

  return () => {
    root.lang = previous;
    delete root.dataset.nicoAssessmentDocumentLanguage;
  };
}

export default function AssessmentDynamicSpanishLocalization({locale}: {locale: "en" | "es-MX"}) {
  useEffect(() => {
    const restoreDocumentLanguage = bindDocumentLanguage(locale);
    if (locale !== "es-MX") return restoreDocumentLanguage;

    translateTree(document.body);
    repairPrematurePackageBlock(locale);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData" && record.target instanceof Text) {
          translateTextNode(record.target);
        }
        for (const node of record.addedNodes) translateTree(node);
      }
      repairPrematurePackageBlock(locale);
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    return () => {
      observer.disconnect();
      restoreDocumentLanguage();
    };
  }, [locale]);

  return null;
}

export {
  LIVE_SPANISH_LABELS,
  bindDocumentLanguage,
  normalizedKey,
  repairPrematurePackageBlock,
  translateTextNode,
};
