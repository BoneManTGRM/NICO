"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const NOTE_ID = "nico-operations-not-loaded";
const PRELOAD_PILL_ATTRIBUTE = "data-nico-preload-hidden";
const PRELOAD_SECTION_ATTRIBUTE = "data-nico-preload-section-hidden";

function setPreloadHidden(element: HTMLElement, hidden: boolean, attribute: string) {
  if (hidden) {
    element.setAttribute(attribute, "true");
    element.style.setProperty("display", "none", "important");
  } else if (element.hasAttribute(attribute)) {
    element.removeAttribute(attribute);
    element.style.removeProperty("display");
  }
}

export default function OperationsPreloadGuard() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname !== "/operations") return;

    let observer: MutationObserver | null = null;
    let frame = 0;
    let cancelled = false;

    const apply = () => {
      if (cancelled) return;
      const main = document.querySelector<HTMLElement>("main");
      if (!main) {
        frame = window.requestAnimationFrame(apply);
        return;
      }

      const sections = Array.from(main.querySelectorAll<HTMLElement>(":scope > section"));
      const authentication = sections.find((section) => section.textContent?.includes("Operator authentication"));
      if (!authentication) {
        frame = window.requestAnimationFrame(apply);
        return;
      }

      const evidenceLoaded = authentication.textContent?.includes("Last loaded:") === true;
      const authenticationIndex = sections.indexOf(authentication);
      sections.forEach((section, index) => {
        if (index > authenticationIndex) {
          setPreloadHidden(section, !evidenceLoaded, PRELOAD_SECTION_ATTRIBUTE);
        }
      });

      const preloadPills = Array.from(main.querySelectorAll<HTMLElement>("span")).filter((element) => {
        const text = String(element.textContent || "").trim().toLowerCase();
        return text === "readiness: not loaded" || text === "highest alert: not loaded";
      });
      preloadPills.forEach((element) => {
        setPreloadHidden(element, !evidenceLoaded, PRELOAD_PILL_ATTRIBUTE);
      });

      const existing = document.getElementById(NOTE_ID);
      if (evidenceLoaded) {
        existing?.remove();
        return;
      }
      if (!existing) {
        const note = document.createElement("p");
        note.id = NOTE_ID;
        note.className = "summary-box";
        note.textContent = "Operations evidence is not loaded. Enter the admin token and select Load operations. No readiness, release, storage, workload, incident, or alert state is inferred before authentication succeeds.";
        authentication.insertAdjacentElement("afterend", note);
      }
    };

    frame = window.requestAnimationFrame(apply);
    observer = new MutationObserver(apply);
    observer.observe(document.body, {childList: true, subtree: true});

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      document.getElementById(NOTE_ID)?.remove();
      document.querySelectorAll<HTMLElement>(`[${PRELOAD_SECTION_ATTRIBUTE}]`).forEach((section) => {
        setPreloadHidden(section, false, PRELOAD_SECTION_ATTRIBUTE);
      });
      document.querySelectorAll<HTMLElement>(`[${PRELOAD_PILL_ATTRIBUTE}]`).forEach((element) => {
        setPreloadHidden(element, false, PRELOAD_PILL_ATTRIBUTE);
      });
    };
  }, [pathname]);

  return null;
}
