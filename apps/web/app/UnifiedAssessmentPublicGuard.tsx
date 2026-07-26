"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const TIER_EVENT = "nico:assessment-tier-selected";
const CANONICAL_COPY_CONTRACT = "expert-engagement-v2";

function normalized(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function setText(element: HTMLElement | null | undefined, value: string): void {
  if (element && element.textContent !== value) element.textContent = value;
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
  if (main.dataset.assessmentServiceCount !== "1") main.dataset.assessmentServiceCount = "1";
  if (main.dataset.canonicalAssessment !== "strategic") main.dataset.canonicalAssessment = "strategic";
  if (main.dataset.customerFacingAssessment !== "comprehensive") main.dataset.customerFacingAssessment = "comprehensive";

  // The canonical React workspace owns its client-facing copy. This guard remains
  // responsible for tier selection and navigation boundaries, but must not replace
  // hydrated headings or actions after the release-copy contract has been verified.
  if (main.dataset.assessmentCopyContract === CANONICAL_COPY_CONTRACT) return;

  const hero = main.querySelector<HTMLElement>(".hero");
  setText(hero?.querySelector<HTMLElement>(".eyebrow"), spanish ? "EVALUACIÓN INTEGRAL NICO" : "NICO COMPREHENSIVE ASSESSMENT");
  setText(
    hero?.querySelector<HTMLElement>("h1"),
    spanish ? "Una evaluación. Un libro de evidencia. Un informe decisivo." : "One assessment. One evidence ledger. One decision-grade report.",
  );
  setText(
    hero?.querySelector<HTMLElement>(".lead"),
    spanish
      ? "NICO ejecuta automáticamente la línea base técnica, el análisis profundo, el triaje de hallazgos, la planificación y el paquete final sobre una sola instantánea inmutable."
      : "NICO automatically runs the technical baseline, deep analysis, finding triage, planning, and final package against one immutable snapshot.",
  );

  const assessment = main.querySelector<HTMLElement>("#assessment");
  setText(assessment?.querySelector<HTMLElement>(".section-head .eyebrow"), spanish ? "EVALUACIÓN INTEGRAL NICO" : "NICO COMPREHENSIVE ASSESSMENT");
  setText(
    assessment?.querySelector<HTMLElement>(".section-head h2"),
    spanish ? "Diligencia técnica y estratégica completa" : "Complete technical and strategic diligence",
  );
  setText(
    assessment?.querySelector<HTMLElement>(".summary-box"),
    spanish
      ? "Una evaluación revisa la salud técnica, seguridad, arquitectura, riesgo de entrega, remediación, hoja de ruta y recursos sobre una instantánea inmutable del repositorio."
      : "One assessment reviews technical health, security, architecture, delivery risk, remediation, roadmap, and resourcing against one immutable repository snapshot.",
  );

  const details = assessment?.querySelector<HTMLDetailsElement>("details.help-details");
  setText(details?.querySelector<HTMLElement>("summary"), spanish ? "Qué incluye la evaluación integral" : "What the comprehensive assessment includes");

  const runButton = Array.from(assessment?.querySelectorAll<HTMLButtonElement>("button.primary-button") || [])
    .find((button) => !button.hasAttribute("aria-pressed"));
  if (runButton) {
    const running = normalized(runButton.textContent).includes("running")
      || normalized(runButton.textContent).includes("ejecutándose");
    setText(
      runButton,
      running
        ? (spanish ? "Ejecutando evaluación NICO" : "Running NICO Assessment")
        : (spanish ? "Ejecutar evaluación NICO" : "Run NICO Assessment"),
    );
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
    if (!grid.hidden) grid.hidden = true;
    if (grid.getAttribute("aria-hidden") !== "true") grid.setAttribute("aria-hidden", "true");
    if (grid.style.getPropertyValue("display") !== "none" || grid.style.getPropertyPriority("display") !== "important") {
      grid.style.setProperty("display", "none", "important");
    }
    if (!grid.hasAttribute("inert")) grid.setAttribute("inert", "");
  }
  buttons.forEach((button) => {
    if (button.tabIndex !== -1) button.tabIndex = -1;
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
      if (!group.hidden) group.hidden = true;
      if (group.getAttribute("aria-hidden") !== "true") group.setAttribute("aria-hidden", "true");
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
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
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
