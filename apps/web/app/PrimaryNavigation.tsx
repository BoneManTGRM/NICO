"use client";

import {useEffect, useState} from "react";
import {usePathname} from "next/navigation";

type ServiceKey = "run-job" | "operations" | "retainer";
type AssessmentMode = "express" | "mid" | "full";

const ASSESSMENT_TIER_EVENT = "nico:assessment-tier-selected";

export const PRIMARY_SERVICES = [
  {
    key: "run-job" as ServiceKey,
    label: "Run a Job",
    shortLabel: "Run a Job",
    href: "/assessment?tier=express#assessment",
  },
  {
    key: "operations" as ServiceKey,
    label: "Operations",
    shortLabel: "Operations",
    href: "/operations",
  },
  {
    key: "retainer" as ServiceKey,
    label: "Retainer",
    shortLabel: "Retainer",
    href: "/retainer-ops",
  },
] as const;

const SPANISH_PRIMARY_LABELS: Record<ServiceKey, string> = {
  "run-job": "Ejecutar evaluación",
  operations: "Operaciones",
  retainer: "Retainer",
};

const ADVANCED_GROUPS = [
  {
    label: "Operations and diagnostics",
    links: [
      {label: "Recovery", href: "/operations/recovery"},
      {label: "Backup & Restore", href: "/operations/backup-restore"},
      {label: "Scanner to Express", href: "/scanner-workflow"},
      {label: "Refresh Evidence", href: "/refresh-full-evidence"},
    ],
  },
  {
    label: "Utilities",
    links: [
      {label: "Easy Mode", href: "/easy"},
      {label: "Start Job", href: "/start-job"},
      {label: "Guide", href: "/guided-workflow"},
    ],
  },
] as const;

const SPANISH_ADVANCED_GROUPS = [
  {
    label: "Operaciones y diagnóstico",
    links: [
      {label: "Recuperación", href: "/operations/recovery"},
      {label: "Respaldo y restauración", href: "/operations/backup-restore"},
      {label: "Escáner a Express", href: "/scanner-workflow"},
      {label: "Actualizar evidencia", href: "/refresh-full-evidence"},
    ],
  },
  {
    label: "Utilidades",
    links: [
      {label: "Modo fácil", href: "/easy"},
      {label: "Iniciar trabajo", href: "/start-job"},
      {label: "Guía", href: "/guided-workflow"},
    ],
  },
] as const;

function normalizeAssessmentMode(value: string | null | undefined): AssessmentMode {
  return value === "mid" || value === "full" ? value : "express";
}

function serviceForPath(pathname: string, assessment: AssessmentMode): ServiceKey | "" {
  void assessment;
  if (pathname.startsWith("/assessment")) return "run-job";
  if (pathname.startsWith("/full-run")) return "run-job";
  if (pathname.startsWith("/operations")) return "operations";
  if (pathname.startsWith("/retainer-ops")) return "retainer";
  if (
    pathname.startsWith("/mid-assessment")
    || pathname.startsWith("/mid-review")
    || pathname.startsWith("/mid-report")
    || pathname.startsWith("/mid-approval")
    || pathname.startsWith("/mid-delivery-admin")
    || pathname.startsWith("/scanner-workflow")
    || pathname.startsWith("/refresh-full-evidence")
  ) return "run-job";
  return "";
}

export default function PrimaryNavigation() {
  const pathname = usePathname();
  const [assessment, setAssessment] = useState<AssessmentMode>("express");

  useEffect(() => {
    if (!pathname.startsWith("/assessment")) return;

    const synchronizeFromUrl = () => {
      setAssessment(normalizeAssessmentMode(new URLSearchParams(window.location.search).get("tier")));
    };
    const synchronizeFromEvent = (event: Event) => {
      const detail = (event as CustomEvent<{tier?: string}>).detail;
      setAssessment(normalizeAssessmentMode(detail?.tier));
    };

    synchronizeFromUrl();
    window.addEventListener("popstate", synchronizeFromUrl);
    window.addEventListener(ASSESSMENT_TIER_EVENT, synchronizeFromEvent as EventListener);
    return () => {
      window.removeEventListener("popstate", synchronizeFromUrl);
      window.removeEventListener(ASSESSMENT_TIER_EVENT, synchronizeFromEvent as EventListener);
    };
  }, [pathname]);

  const activeService = serviceForPath(pathname, assessment);
  const spanishActive = pathname.startsWith("/es-mx");
  const languageHref = spanishActive ? "/assessment?tier=express#assessment" : "/es-mx";
  const languageLabel = spanishActive ? "English" : "Español";
  const advancedGroups = spanishActive ? SPANISH_ADVANCED_GROUPS : ADVANCED_GROUPS;

  return (
    <nav className="global-nav" aria-label={spanishActive ? "Navegación principal de NICO" : "NICO primary navigation"}>
      <div className="global-nav-inner">
        <a className="global-brand" href="/assessment?tier=express#assessment" aria-label={spanishActive ? "Inicio de NICO" : "NICO home"}>NICO</a>

        <div className="primary-service-links" data-primary-service-count="3">
          {PRIMARY_SERVICES.map((service) => {
            const active = activeService === service.key;
            const label = spanishActive ? SPANISH_PRIMARY_LABELS[service.key] : service.label;
            return (
              <a
                key={service.key}
                className={`primary-service-link${active ? " active" : ""}`}
                href={service.href}
                aria-current={active ? "page" : undefined}
                data-service={service.key}
              >
                <span className="primary-service-label">{label}</span>
                <span className="primary-service-short-label">{label}</span>
              </a>
            );
          })}
        </div>

        <a
          className={`primary-service-link${spanishActive ? " active" : ""}`}
          href={languageHref}
          hrefLang={spanishActive ? "en" : "es-MX"}
          lang={spanishActive ? "en" : "es-MX"}
          aria-label={spanishActive ? "Cambiar a inglés" : "Cambiar a Español"}
        >
          <span className="primary-service-label">{languageLabel}</span>
          <span className="primary-service-short-label">{languageLabel}</span>
        </a>

        <details className="nav-more">
          <summary aria-label={spanishActive ? "Abrir herramientas avanzadas de NICO" : "Open advanced NICO tools"}>{spanishActive ? "Más" : "More"}</summary>
          <div className="nav-more-panel" lang={spanishActive ? "es-MX" : undefined}>
            <div className="nav-more-heading">
              <b>{spanishActive ? "Herramientas avanzadas" : "Advanced tools"}</b>
              <span>{spanishActive ? "Diagnóstico y utilidades para operadores" : "Operator diagnostics and utilities"}</span>
            </div>
            <div className="nav-more-groups">
              {advancedGroups.map((group) => (
                <section className="nav-more-group" key={group.label}>
                  <p>{group.label}</p>
                  {group.links.map((link) => (
                    <a href={link.href} key={link.href}>{link.label}</a>
                  ))}
                </section>
              ))}
            </div>
          </div>
        </details>
      </div>
    </nav>
  );
}
