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

  return (
    <nav className="global-nav" aria-label="NICO primary navigation">
      <div className="global-nav-inner">
        <a className="global-brand" href="/assessment?tier=express#assessment" aria-label="NICO home">NICO</a>

        <div className="primary-service-links" data-primary-service-count="3">
          {PRIMARY_SERVICES.map((service) => {
            const active = activeService === service.key;
            return (
              <a
                key={service.key}
                className={`primary-service-link${active ? " active" : ""}`}
                href={service.href}
                aria-current={active ? "page" : undefined}
                data-service={service.key}
              >
                <span className="primary-service-label">{service.label}</span>
                <span className="primary-service-short-label">{service.shortLabel}</span>
              </a>
            );
          })}
        </div>

        <a
          className={`primary-service-link${spanishActive ? " active" : ""}`}
          href="/es-mx"
          hrefLang="es-MX"
          lang="es-MX"
          aria-current={spanishActive ? "page" : undefined}
        >
          <span className="primary-service-label">Español</span>
          <span className="primary-service-short-label">ES</span>
        </a>

        <details className="nav-more">
          <summary aria-label="Open advanced NICO tools">More</summary>
          <div className="nav-more-panel">
            <div className="nav-more-heading">
              <b>Advanced tools</b>
              <span>Operator diagnostics and utilities</span>
            </div>
            <div className="nav-more-groups">
              {ADVANCED_GROUPS.map((group) => (
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
