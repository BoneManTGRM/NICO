"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const TIER_EVENT = "nico:assessment-tier-selected";

function normalized(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isAssessmentPath(pathname: string): boolean {
  return pathname === "/assessment" || pathname === "/es/assessment";
}

function spanishPage(pathname: string): boolean {
  return pathname.startsWith("/es") || document.documentElement.lang.toLowerCase().startsWith("es");
}

function forceCanonicalTier(pathname: string): void {
  if (!isAssessmentPath(pathname)) return;
  const url = new URL(window.location.href);
  if (url.searchParams.get("tier") !== "comprehensive") {
    url.searchParams.set("tier", "comprehensive");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }
}

function rewriteAssessmentCopy(main: HTMLElement, spanish: boolean): void {
  main.dataset.assessmentServiceCount = "1";
  main.dataset.canonicalAssessment = "strategic";

  const hero = main.querySelector<HTMLElement>(".hero");
  const heroEyebrow = hero?.querySelector<HTMLElement>(".eyebrow");
  const heroTitle = hero?.querySelector<HTMLElement>("h1");
  const heroLead = hero?.querySelector<HTMLElement>(".lead");
  if (heroEyebrow) heroEyebrow.textContent = spanish ? "EVALUACIÓN ESTRATÉGICA NICO" : "NICO STRATEGIC ASSESSMENT";
  if (heroTitle) heroTitle.textContent = spanish
    ? "Una evaluación. Un libro de evidencia. Un informe decisivo."
    : "One assessment. One evidence ledger. One decision-grade report.";
  if (heroLead) heroLead.textContent = spanish
    ? "NICO ejecuta automáticamente la línea base técnica, el análisis profundo, el triaje de hallazgos, la planificación y el paquete final sobre una sola instantánea inmutable."
    : "NICO automatically runs the technical baseline, deep analysis, finding triage, planning, and final package against one immutable snapshot.";

  const assessment = main.querySelector<HTMLElement>("#assessment");
  const eyebrow = assessment?.querySelector<HTMLElement>(".section-head .eyebrow");
  const heading = assessment?.querySelector<HTMLElement>(".section-head h2");
  const summary = assessment?.querySelector<HTMLElement>(".summary-box");
  if (eyebrow) eyebrow.textContent = spanish ? "EVALUACIÓN NICO UNIFICADA" : "UNIFIED NICO ASSESSMENT";
  if (heading) heading.textContent = spanish
    ? "Diligencia técnica y estratégica completa"
    : "Complete technical and strategic diligence";
  if (summary) summary.textContent = spanish
    ? "Una ejecución reúne todo lo útil de Express, Mid y Comprehensive: evidencia exacta, analizadores, puntuación calibrada, arquitectura, riesgo, código a corregir, hoja de ruta, recursos y un único informe final sujeto a revisión humana."
    : "One run combines everything useful from Express, Mid, and Comprehensive: exact evidence, scanners, calibrated scoring, architecture, risk, code-specific remediation, roadmap, resourcing, and one final report subject to human review.";

  const details = assessment?.querySelector<HTMLDetailsElement>("details.help-details");
  const detailSummary = details?.querySelector<HTMLElement>("summary");
  if (detailSummary) detailSummary.textContent = spanish ? "Qué incluye la evaluación" : "What the assessment includes";

  const runButton = Array.from(assessment?.querySelectorAll<HTMLButtonElement>("button.primary-button") || [])
    .find((button) => !button.hasAttribute("aria-pressed"));
  if (runButton) {
    const running = normalized(runButton.textContent).includes("running")
      || normalized(runButton.textContent).includes("ejecutándose");
    runButton.textContent = running
      ? (spanish ? "Ejecutando evaluación NICO" : "Running NICO Assessment")
      : (spanish ? "Ejecutar evaluación NICO" : "Run NICO Assessment");
  }
}

function selectComprehensiveAndHideChoices(main: HTMLElement): void {
  const buttons = Array.from(main.querySelectorAll<HTMLButtonElement>("#assessment button[aria-pressed]"));
  const comprehensive = buttons.find((button) => {
    const text = normalized(button.textContent);
    return text.startsWith("comprehensive") || text.startsWith("integral") || button.dataset.nicoService === "comprehensive";
  });
  const grid = comprehensive?.parentElement;
  if (grid) {
    grid.hidden = true;
    grid.setAttribute("aria-hidden", "true");
  }
  buttons.forEach((button) => {
    button.tabIndex = -1;
  });
  if (comprehensive && comprehensive.getAttribute("aria-pressed") !== "true" && !comprehensive.disabled) {
    comprehensive.click();
    window.dispatchEvent(new CustomEvent(TIER_EVENT, {detail: {tier: "comprehensive"}}));
  }
}

function hideOperatorNavigation(pathname: string): void {
  if (!isAssessmentPath(pathname)) return;
  document.querySelectorAll<HTMLElement>(".nav-more-group").forEach((group) => {
    const text = normalized(group.textContent);
    const operatorGroup = text.includes("operator workspaces")
      || text.includes("espacios de trabajo del operador")
      || text.includes("operations (admin)")
      || text.includes("operaciones (administrador)");
    if (operatorGroup) {
      group.hidden = true;
      group.setAttribute("aria-hidden", "true");
    }
  });
}

function reconcile(pathname: string): void {
  forceCanonicalTier(pathname);
  if (!isAssessmentPath(pathname)) return;
  const main = document.querySelector<HTMLElement>("main.shell");
  if (!main) return;
  const spanish = spanishPage(pathname) || main.dataset.assessmentLocale === "es-MX";
  selectComprehensiveAndHideChoices(main);
  rewriteAssessmentCopy(main, spanish);
  hideOperatorNavigation(pathname);
}

export default function UnifiedAssessmentPublicGuard() {
  const pathname = usePathname();

  useEffect(() => {
    let queued = false;
    const run = () => {
      queued = false;
      reconcile(pathname);
    };
    const schedule = () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(run);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true});
    window.addEventListener("popstate", schedule);
    schedule();
    const timer = window.setInterval(run, 750);
    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", schedule);
      window.clearInterval(timer);
    };
  }, [pathname]);

  return null;
}
