"use client";

import {useEffect, useState} from "react";
import {usePathname} from "next/navigation";

type ServiceKey = "run-job" | "operations" | "retainer";
type AssessmentMode = "express" | "comprehensive";

const ASSESSMENT_TIER_EVENT = "nico:assessment-tier-selected";

export const PRIMARY_SERVICES = [
  {
    key: "run-job" as ServiceKey,
    label: "Run Assessment",
    href: "/assessment?tier=express#assessment",
  },
] as const;

const SPANISH_PRIMARY_LABELS: Record<ServiceKey, string> = {
  "run-job": "Ejecutar evaluación",
  operations: "Operaciones (administrador)",
  retainer: "Servicio continuo",
};

const ADVANCED_GROUPS = [
  {
    label: "Operator workspaces",
    description: "Deployment administration and ongoing evidence refresh",
    links: [
      {label: "Operations (Admin)", href: "/operations"},
      {label: "Retainer Ops", href: "/retainer-ops"},
      {label: "Recovery", href: "/operations/recovery"},
      {label: "Backup & Restore", href: "/operations/backup-restore"},
    ],
  },
  {
    label: "Advanced evidence tools",
    description: "Use only when the standard assessment workspace is insufficient",
    links: [
      {label: "Scanner to Express", href: "/scanner-workflow"},
      {label: "Refresh Evidence", href: "/refresh-full-evidence"},
      {label: "Easy Mode", href: "/easy"},
      {label: "Guide", href: "/guided-workflow"},
    ],
  },
] as const;

const SPANISH_ADVANCED_GROUPS = [
  {
    label: "Espacios para operadores",
    description: "Administración del despliegue y actualización continua de evidencia",
    links: [
      {label: "Operaciones (administrador)", href: "/operations"},
      {label: "Servicio continuo", href: "/retainer-ops"},
      {label: "Recuperación", href: "/operations/recovery"},
      {label: "Respaldo y restauración", href: "/operations/backup-restore"},
    ],
  },
  {
    label: "Herramientas avanzadas de evidencia",
    description: "Úsalas solo cuando el espacio normal de evaluación no sea suficiente",
    links: [
      {label: "Escáner a Express", href: "/scanner-workflow"},
      {label: "Actualizar evidencia", href: "/refresh-full-evidence"},
      {label: "Modo fácil", href: "/easy"},
      {label: "Guía", href: "/guided-workflow"},
    ],
  },
] as const;

function normalizeAssessmentMode(value: string | null | undefined): AssessmentMode {
  return ["comprehensive", "mid", "full", "deep"].includes(String(value || "")) ? "comprehensive" : "express";
}

function serviceForPath(pathname: string, assessment: AssessmentMode): ServiceKey | "" {
  void assessment;
  if (pathname.startsWith("/assessment") || pathname.startsWith("/es/assessment")) return "run-job";
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

function linkIsActive(pathname: string, href: string): boolean {
  const target = href.split("?")[0].split("#")[0];
  if (target === "/operations") return pathname === "/operations";
  return pathname.startsWith(target);
}

export default function PrimaryNavigation() {
  const pathname = usePathname();
  const [assessment, setAssessment] = useState<AssessmentMode>("express");

  useEffect(() => {
    if (!pathname.startsWith("/assessment") && !pathname.startsWith("/es/assessment")) return;

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
  const spanishActive = pathname.startsWith("/es");
  const languageHref = spanishActive ? "/assessment?tier=express#assessment" : "/es/assessment?tier=express#assessment";
  const languageLabel = spanishActive ? "English" : "Español";
  const advancedGroups = spanishActive ? SPANISH_ADVANCED_GROUPS : ADVANCED_GROUPS;
  const advancedActive = activeService === "operations" || activeService === "retainer";

  return (
    <nav className="global-nav" aria-label={spanishActive ? "Navegación principal de NICO" : "NICO primary navigation"}>
      <div className="global-nav-inner">
        <a className="global-brand" href="/assessment?tier=express#assessment" aria-label={spanishActive ? "Inicio de NICO" : "NICO home"}>NICO</a>

        <div className="primary-service-links" data-primary-service-count="1">
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

        <details className={`nav-more${advancedActive ? " active" : ""}`}>
          <summary aria-label={spanishActive ? "Abrir herramientas para operadores y herramientas avanzadas" : "Open operator and advanced tools"}>{spanishActive ? "Más" : "More"}</summary>
          <div className="nav-more-panel" lang={spanishActive ? "es-MX" : undefined}>
            <div className="nav-more-heading">
              <b>{spanishActive ? "Operadores y herramientas avanzadas" : "Operator and advanced tools"}</b>
              <span>{spanishActive ? "La evaluación normal permanece en Ejecutar evaluación" : "The standard assessment remains under Run Assessment"}</span>
            </div>
            <div className="nav-more-groups">
              {advancedGroups.map((group) => (
                <section className="nav-more-group" key={group.label}>
                  <p>{group.label}</p>
                  <small>{group.description}</small>
                  {group.links.map((link) => {
                    const active = linkIsActive(pathname, link.href);
                    return <a href={link.href} key={link.href} aria-current={active ? "page" : undefined}>{link.label}</a>;
                  })}
                </section>
              ))}
            </div>
          </div>
        </details>
      </div>
    </nav>
  );
}
