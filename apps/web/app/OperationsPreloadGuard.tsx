"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const NOTE_ID = "nico-operations-not-loaded";

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
        if (index > authenticationIndex) section.hidden = !evidenceLoaded;
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
        note.textContent = "Operations evidence is not loaded. Enter the admin token and select Load operations. Unloaded cards are not failures and are not shown as red evidence states.";
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
      document.querySelectorAll<HTMLElement>("main > section[hidden]").forEach((section) => {
        section.hidden = false;
      });
    };
  }, [pathname]);

  return null;
}
