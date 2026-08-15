"use client";

import {useEffect} from "react";

const LIVE_SPANISH_LABELS = new Map<string, string>([
  ["comprehensive run", "Ejecución integral"],
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

export default function AssessmentDynamicSpanishLocalization() {
  useEffect(() => {
    if (!document.documentElement.lang.toLowerCase().startsWith("es")) return;

    translateTree(document.body);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData" && record.target instanceof Text) {
          translateTextNode(record.target);
        }
        for (const node of record.addedNodes) translateTree(node);
      }
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, []);

  return null;
}

export {LIVE_SPANISH_LABELS, normalizedKey, translateTextNode};
