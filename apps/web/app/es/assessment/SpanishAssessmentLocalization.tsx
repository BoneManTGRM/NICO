"use client";

import {useEffect} from "react";

const TEXT: Record<string, string> = {
  "NICO ASSESSMENTS": "EVALUACIONES NICO",
  "One form. Three assessment depths.": "Un formulario. Tres niveles de evaluación.",
  "Choose Express, Mid, or Full. NICO displays truthful backend stages, completes every automated step available for the tier, and stops at completion or a required human-review gate.": "Elige Express, Intermedia o Completa. NICO muestra las etapas reales del backend, completa cada paso automatizado disponible para el nivel y se detiene al finalizar o al llegar a un control obligatorio de revisión humana.",
  "EXPRESS ASSESSMENT": "EVALUACIÓN EXPRESS",
  "MID ASSESSMENT": "EVALUACIÓN INTERMEDIA",
  "FULL ASSESSMENT": "EVALUACIÓN COMPLETA",
  "Fast evidence-bound technical baseline": "Línea base técnica rápida vinculada a evidencia",
  "Complete snapshot-bound assessment": "Evaluación completa vinculada a una instantánea exacta",
  "Deep multi-section technical assessment": "Evaluación técnica profunda de múltiples secciones",
  "Repository evidence, calibrated scoring, decision-ready repair intelligence, and a downloadable draft report.": "Evidencia del repositorio, puntuación calibrada, inteligencia de reparación lista para decisiones y un informe preliminar descargable.",
  "One exact commit, modern scanner suite, evidence attachment, technical score, decision-ready draft, and human-review request.": "Un commit exacto, un conjunto moderno de analizadores, evidencia vinculada, puntuación técnica, un informe preliminar listo para decisiones y una solicitud de revisión humana.",
  "Repository evidence, comprehensive scanners, multi-section scoring, trust-gated reports, and final-review request.": "Evidencia del repositorio, analizadores integrales, puntuación por secciones, informes sujetos a controles de confianza y una solicitud de revisión final.",
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
  "I confirm I own this target or have explicit permission to assess it.": "Confirmo que soy propietario de este objetivo o que tengo autorización explícita para evaluarlo.",
  "The assessment backend URL is not configured.": "La URL del backend de evaluación no está configurada.",
  "AUTOMATED RUN STATE": "ESTADO DE EJECUCIÓN AUTOMATIZADA",
  "Running automatically": "Ejecutándose automáticamente",
  "Human review required": "Se requiere revisión humana",
  "Not started": "No iniciada",
  "Starting": "Iniciando",
  "Complete": "Completa",
  "Continuation timed out": "La continuación agotó el tiempo",
  "Run failed or blocked": "La ejecución falló o está bloqueada",
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
  "Current stage": "Etapa actual",
  "Progress": "Progreso",
  "Elapsed": "Tiempo transcurrido",
  "Status checks": "Comprobaciones de estado",
  "Run ID": "ID de ejecución",
  "Scanner": "Analizadores",
  "Report": "Informe",
  "Human review": "Revisión humana",
  "Maturity signal": "Señal de madurez",
  "Technical score": "Puntuación técnica",
  "Evidence readiness": "Preparación de evidencia",
  "Durable record": "Registro durable",
  "Pending": "Pendiente",
  "Not scored": "Sin puntuación",
  "Recorded, not durable": "Registrado, no durable",
  "Not verified": "No verificado",
  "Copy Markdown": "Copiar Markdown",
  "Download draft PDF": "Descargar PDF preliminar",
  "Open human review": "Abrir revisión humana",
  "Step evidence": "Evidencia de la etapa",
  "Evidence": "Evidencia",
  "Findings": "Hallazgos",
  "Unavailable or limited evidence": "Evidencia no disponible o limitada",
  "Assessment-wide unavailable evidence": "Evidencia no disponible en toda la evaluación",
  "Technical details": "Detalles técnicos",
  "Audit identity": "Identidad de auditoría",
};

const PHRASES: Array<[RegExp, string]> = [
  [/^Run Express assessment$/, "Ejecutar evaluación Express"],
  [/^Run Mid assessment$/, "Ejecutar evaluación intermedia"],
  [/^Run Full assessment$/, "Ejecutar evaluación completa"],
  [/^Running Express automatically\.\.\.$/, "Ejecutando Express automáticamente..."],
  [/^Running Mid automatically\.\.\.$/, "Ejecutando la evaluación intermedia automáticamente..."],
  [/^Running Full automatically\.\.\.$/, "Ejecutando la evaluación completa automáticamente..."],
  [/^Evidence \((\d+)\)$/, "Evidencia ($1)"],
  [/^Findings \((\d+)\)$/, "Hallazgos ($1)"],
  [/^Unavailable or limited evidence \((\d+)\)$/, "Evidencia no disponible o limitada ($1)"],
];

const PLACEHOLDERS: Record<string, string> = {
  "your-org/your-repo": "tu-organización/tu-repositorio",
  "Client name": "Nombre del cliente",
  "Project name": "Nombre del proyecto",
};

function translatedValue(value: string): string | null {
  const direct = TEXT[value];
  if (direct) return direct;
  for (const [pattern, replacement] of PHRASES) {
    if (pattern.test(value)) return value.replace(pattern, replacement);
  }
  return null;
}

function translateTextNode(node: Text) {
  const original = node.nodeValue || "";
  const trimmed = original.trim();
  if (!trimmed) return;
  const translated = translatedValue(trimmed);
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
        if (mutation.type === "characterData" && mutation.target.nodeType === Node.TEXT_NODE) {
          translateTextNode(mutation.target as Text);
        }
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node as Text);
          if (node instanceof Element) translateTree(node);
        });
      }
    });
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    return () => observer.disconnect();
  }, []);
  return null;
}
