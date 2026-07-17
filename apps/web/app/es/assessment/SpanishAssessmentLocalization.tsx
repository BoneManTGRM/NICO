"use client";

import {useEffect} from "react";

const TEXT: Record<string, string> = {
  "EXPRESS ASSESSMENT": "EVALUACIÓN EXPRESS",
  "MID ASSESSMENT": "EVALUACIÓN INTERMEDIA",
  "FULL ASSESSMENT": "EVALUACIÓN COMPLETA",
  "Fast evidence-bound technical baseline": "Línea base técnica rápida y vinculada a evidencia",
  "Complete snapshot-bound assessment": "Evaluación completa vinculada a una instantánea",
  "Deep multi-section technical assessment": "Evaluación técnica profunda de múltiples secciones",
  "Repository evidence, calibrated scoring, decision-ready repair intelligence, and a downloadable draft report.": "Evidencia del repositorio, puntuación calibrada, inteligencia de reparación lista para decisiones y un informe preliminar descargable.",
  "One exact commit, modern scanner suite, evidence attachment, technical score, decision-ready draft, and human-review request.": "Un commit exacto, conjunto moderno de analizadores, vinculación de evidencia, puntuación técnica, informe preliminar listo para decisiones y solicitud de revisión humana.",
  "Repository evidence, comprehensive scanners, multi-section scoring, trust-gated reports, and final-review request.": "Evidencia del repositorio, analizadores integrales, puntuación por secciones, informes sujetos a controles de confianza y solicitud de revisión final.",
  "Coverage calculated after run": "Cobertura calculada después de la ejecución",
  "Express": "Express",
  "Mid": "Intermedia",
  "Full": "Completa",
  "Express instructions": "Instrucciones de Express",
  "Mid instructions": "Instrucciones de la evaluación intermedia",
  "Full instructions": "Instrucciones de la evaluación completa",
  "Only assess repositories you own or are explicitly authorized to review. NICO performs defensive read-only assessment and does not make destructive changes.": "Evalúa únicamente repositorios que te pertenezcan o para los que tengas autorización explícita. NICO realiza evaluaciones defensivas de solo lectura y no efectúa cambios destructivos.",
  "Repository owner/name or GitHub URL": "Propietario/nombre del repositorio o URL de GitHub",
  "Client name, optional": "Nombre del cliente, opcional",
  "Project name, optional": "Nombre del proyecto, opcional",
  "Run assessment": "Ejecutar evaluación",
  "Running automatically": "Ejecución automática",
  "Human review required": "Se requiere revisión humana",
  "Not started": "No iniciada",
  "Starting": "Iniciando",
  "Complete": "Completa",
  "Request accepted": "Solicitud aceptada",
  "Repository evidence": "Evidencia del repositorio",
  "Scanner suite": "Conjunto de analizadores",
  "Scanner reconciliation": "Conciliación de analizadores",
  "Evidence attachment": "Vinculación de evidencia",
  "Accuracy review": "Revisión de precisión",
  "Technical scoring": "Puntuación técnica",
  "Score reconciliation": "Conciliación de puntuación",
  "Report generation": "Generación del informe",
  "Human-review request": "Solicitud de revisión humana",
  "Truth and review gates": "Controles de veracidad y revisión",
  "Request submission": "Envío de la solicitud",
  "Download PDF": "Descargar PDF",
  "Evidence": "Evidencia",
  "Findings": "Hallazgos",
  "Unavailable": "No disponible",
  "Repairs": "Reparaciones",
  "Assessment result": "Resultado de la evaluación",
};

const PLACEHOLDERS: Record<string, string> = {
  "your-org/your-repo": "tu-organización/tu-repositorio",
};

function translateTextNode(node: Text) {
  const original = node.nodeValue || "";
  const trimmed = original.trim();
  const translated = TEXT[trimmed];
  if (!translated) return;
  node.nodeValue = original.replace(trimmed, translated);
}

function translateElement(element: Element) {
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    const translated = PLACEHOLDERS[element.placeholder];
    if (translated) element.placeholder = translated;
  }
  for (const child of Array.from(element.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) translateTextNode(child as Text);
  }
}

function translateTree(root: ParentNode) {
  if (root instanceof Element) translateElement(root);
  root.querySelectorAll("*").forEach(translateElement);
}

export default function SpanishAssessmentLocalization() {
  useEffect(() => {
    document.documentElement.lang = "es";
    translateTree(document.body);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node as Text);
          if (node instanceof Element) translateTree(node);
        });
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, []);
  return null;
}
