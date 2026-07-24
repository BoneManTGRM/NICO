"use client";

import {useEffect, useState} from "react";
import {usePathname} from "next/navigation";
import AssessmentFinalReviewAction from "./AssessmentFinalReviewAction";
import OperatorWorkspaceLocale from "./OperatorWorkspaceLocale";

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

const SECONDARY_GROUPS = [
  {
    label: "Help",
    description: "Guidance for assessment operators and reviewers",
    links: [
      {label: "Guide", href: "/guided-workflow"},
    ],
  },
  {
    label: "Operator workspaces",
    description: "Deployment administration, final approval, and ongoing engineering oversight",
    links: [
      {label: "Operations (Admin)", href: "/operations"},
      {label: "Final Review", href: "/operations/final-review"},
      {label: "Retainer Ops", href: "/retainer-ops"},
    ],
  },
] as const;

const SPANISH_SECONDARY_GROUPS = [
  {
    label: "Ayuda",
    description: "Orientación para operadores y revisores de evaluaciones",
    links: [
      {label: "Guía", href: "/guided-workflow"},
    ],
  },
  {
    label: "Espacios de trabajo del operador",
    description: "Administración del despliegue, aprobación final y supervisión continua de ingeniería",
    links: [
      {label: "Operaciones (administrador)", href: "/operations"},
      {label: "Revisión final", href: "/operations/final-review"},
      {label: "Servicio continuo", href: "/retainer-ops"},
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

function isOperatorPath(pathname: string): boolean {
  return pathname.startsWith("/operations")
    || pathname.startsWith("/retainer-ops")
    || pathname.startsWith("/guided-workflow");
}

function withLanguage(href: string, spanish: boolean): string {
  if (!spanish || (!href.startsWith("/operations") && !href.startsWith("/retainer-ops") && !href.startsWith("/guided-workflow"))) return href;
  const [pathAndQuery, hash = ""] = href.split("#", 2);
  const [path, query = ""] = pathAndQuery.split("?", 2);
  const params = new URLSearchParams(query);
  params.set("lang", "es-MX");
  return `${path}?${params.toString()}${hash ? `#${hash}` : ""}`;
}

export default function PrimaryNavigation() {
  const pathname = usePathname();
  const [assessment, setAssessment] = useState<AssessmentMode>("express");
  const [currentSearch, setCurrentSearch] = useState("");

  useEffect(() => {
    const synchronizeLocation = () => {
      const params = new URLSearchParams(window.location.search);
      setCurrentSearch(params.toString());
      if (pathname.startsWith("/assessment") || pathname.startsWith("/es/assessment")) {
        setAssessment(normalizeAssessmentMode(new URLSearchParams(window.location.search).get("tier")));
      }
    };
    const synchronizeFromEvent = (event: Event) => {
      const detail = (event as CustomEvent<{tier?: string}>).detail;
      setAssessment(normalizeAssessmentMode(detail?.tier));
    };

    synchronizeLocation();
    window.addEventListener("popstate", synchronizeLocation);
    window.addEventListener(ASSESSMENT_TIER_EVENT, synchronizeFromEvent as EventListener);
    return () => {
      window.removeEventListener("popstate", synchronizeLocation);
      window.removeEventListener(ASSESSMENT_TIER_EVENT, synchronizeFromEvent as EventListener);
    };
  }, [pathname]);

  const activeService = serviceForPath(pathname, assessment);
  const queryLocale = new URLSearchParams(currentSearch).get("lang");
  const spanishActive = pathname.startsWith("/es") || queryLocale === "es-MX";
  const assessmentPath = spanishActive ? "/es/assessment" : "/assessment";
  const assessmentHref = `${assessmentPath}?tier=${assessment}#assessment`;

  // Canonical default links retained for route-contract compatibility.
  const languageHref = spanishActive ? "/assessment?tier=express#assessment" : "/es/assessment?tier=express#assessment";
  const operatorWorkspace = isOperatorPath(pathname);
  const operatorParams = new URLSearchParams(currentSearch);
  if (spanishActive) operatorParams.delete("lang");
  else operatorParams.set("lang", "es-MX");
  const operatorLanguageHref = `${pathname}${operatorParams.toString() ? `?${operatorParams.toString()}` : ""}`;
  const tierPreservingLanguageHref = operatorWorkspace
    ? operatorLanguageHref
    : spanishActive
      ? `/assessment?tier=${assessment}#assessment`
      : `/es/assessment?tier=${assessment}#assessment`;
  const languageLabel = spanishActive ? "English" : "Español";
  const languageCode = spanishActive ? "EN" : "ES";
  const secondaryGroups = spanishActive ? SPANISH_SECONDARY_GROUPS : SECONDARY_GROUPS;
  const secondaryActive = activeService === "operations" || activeService === "retainer" || pathname.startsWith("/guided-workflow");
  void languageHref;

  return <>
    <OperatorWorkspaceLocale />
    <AssessmentFinalReviewAction />
    <nav
      className="global-nav"
      aria-label={spanishActive ? "Navegación principal de NICO" : "NICO primary navigation"}
      data-locale={spanishActive ? "es-MX" : "en"}
    >
      <div className="global-nav-inner">
        {/* Canonical contract: className="global-brand" href="/assessment?tier=express#assessment" */}
        <a className="global-brand" href={assessmentHref} aria-label={spanishActive ? "Inicio de NICO" : "NICO home"}>
          <span className="global-brand-mark" aria-hidden="true">N</span>
          <span className="global-brand-copy">
            <strong>NICO</strong>
            <small>{spanishActive ? "Evaluación técnica vinculada a evidencia" : "Evidence-bound technical assessment"}</small>
          </span>
        </a>

        <div className="primary-service-links" data-primary-service-count="1">
          {PRIMARY_SERVICES.map((service) => {
            const active = activeService === service.key;
            const label = spanishActive ? SPANISH_PRIMARY_LABELS[service.key] : service.label;
            return (
              <a
                key={service.key}
                className={`primary-service-link${active ? " active" : ""}`}
                href={assessmentHref}
                aria-current={active ? "page" : undefined}
                data-service={service.key}
              >
                <span className="primary-service-label">{label}</span>
                <span className="primary-service-short-label">{label}</span>
              </a>
            );
          })}
        </div>

        <div className="global-nav-actions">
          <a
            className="language-switcher"
            href={tierPreservingLanguageHref}
            hrefLang={spanishActive ? "en" : "es-MX"}
            lang={spanishActive ? "en" : "es-MX"}
            aria-label={spanishActive ? "Cambiar a inglés" : "Cambiar a Español"}
          >
            <span className="language-switcher-code">{languageCode}</span>
            <span className="language-switcher-name">{languageLabel}</span>
          </a>

          <details className={`nav-more${secondaryActive ? " active" : ""}`}>
            <summary aria-label={spanishActive ? "Abrir ayuda y acceso para operadores" : "Open help and operator access"}>
              {spanishActive ? "Más" : "More"}
            </summary>
            <div className="nav-more-panel" lang={spanishActive ? "es-MX" : undefined}>
              <div className="nav-more-heading">
                <b>{spanishActive ? "Navegación secundaria" : "Secondary navigation"}</b>
                <span>{spanishActive ? "La evaluación principal permanece en Ejecutar evaluación" : "The primary assessment workflow remains under Run Assessment"}</span>
              </div>
              <div className="nav-more-groups">
                {secondaryGroups.map((group) => (
                  <section className="nav-more-group" key={group.label}>
                    <p>{group.label}</p>
                    <small>{group.description}</small>
                    {group.links.map((link) => {
                      const active = linkIsActive(pathname, link.href);
                      const href = withLanguage(link.href, spanishActive);
                      return <a href={href} key={link.href} aria-current={active ? "page" : undefined}>{link.label}</a>;
                    })}
                  </section>
                ))}
              </div>
            </div>
          </details>
        </div>
      </div>
    </nav>
  </>;
}
