"use client";

import {useEffect} from "react";

const TEXT: Record<string, string> = {
  "NICO FINAL REVIEW": "REVISIÓN FINAL DE NICO",
  "Review once. Approve once. Download the accepted report.": "Revisa una vez. Aprueba una vez. Descarga el informe aceptado.",
  "Review and release the final report.": "Revisa y libera el informe final.",
  "One exact package. One human decision. One accepted PDF.": "Un paquete exacto. Una decisión humana. Un PDF aceptado.",
  "Immutable run": "Ejecución inmutable",
  "Human approval": "Aprobación humana",
  "Delivery locked": "Entrega bloqueada",
  "Identify": "Identificar",
  "Exact report": "Informe exacto",
  "Approve": "Aprobar",
  "Download PDF": "Descargar PDF",
  "STEP 1 OF 2": "PASO 1 DE 2",
  "STEP 2 OF 2": "PASO 2 DE 2",
  "Open the exact report": "Abrir el informe exacto",
  "Run identity is filled automatically from the completed assessment.": "La identidad de ejecución se completa automáticamente desde la evaluación terminada.",
  "Read-only": "Solo lectura",
  "Exact package": "Paquete exacto",
  "Comprehensive assessment": "Evaluación integral",
  "Express assessment": "Evaluación exprés",
  "No report selected": "Ningún informe seleccionado",
  "Bound": "Vinculado",
  "Needed": "Necesario",
  "Name recorded on the immutable approval.": "Nombre registrado en la aprobación inmutable.",
  "Used once in this open page and never stored.": "Se usa una vez en esta página abierta y nunca se almacena.",
  "Use another report or advanced scope": "Usar otro informe o alcance avanzado",
  "Assessment type is detected from the run ID.": "El tipo de evaluación se detecta a partir del ID de ejecución.",
  "Open report for review": "Abrir informe para revisión",
  "Opening report…": "Abriendo informe…",
  "The report remains unchanged. Approval is bound to this exact run, report package, evidence set, and disclosed limitations.": "El informe permanece sin cambios. La aprobación queda vinculada a esta ejecución exacta, el paquete del informe, el conjunto de evidencia y las limitaciones declaradas.",
  "Review ready": "Listo para revisión",
  "Approved": "Aprobado",
  "Confirm the exact package, then approve and download it in one controlled action.": "Confirma el paquete exacto y después apruébalo y descárgalo en una sola acción controlada.",
  "Change report": "Cambiar informe",
  "Pending review": "Revisión pendiente",
  "This confirmation is recorded with the approval decision.": "Esta confirmación se registra con la decisión de aprobación.",
  "Add a note or choose another decision": "Agregar una nota o elegir otra decisión",
  "Review note": "Nota de revisión",
  "Download approved final PDF": "Descargar el PDF final aprobado",
  "Delivery stays locked until this exact package is approved.": "La entrega permanece bloqueada hasta que se apruebe este paquete exacto.",
  "The assessment report is not rewritten. Approval binds the authorized reviewer to the exact run, immutable report, evidence package, and disclosed limitations.": "El informe de evaluación no se reescribe. La aprobación vincula al revisor autorizado con la ejecución exacta, el informe inmutable, el paquete de evidencia y las limitaciones declaradas.",
  "Load the exact report": "Cargar el informe exacto",
  "Opening Final Review from a completed assessment automatically fills the service and run ID.": "Al abrir Revisión final desde una evaluación completada, el servicio y el ID de ejecución se completan automáticamente.",
  "Assessment type": "Tipo de evaluación",
  "Exact run ID": "ID de ejecución exacta",
  "Operator admin token": "Token de administrador del operador",
  "Authorized reviewer": "Revisor autorizado",
  "Advanced scope": "Alcance avanzado",
  "Customer ID": "ID del cliente",
  "Project ID": "ID del proyecto",
  "Load exact report": "Cargar informe exacto",
  "Reload exact status": "Recargar estado exacto",
  "The operator token remains only in this open page. It is not stored in the URL, browser storage, cookies, or build output.": "El token del operador permanece únicamente en esta página abierta. No se guarda en la URL, el almacenamiento del navegador, las cookies ni el resultado de compilación.",
  "Approve and receive the final report": "Aprobar y recibir el informe final",
  "Review the PDF and evidence limitations first. The button records approval and downloads the accepted PDF in one controlled action.": "Primero revisa el PDF y las limitaciones de evidencia. El botón registra la aprobación y descarga el PDF aceptado en una sola acción controlada.",
  "Review status": "Estado de revisión",
  "Client delivery": "Entrega al cliente",
  "Not loaded": "No cargado",
  "Blocked": "Bloqueada",
  "Authorized": "Autorizada",
  "Load the report above, review its exact PDF and limitations, then approve it here.": "Carga el informe, revisa su PDF exacto y sus limitaciones, y después apruébalo aquí.",
  "I reviewed the exact report, scorecard, evidence limitations, and delivery boundary for this run.": "Revisé el informe exacto, la tabla de puntuación, las limitaciones de evidencia y el límite de entrega de esta ejecución.",
  "Approval note, optional": "Nota de aprobación, opcional",
  "Approve and download final report": "Aprobar y descargar el informe final",
  "Report already approved": "Informe ya aprobado",
  "Download approved final PDF again": "Descargar de nuevo el PDF final aprobado",
  "Delivery remains blocked until the authorized reviewer approves this exact package.": "La entrega permanece bloqueada hasta que el revisor autorizado apruebe este paquete exacto.",
  "Approval is recorded for this exact run and the accepted report is available.": "La aprobación quedó registrada para esta ejecución exacta y el informe aceptado está disponible.",
  "Other decisions": "Otras decisiones",
  "Request more evidence": "Solicitar más evidencia",
  "Reject delivery": "Rechazar entrega",
  "Exact review record": "Registro exacto de revisión",

  "ONGOING ENGINEERING OVERSIGHT": "SUPERVISIÓN CONTINUA DE INGENIERÍA",
  "See what changed after an accepted assessment.": "Consulta qué cambió después de una evaluación aceptada.",
  "Retainer Ops does not rerun the full assessment and does not deploy code. It compares current GitHub evidence with one exact accepted baseline, identifies blockers and release concerns, and prepares weekly and monthly material for human review.": "Servicio continuo no repite la evaluación completa ni despliega código. Compara la evidencia actual de GitHub con una línea base exacta, identifica bloqueos y riesgos de liberación, y prepara material semanal y mensual para revisión humana.",
  "Create a baseline": "Crear una línea base",
  "Approve a completed report": "Aprobar un informe completado",
  "ONE CONTROL": "UN SOLO CONTROL",
  "Refresh ongoing evidence": "Actualizar evidencia continua",
  "Read-only GitHub evidence": "Evidencia de GitHub de solo lectura",
  "What it checks:": "Qué comprueba:",
  "current commit, commits, pull requests, open issues, workflow results, CodeQL activity, releases, deployments, and verified blocker signals. It never treats an empty field as proof that risk is clear.": "commit actual, commits, solicitudes de cambio, incidencias abiertas, resultados de flujos, actividad de CodeQL, versiones, despliegues y señales verificadas de bloqueo. Nunca considera un campo vacío como prueba de ausencia de riesgo.",
  "Repository owner/name": "Propietario/nombre del repositorio",
  "Accepted baseline run ID": "ID de ejecución de la línea base",
  "Evidence window": "Ventana de evidencia",
  "Last 7 days": "Últimos 7 días",
  "Last 30 days": "Últimos 30 días",
  "Last 90 days": "Últimos 90 días",
  "Last 180 days": "Últimos 180 días",
  "Optional business context": "Contexto comercial opcional",
  "These notes add decisions and business context that GitHub cannot prove. They cannot turn failed or unavailable technical evidence into a clean result.": "Estas notas agregan decisiones y contexto comercial que GitHub no puede demostrar. No pueden convertir evidencia técnica fallida o no disponible en un resultado limpio.",
  "Roadmap decisions": "Decisiones de la hoja de ruta",
  "Client update context": "Contexto de actualización para el cliente",
  "Success metrics": "Métricas de éxito",
  "Budget and scope context": "Contexto de presupuesto y alcance",
  "Advanced project scope": "Alcance avanzado del proyecto",
  "Client name": "Nombre del cliente",
  "Project name": "Nombre del proyecto",
  "I own this repository or have explicit permission to collect ongoing read-only engineering evidence.": "Soy propietario de este repositorio o tengo autorización explícita para recopilar evidencia continua de ingeniería de solo lectura.",
  "CURRENT OVERVIEW": "RESUMEN ACTUAL",
  "Baseline": "Línea base",
  "Matched": "Coincide",
  "Not matched": "No coincide",
  "Current commit": "Commit actual",
  "Verified sources": "Fuentes verificadas",
  "GitHub evidence checks": "Comprobaciones de evidencia de GitHub",
  "Ongoing delivery health": "Salud de entrega continua",
  "This is not the assessment technical-maturity score.": "Esta no es la puntuación de madurez técnica de la evaluación.",
  "Retainer results are advisory and require human review. Production actions, client communication, roadmap commitments, scope, budget, and timeline changes are never approved automatically.": "Los resultados del servicio continuo son consultivos y requieren revisión humana. Las acciones de producción, la comunicación con clientes y los cambios de hoja de ruta, alcance, presupuesto o calendario nunca se aprueban automáticamente.",
  "WHAT NEEDS ATTENTION": "QUÉ REQUIERE ATENCIÓN",
  "Changes, blockers, and release posture": "Cambios, bloqueos y postura de liberación",
  "What changed": "Qué cambió",
  "Current blockers": "Bloqueos actuales",
  "Release readiness": "Preparación para liberación",
  "Next review actions": "Próximas acciones de revisión",
  "Detailed evidence and scoring": "Evidencia detallada y puntuación",
  "SOURCE LEDGER": "REGISTRO DE FUENTES",
  "Exact evidence checks": "Comprobaciones exactas de evidencia",
  "Ongoing-health score:": "Puntuación de salud continua:",
  "Evidence": "Evidencia",
  "Findings": "Hallazgos",
  "Unavailable": "No disponible",
  "Monthly strategy": "Estrategia mensual",
  "Weekly status": "Estado semanal",
  "No verified items returned.": "No se devolvieron elementos verificados.",
  "not calculated": "no calculada",
  "Not calculated": "No calculada",
};

