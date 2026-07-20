"use client";

import {useEffect} from "react";
import {usePathname} from "next/navigation";

const LEGACY_LABELS = new Set(["mid", "full", "deep"]);

function normalizeAssessmentQuery() {
  const url = new URL(window.location.href);
  const requested = String(url.searchParams.get("tier") || "").toLowerCase();
  if (!LEGACY_LABELS.has(requested)) return;
  url.searchParams.set("tier", "comprehensive");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function rewriteWorkspace() {
  const selector = document.querySelector<HTMLElement>('[aria-label="Assessment type"]');
  if (!selector) return;

  const buttons = Array.from(selector.querySelectorAll<HTMLButtonElement>("button"));
  if (buttons.length < 2) return;

  const express = buttons.find((button) => button.textContent?.trim().toLowerCase() === "express") || buttons[0];
  const comprehensive = buttons.find((button) => {
    const text = button.textContent?.trim().toLowerCase() || "";
    return text === "mid" || text === "full" || text === "deep" || text === "comprehensive";
  }) || buttons[1];

  express.textContent = "Express";
  express.dataset.nicoPublicService = "express";

  comprehensive.textContent = "Comprehensive";
  comprehensive.dataset.nicoPublicService = "comprehensive";
  comprehensive.setAttribute("aria-label", "Comprehensive technical assessment");

  for (const button of buttons) {
    if (button === express || button === comprehensive) continue;
    button.hidden = true;
    button.setAttribute("aria-hidden", "true");
    button.tabIndex = -1;
    button.dataset.nicoLegacyServiceHidden = "true";
  }

  selector.dataset.nicoCustomerAssessmentCount = "2";

  const replacements: Array<[RegExp, string]> = [
    [/\bMid Assessment\b/g, "Comprehensive Assessment"],
    [/\bFull Assessment\b/g, "Comprehensive Assessment"],
    [/\bMID ASSESSMENT\b/g, "COMPREHENSIVE ASSESSMENT"],
    [/\bFULL ASSESSMENT\b/g, "COMPREHENSIVE ASSESSMENT"],
    [/\bMid run\b/g, "Comprehensive run"],
    [/\bUnified Mid run\b/g, "Unified Comprehensive run"],
    [/\bCheck Mid status\b/g, "Check Comprehensive status"],
    [/\bRun fresh Mid assessment\b/g, "Run Comprehensive assessment"],
    [/\bRun fresh Full assessment\b/g, "Run Comprehensive assessment"],
  ];

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const parent = node.parentElement;
    if (parent && !["SCRIPT", "STYLE", "TEXTAREA", "OPTION"].includes(parent.tagName)) {
      let value = node.textContent || "";
      for (const [pattern, replacement] of replacements) value = value.replace(pattern, replacement);
      if (value !== node.textContent) node.textContent = value;
    }
    node = walker.nextNode();
  }
}

export default function TwoServiceAssessmentGuard() {
  const pathname = usePathname();

  useEffect(() => {
    if (pathname !== "/assessment") return;
    normalizeAssessmentQuery();
    rewriteWorkspace();

    const observer = new MutationObserver(() => rewriteWorkspace());
    observer.observe(document.body, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, [pathname]);

  return null;
}
