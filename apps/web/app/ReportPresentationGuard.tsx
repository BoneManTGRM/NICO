"use client";

import {useEffect} from "react";

// Match only an actually empty score denominator. Numeric values such as 85/100
// must never be rewritten as NOT SCORED.
const EMPTY_SCORE = /(?:^|\s*·\s*)(?:null|undefined|nan)?\s*\/100\s*$/i;
const RAW_RUN_ID = /^(express_run_|midrun_|mid_run_|full_run_)[a-z0-9_-]+$/i;

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

function friendlyTierLabel(runId: string) {
  if (runId.toLowerCase().startsWith("express_run_")) return "Express Assessment";
  if (runId.toLowerCase().startsWith("full_run_")) return "Full Assessment";
  return "Mid Assessment";
}

function normalizeRunIdentity(root: ParentNode) {
  root.querySelectorAll<HTMLElement>("h1, h2, h3, p, span").forEach((element) => {
    const current = element.textContent?.trim() || "";
    if (!RAW_RUN_ID.test(current)) return;

    element.style.overflowWrap = "anywhere";
    element.style.wordBreak = "break-word";

    if (element.matches("h1, h2, h3")) {
      element.dataset.technicalRunId = current;
      element.title = `Technical run ID: ${current}`;
      element.textContent = `${friendlyTierLabel(current)} · Active authorized repository`;
    }
  });
}

function removeDuplicateDetail(root: ParentNode) {
  root.querySelectorAll<HTMLElement>(".result-card").forEach((card) => {
    // Paragraph summaries and semantic evidence/findings/unavailable lists are
    // different report fields. Deduplicate only within the same presentation
    // field so a finding identical to the card summary is not removed and left
    // behind as an empty `Findings (1)` disclosure.
    const seenParagraphs = new Set<string>();
    Array.from(card.querySelectorAll<HTMLParagraphElement>("p")).forEach((paragraph) => {
      const key = textKey(paragraph.textContent || "");
      if (!key || seenParagraphs.has(key)) paragraph.remove();
      else seenParagraphs.add(key);
    });

    card.querySelectorAll<HTMLElement>("details, ul, ol").forEach((container) => {
      const seenItems = new Set<string>();
      Array.from(container.querySelectorAll<HTMLLIElement>("li")).forEach((item) => {
        const key = textKey(item.textContent || "");
        if (!key || seenItems.has(key)) item.remove();
        else seenItems.add(key);
      });
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
  normalizeRunIdentity(document);
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
