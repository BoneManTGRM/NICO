"use client";

import {useEffect, useState} from "react";
import {usePathname} from "next/navigation";

type ServiceKey = "express" | "mid" | "full" | "operations" | "retainer";

export const PRIMARY_SERVICES = [
  {
    key: "express" as ServiceKey,
    label: "Express Assessment",
    shortLabel: "Express",
    href: "/?assessment=express#assessment",
  },
  {
    key: "mid" as ServiceKey,
    label: "Mid Assessment",
    shortLabel: "Mid",
    href: "/?assessment=mid#assessment",
  },
  {
    key: "full" as ServiceKey,
    label: "Full Assessment",
    shortLabel: "Full",
    href: "/full-run",
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
    label: "Mid workflow",
    links: [
      {label: "Mid Review", href: "/mid-review"},
      {label: "Mid Report", href: "/mid-report"},
      {label: "Mid Approval", href: "/mid-approval"},
      {label: "Mid Delivery", href: "/mid-delivery-admin"},
    ],
  },
  {
    label: "Operations and diagnostics",
    links: [
      {label: "Recovery", href: "/operations/recovery"},
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

function serviceForPath(pathname: string, assessment: string): ServiceKey | "" {
  if (pathname === "/") return assessment === "mid" ? "mid" : "express";
  if (pathname.startsWith("/full-run")) return "full";
  if (pathname.startsWith("/operations")) return "operations";
  if (pathname.startsWith("/retainer-ops")) return "retainer";
  if (
    pathname.startsWith("/mid-review")
    || pathname.startsWith("/mid-report")
    || pathname.startsWith("/mid-approval")
    || pathname.startsWith("/mid-delivery-admin")
  ) return "mid";
  if (
    pathname.startsWith("/scanner-workflow")
    || pathname.startsWith("/refresh-full-evidence")
  ) return "express";
  return "";
}

export default function PrimaryNavigation() {
  const pathname = usePathname();
  const [assessment, setAssessment] = useState("express");

  useEffect(() => {
    if (pathname !== "/") return;
    const requested = new URLSearchParams(window.location.search).get("assessment");
    setAssessment(requested === "mid" ? "mid" : "express");
  }, [pathname]);

  const activeService = serviceForPath(pathname, assessment);

  return (
    <nav className="global-nav" aria-label="NICO primary navigation">
      <div className="global-nav-inner">
        <a className="global-brand" href="/" aria-label="NICO home">NICO</a>

        <div className="primary-service-links" data-primary-service-count="5">
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

        <details className="nav-more">
          <summary aria-label="Open advanced NICO tools">More</summary>
          <div className="nav-more-panel">
            <div className="nav-more-heading">
              <b>Advanced tools</b>
              <span>Workflow stages and operator utilities</span>
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
