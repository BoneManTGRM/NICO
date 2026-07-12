"use client";

import {useEffect} from "react";

// Match only an actually empty score denominator. Numeric values such as 85/100
// must never be rewritten as NOT SCORED.
const EMPTY_SCORE = /(?:^|\s*·\s*)(?:null|undefined|nan)?\s*\/100\s*$/i;

function textKey(value: string) {
  return value.trim().replace(/\s+/g, " ").toLowerCase().replace(/[.;:]+$/, "");
}

function normalizeScoreLabels(root: ParentNode) {
  root.querySelectorAll<HTMLElement>(".result-head .status").forEach((element) => {
    const current = element.textContent?.trim() || "";
    if (!EMPTY_SCORE.test(current)) return;
    const status = current.replace(EMPTY_SCORE, "").replace(/·\s*$/, "").trim();
    const replacement = status ? `${status} · NOT SCORED` : "NOT SCORED";
    if (current !== replacement) element.textContent = replacement;
  });
}

function removeDuplicateDetail(root: ParentNode) {
  root.querySelectorAll<HTMLElement>(".result-card").forEach((card) => {
    // Use one set in document order so a summary paragraph is retained and an
    // identical later limitation bullet is removed. Separate paragraph/list sets
    // allowed the same sentence to appear twice in the screenshots for Issue #296.
    const seenDetail = new Set<string>();
    Array.from(card.querySelectorAll<HTMLElement>("p, li")).forEach((element) => {
      const key = textKey(element.textContent || "");
      if (!key || seenDetail.has(key)) element.remove();
      else seenDetail.add(key);
    });
  });
}

function collapseMobileDetail(root: ParentNode) {
  if (!window.matchMedia("(max-width: 900px)").matches) return;
  root.querySelectorAll<HTMLDetailsElement>("details.result-card[open], #mid-evidence-console details.result-card[open]").forEach((detail) => {
    detail.removeAttribute("open");
  });
}

function normalizePresentation() {
  normalizeScoreLabels(document);
  removeDuplicateDetail(document);
  collapseMobileDetail(document);
}

export default function ReportPresentationGuard() {
  useEffect(() => {
    normalizePresentation();
    let queued = false;
    const observer = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(() => {
        queued = false;
        normalizePresentation();
      });
    });
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    window.addEventListener("resize", normalizePresentation);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", normalizePresentation);
    };
  }, []);

  return null;
}
