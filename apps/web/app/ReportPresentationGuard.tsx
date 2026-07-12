"use client";

import {useEffect} from "react";

const EMPTY_SCORE = /(?:\s*·\s*)?(?:null|undefined|nan)?\s*\/100\s*$/i;

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
    const listItems = Array.from(card.querySelectorAll<HTMLLIElement>("li"));
    const seenItems = new Set<string>();
    listItems.forEach((item) => {
      const key = textKey(item.textContent || "");
      if (!key || seenItems.has(key)) item.remove();
      else seenItems.add(key);
    });

    const paragraphs = Array.from(card.querySelectorAll<HTMLParagraphElement>("p"));
    const seenParagraphs = new Set<string>();
    paragraphs.forEach((paragraph) => {
      const key = textKey(paragraph.textContent || "");
      if (!key || seenParagraphs.has(key)) paragraph.remove();
      else seenParagraphs.add(key);
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
