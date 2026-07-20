"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const LEGACY_LABELS = new Set(["mid", "full", "deep"]);
const ASSESSMENT_PATHS = new Set(["/", "/assessment"]);
const DEFAULT_REPOSITORY = "BoneManTGRM/NICO";

function normalizeAssessmentQuery() {
  const url = new URL(window.location.href);
  const requested = String(url.searchParams.get("tier") || "").toLowerCase();
  if (!LEGACY_LABELS.has(requested)) return;
  url.searchParams.set("tier", "comprehensive");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function setNativeInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", {bubbles: true}));
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

function clearLegacyRepositoryDefault() {
  const input = document.querySelector<HTMLInputElement>('input[placeholder="owner/repo"]');
  if (!input || input.dataset.nicoDefaultCleared === "true") return;
  input.dataset.nicoDefaultCleared = "true";
  if (input.value === DEFAULT_REPOSITORY) setNativeInputValue(input, "");
}

function rewriteWorkspace(): HTMLElement | null {
  const selector = document.querySelector<HTMLElement>('[aria-label="Assessment type"]');
  if (!selector) return null;

  const buttons = Array.from(selector.querySelectorAll<HTMLButtonElement>("button"));
  if (buttons.length < 2) return selector;

  const express = buttons.find((button) => button.textContent?.trim().toLowerCase() === "express") || buttons[0];
  const comprehensive = buttons.find((button) => {
    const text = button.textContent?.trim().toLowerCase() || "";
    return text === "mid" || text === "full" || text === "deep" || text === "comprehensive";
  }) || buttons[1];

  express.textContent = "Express";
  express.hidden = false;
  express.disabled = false;
  express.removeAttribute("aria-hidden");
  express.dataset.nicoPublicService = "express";

  comprehensive.textContent = "Comprehensive";
  comprehensive.hidden = false;
  comprehensive.disabled = false;
  comprehensive.removeAttribute("aria-hidden");
  comprehensive.dataset.nicoPublicService = "comprehensive";
  comprehensive.setAttribute("aria-label", "Comprehensive technical assessment");

  for (const button of buttons) {
    if (button === express || button === comprehensive) continue;
    button.hidden = true;
    button.style.display = "none";
    button.disabled = true;
    button.setAttribute("aria-hidden", "true");
    button.tabIndex = -1;
    button.dataset.nicoLegacyServiceHidden = "true";
  }

  selector.dataset.nicoCustomerAssessmentCount = "2";
  clearLegacyRepositoryDefault();
  return selector;
}

export default function TwoServiceAssessmentGuard() {
  const pathname = usePathname();

  useEffect(() => {
    if (!ASSESSMENT_PATHS.has(pathname)) return;

    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    window.scrollTo({top: 0, left: 0, behavior: "instant" as ScrollBehavior});
    normalizeAssessmentQuery();

    let attempts = 0;
    let selectorObserver: MutationObserver | null = null;
    const install = () => {
      attempts += 1;
      const selector = rewriteWorkspace();
      if (selector) {
        selectorObserver = new MutationObserver(() => rewriteWorkspace());
        selectorObserver.observe(selector, {childList: true, subtree: true});
        return;
      }
      if (attempts < 40) window.setTimeout(install, 100);
    };
    install();

    return () => selectorObserver?.disconnect();
  }, [pathname]);

  return null;
}
