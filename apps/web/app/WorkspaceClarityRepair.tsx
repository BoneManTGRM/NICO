"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";
import "../styles/workspace-clarity.css";

function normalized(value: string | null | undefined): string {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function spanishPage(): boolean {
  return document.documentElement.lang.toLowerCase().startsWith("es")
    || window.location.pathname.toLowerCase().startsWith("/es");
}

function assessmentServiceKey(button: HTMLButtonElement): "express" | "comprehensive" | null {
  const text = normalized(button.textContent);
  if (text.startsWith("express")) return "express";
  if (text.startsWith("comprehensive") || text.startsWith("integral")) return "comprehensive";
  return null;
}

function reconcileAssessmentChoices(): void {
  const main = document.querySelector<HTMLElement>('main.shell[data-assessment-service-count="2"]');
  if (!main) return;
  const spanish = spanishPage() || main.dataset.assessmentLocale === "es-MX";
  const labels = spanish
    ? {express: "Línea base técnica", comprehensive: "Diligencia técnica integral"}
    : {express: "Technical baseline", comprehensive: "Technical diligence"};

  main.querySelectorAll<HTMLButtonElement>('#assessment button[aria-pressed]').forEach((button) => {
    const key = assessmentServiceKey(button);
    if (!key) return;
    button.classList.add("nico-service-choice", "nico-service-choice-contained");
    button.dataset.nicoService = key;
    let detail = button.querySelector<HTMLElement>(".nico-service-detail");
    if (!detail) {
      detail = document.createElement("span");
      detail.className = "nico-service-detail";
      button.appendChild(detail);
    }
    if (detail.textContent !== labels[key]) detail.textContent = labels[key];
    button.setAttribute(
      "aria-label",
      `${key === "express" ? "Express" : spanish ? "Integral" : "Comprehensive"}: ${labels[key]}`,
    );
  });
}

function runKind(value: string): "express" | "comprehensive" | null {
  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue.startsWith("express_run_")) return "express";
  if (normalizedValue.startsWith("comprun_") || normalizedValue.startsWith("midrun_") || normalizedValue.startsWith("fullrun_")) return "comprehensive";
  return null;
}

function reconcileRunIdentity(): void {
  const main = document.querySelector<HTMLElement>('main.shell[data-assessment-service-count="2"]');
  if (!main) return;
  const spanish = spanishPage() || main.dataset.assessmentLocale === "es-MX";
  main.querySelectorAll<HTMLElement>("h2").forEach((heading) => {
    const raw = String(heading.dataset.nicoFullRunId || heading.textContent || "").trim();
    const kind = runKind(raw);
    if (!kind) return;
    heading.dataset.nicoFullRunId = raw;
    heading.title = raw;
    heading.classList.add("nico-run-identity-heading");
    const replacement = kind === "express"
      ? (spanish ? "Ejecución Express" : "Express run")
      : (spanish ? "Ejecución Integral" : "Comprehensive run");
    if (heading.textContent !== replacement) heading.textContent = replacement;
  });
}

function reconcileStorageGuidance(): void {
  const main = document.querySelector<HTMLElement>('main.shell[data-assessment-service-count="2"]');
  if (!main) return;
  const spanish = spanishPage() || main.dataset.assessmentLocale === "es-MX";
  main.querySelectorAll<HTMLElement>(".target-grid article").forEach((card) => {
    const label = normalized(card.querySelector("b")?.textContent);
    if (label !== "durable record" && label !== "registro durable") return;
    const value = normalized(card.querySelector("span")?.textContent);
    const unverified = value.includes("temporary")
      || value.includes("temporal")
      || value.includes("not verified")
      || value.includes("no verificado");
    card.classList.toggle("nico-storage-warning", unverified);
    if (!unverified || card.querySelector(".nico-storage-remediation")) return;

    const note = document.createElement("small");
    note.className = "nico-storage-remediation";
    note.textContent = spanish
      ? "La ejecución está registrada, pero todavía no se ha probado que sobreviva al reemplazo del contenedor. Conecta Postgres o monta un volumen persistente de Railway en /data; Operaciones verificará la durabilidad después del despliegue."
      : "The run is recorded, but survival across container replacement is not yet proven. Connect Postgres or mount a Railway persistent volume at /data; Operations will verify durability after deployment.";
    card.appendChild(note);
  });
}

function createGuide(id: string, title: string, paragraphs: string[], link?: {href: string; label: string}): HTMLElement {
  const guide = document.createElement("aside");
  guide.id = id;
  guide.className = "nico-workspace-guide";
  const heading = document.createElement("h3");
  heading.textContent = title;
  guide.appendChild(heading);
  paragraphs.forEach((text) => {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    guide.appendChild(paragraph);
  });
  if (link) {
    const anchor = document.createElement("a");
    anchor.href = link.href;
    anchor.textContent = link.label;
    guide.appendChild(anchor);
  }
  return guide;
}

function reconcileOperationsWorkspace(): void {
  if (window.location.pathname !== "/operations") return;
  const main = document.querySelector<HTMLElement>("main");
  if (!main) return;
  main.classList.add("nico-operator-workspace");
  const heading = main.querySelector<HTMLElement>("h1");
  if (heading && heading.textContent !== "Operations (Admin)") heading.textContent = "Operations (Admin)";
  const lead = main.querySelector<HTMLElement>(".lead");
  if (lead) lead.textContent = "Owner-only deployment health, readiness, workload, incident, storage, and alert evidence. This page is not required to run an assessment.";

  const authHeading = Array.from(main.querySelectorAll<HTMLElement>("h2")).find((item) => normalized(item.textContent) === "operator authentication");
  const panel = authHeading?.closest<HTMLElement>("section");
  if (!panel || panel.querySelector("#nico-operations-guide")) return;
  const guide = createGuide(
    "nico-operations-guide",
    "How to use Operations",
    [
      "Use this page only when you administer the live NICO deployment. Assessment users should use Run Assessment instead.",
      "NICO_ADMIN_TOKEN is a protected backend deployment secret. Enter the same configured value in the field below; it remains only in this open page's memory. Never place it in a URL, screenshot, issue, or message.",
      "Select Load operations to retrieve deployment alignment, semantic readiness, durable storage, workloads, incidents, and deterministic alerts.",
    ],
    {href: "/assessment?tier=express#assessment", label: "Return to Run Assessment"},
  );
  const form = panel.querySelector("form");
  panel.insertBefore(guide, form || null);
}

function reconcileRetainerWorkspace(): void {
  if (window.location.pathname !== "/retainer-ops") return;
  const main = document.querySelector<HTMLElement>("main");
  if (!main) return;
  main.classList.add("nico-retainer-workspace");
}

function reconcile(): void {
  reconcileAssessmentChoices();
  reconcileRunIdentity();
  reconcileStorageGuidance();
  reconcileOperationsWorkspace();
  reconcileRetainerWorkspace();
}

export default function WorkspaceClarityRepair() {
  const pathname = usePathname();

  useEffect(() => {
    let queued = false;
    const run = () => {
      queued = false;
      reconcile();
    };
    const schedule = () => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(run);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    schedule();
    const timer = window.setInterval(reconcile, 750);
    return () => {
      observer.disconnect();
      window.clearInterval(timer);
    };
  }, [pathname]);

  return null;
}