const PLACEHOLDERS: Record<string, string> = {
  "express_run_… or comprun_…": "express_run_… o comprun_…",
  "comprun_… or express_run_…": "comprun_… o express_run_…",
  "Name and role": "Nombre y función",
  "Optional approval context. Required only for other decisions.": "Contexto opcional de aprobación. Solo es obligatorio para otras decisiones.",
  "owner/repository": "propietario/repositorio",
  "Approved priorities, dependencies, or sequencing": "Prioridades, dependencias o secuencia aprobadas",
  "Context for the next reviewed update": "Contexto para la próxima actualización revisada",
  "Outcomes, service levels, or adoption measures": "Resultados, niveles de servicio o medidas de adopción",
  "Approved budget, scope, timeline, or priority constraints": "Restricciones aprobadas de presupuesto, alcance, calendario o prioridad",
};

function translateText(root: ParentNode): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const parent = node.parentElement;
    if (!parent || ["SCRIPT", "STYLE", "PRE", "CODE"].includes(parent.tagName)) continue;
    const normalized = String(node.nodeValue || "").trim();
    const translated = TEXT[normalized];
    if (translated) node.nodeValue = translated;
  }

  root.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input[placeholder], textarea[placeholder]").forEach((element) => {
    const translated = PLACEHOLDERS[element.placeholder];
    if (translated) element.placeholder = translated;
  });
}

export default function OperatorWorkspaceLocale() {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("lang") !== "es-MX") return;
    if (!window.location.pathname.startsWith("/operations") && !window.location.pathname.startsWith("/retainer-ops") && !window.location.pathname.startsWith("/guided-workflow")) return;

    const previousLanguage = document.documentElement.lang;
    document.documentElement.lang = "es-MX";
    document.body.dataset.nicoLocale = "es-MX";
    translateText(document.body);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData" && mutation.target.parentNode) translateText(mutation.target.parentNode);
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) translateText(node as Element);
        }
      }
    });
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    return () => {
      observer.disconnect();
      document.documentElement.lang = previousLanguage || "en";
      delete document.body.dataset.nicoLocale;
    };
  }, []);

  return null;
}
