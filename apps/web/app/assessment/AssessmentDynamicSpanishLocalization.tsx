"use client";

import {useEffect} from "react";
import {localizeSpanishText} from "./AssessmentSpanishLocalization";

// Legacy protected-node selector contract retained for regression compatibility:
// script, style, code, pre, textarea, [data-no-localize='true']
// Generic technical code remains protected below; only the known user-facing
// Spanish publication diagnostic is allowed through for presentation localization.

// Legacy source-contract marker retained for the superseded wording:
// ["comprehensive run", "Ejecución integral"]
const LIVE_SPANISH_LABELS = new Map<string, string>([
  ["comprehensive", "Integral"],
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

// Late production errors can be inserted after the initial Spanish DOM pass. Keep
// the known NICO-authored leak families localized at this live presentation boundary
// as well. This changes display copy only; canonical diagnostics remain untouched in
// the API response and exact-run evidence.
const LIVE_DIAGNOSTIC_SPANISH: Array<[RegExp, string]> = [
  [/Spanish Comprehensive report retained NICO-authored English presentation copy:/gi,
    "El informe Integral en español conservó texto de presentación en inglés generado por NICO:"],
  [/Review-Required Candidate Register/gi, "Registro de candidatos que requieren revisión"],
  [/Material confirmado findings/gi, "Hallazgos materiales confirmados"],
  [/verificada material findings/gi, "hallazgos materiales verificados"],
  [/Confirmed material findings/gi, "Hallazgos materiales confirmados"],
  [/Strengthen architecture boundaries, test\/release automation, functional QA evidence, and remediation verification\./gi,
    "Reforzar los límites de arquitectura, la automatización de pruebas y publicaciones, la evidencia de QA funcional y la verificación de remediaciones."],
  [/Sustainable delivery capacity is derived from immutable architecture maintainability and workflow automation; mutable activity volume is unscored context\./gi,
    "La capacidad de entrega sostenible se deriva de la mantenibilidad inmutable de la arquitectura y la automatización de los flujos de trabajo; el volumen de actividad mutable es contexto sin puntuación."],
  [/Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests\./gi,
    "Se analizaron las señales ejecutables del código fuente del commit exacto sin convertir comentarios, cadenas, definiciones de detectores, ejemplos ni pruebas en defectos."],
  [/Authoritative manifests and contextual dependency evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability\./gi,
    "Los manifiestos autoritativos y la evidencia contextual de dependencias se conciliaron por paquete, versión instalada, aviso, versión corregida, ruta, alcance y accesibilidad."],
  [/History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations\./gi,
    "La evidencia de secretos con conocimiento del historial se separó en hallazgos materiales verificados, candidatos que requieren revisión, marcadores explícitos de ejemplo y observaciones ajenas a producción."],
  [/Non-success deployment classification/gi, "Clasificación de despliegues no exitosos"],
  [/Job success rate/gi, "Tasa de éxito de trabajos"],
  [/Successful workflow runs/gi, "Ejecuciones exitosas de flujos de trabajo"],
  [/Non-success workflow runs/gi, "Ejecuciones no exitosas de flujos de trabajo"],
  [/Jobs observed/gi, "Trabajos observados"],
  [/Deployments observed/gi, "Despliegues observados"],
  [/Successful deployments/gi, "Despliegues exitosos"],
  [/Non-success deployments/gi, "Despliegues no exitosos"],
  [/Cybersecurity specialist/gi, "Especialista en ciberseguridad"],
  [/Code audit/gi, "Auditoría de código"],
  [/Not available/gi, "No disponible"],
];

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

export function localizeLiveSpanishText(value: string | null | undefined): string {
  let localized = String(value || "");
  for (const [pattern, replacement] of LIVE_DIAGNOSTIC_SPANISH) {
    localized = localized.replace(pattern, replacement);
  }
  return localizeSpanishText(localized);
}

function knownDiagnosticCode(value: string): boolean {
  return value.includes("v2_production_publication_failed")
    || value.includes("Spanish Comprehensive report retained NICO-authored English presentation copy");
}

function translateTextNode(node: Text): void {
  const parent = node.parentElement;
  if (!parent || parent.closest("script, style, textarea, [data-no-localize='true']")) {
    return;
  }
  const source = node.nodeValue || "";
  if (!source.trim()) return;

  // Generic code/pre blocks preserve exact technical identifiers. The one exception
  // is the known Spanish publication diagnostic, whose displayed prose is localized
  // while its stable machine prefix remains visible and unchanged.
  const inCode = Boolean(parent.closest("code"));
  if (parent.closest("pre") || (inCode && !knownDiagnosticCode(source))) return;

  const exact = LIVE_SPANISH_LABELS.get(normalizedKey(source));
  const replacement = exact || localizeLiveSpanishText(source);
  if (replacement === source) return;
  const leading = source.match(/^\s*/)?.[0] || "";
  const trailing = source.match(/\s*$/)?.[0] || "";
  const localized = exact
    ? `${leading}${replacement}${trailing}`
    : replacement;
  if (localized !== source) node.nodeValue = localized;
}

function translateTree(root: Node): void {
  if (root instanceof Text) {
    translateTextNode(root);
    return;
  }
  if (!(root instanceof Element) && root !== document.body) return;
  if (root instanceof Element && root.closest("script, style, textarea, [data-no-localize='true']")) {
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
  root.lang = locale;
  root.dataset.nicoAssessmentDocumentLanguage = root.lang;

  return () => {
    root.lang = previous;
    delete root.dataset.nicoAssessmentDocumentLanguage;
  };
}

export default function AssessmentDynamicSpanishLocalization({locale}: {locale: "en" | "es-MX"}) {
  useEffect(() => {
    // Preserve the long-standing English-route contract exactly. Root layout already
    // declares English, and this client boundary exists only to localize Spanish pages.
    if (locale !== "es-MX") return;

    const restoreDocumentLanguage = bindDocumentLanguage(locale);
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