"use client";

import {useEffect} from "react";

const combinedScorePattern = /^(GREEN|YELLOW|RED)\s*[·•-]\s*(\d{1,3})\s*\/\s*100$/i;
const combinedNotScoredPattern = /^(SUPPLEMENTAL|GRAY)\s*[·•-]\s*NOT\s+SCORED$/i;

function technicalBand(score: number) {
  if (score >= 90) return {label: "EXCEPTIONAL", tone: "green"};
  if (score >= 80) return {label: "STRONG", tone: "green"};
  if (score >= 70) return {label: "MODERATE", tone: "yellow"};
  if (score >= 55) return {label: "WEAK", tone: "red"};
  return {label: "CRITICAL", tone: "red"};
}

function assurance(status: string) {
  const normalized = status.toUpperCase();
  if (normalized === "GREEN") return {label: "VERIFIED", tone: "green"};
  if (normalized === "YELLOW") return {label: "REVIEW LIMITED", tone: "yellow"};
  return {label: "BLOCKED", tone: "red"};
}

function removeOldAssurance(badge: HTMLElement) {
  const sibling = badge.nextElementSibling;
  if (sibling instanceof HTMLElement && sibling.dataset.nicoAssuranceFor === "score-badge") {
    sibling.remove();
  }
}

function applyTone(element: HTMLElement, tone: string) {
  element.classList.remove("green", "yellow", "red", "gray", "blue");
  element.classList.add(tone);
}

function splitBadge(badge: HTMLElement) {
  const text = (badge.textContent || "").replace(/\s+/g, " ").trim();
  const scoreMatch = text.match(combinedScorePattern);
  if (scoreMatch) {
    removeOldAssurance(badge);
    const canonicalStatus = scoreMatch[1].toUpperCase();
    const score = Math.max(0, Math.min(100, Number(scoreMatch[2])));
    const band = technicalBand(score);
    const evidenceAssurance = assurance(canonicalStatus);

    badge.textContent = `${band.label} · ${score}/100`;
    badge.dataset.nicoScoreBand = band.label.toLowerCase();
    badge.dataset.nicoTechnicalScore = String(score);
    badge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    badge.setAttribute("aria-label", `Technical score ${score} out of 100, ${band.label.toLowerCase()}`);
    applyTone(badge, band.tone);

    const assuranceBadge = document.createElement("span");
    assuranceBadge.className = `status ${evidenceAssurance.tone} assurance-badge`;
    assuranceBadge.textContent = evidenceAssurance.label;
    assuranceBadge.dataset.nicoAssuranceFor = "score-badge";
    assuranceBadge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    assuranceBadge.setAttribute("aria-label", `Evidence assurance: ${evidenceAssurance.label.toLowerCase()}`);
    badge.insertAdjacentElement("afterend", assuranceBadge);
    badge.parentElement?.classList.add("score-assurance-badges");
    return;
  }

  const notScoredMatch = text.match(combinedNotScoredPattern);
  if (notScoredMatch) {
    removeOldAssurance(badge);
    const canonicalStatus = notScoredMatch[1].toUpperCase();
    badge.textContent = "NOT SCORED";
    badge.dataset.nicoScoreBand = "not-scored";
    badge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    badge.setAttribute("aria-label", "Technical score: not scored");
    applyTone(badge, "gray");

    const assuranceBadge = document.createElement("span");
    const isSupplemental = canonicalStatus === "SUPPLEMENTAL";
    assuranceBadge.className = `status ${isSupplemental ? "blue" : "gray"} assurance-badge`;
    assuranceBadge.textContent = isSupplemental ? "SUPPLEMENTAL" : "HUMAN REVIEW PENDING";
    assuranceBadge.dataset.nicoAssuranceFor = "score-badge";
    assuranceBadge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    badge.insertAdjacentElement("afterend", assuranceBadge);
    badge.parentElement?.classList.add("score-assurance-badges");
  }
}

function processRoot(root: ParentNode) {
  if (root instanceof HTMLElement && root.matches(".status")) splitBadge(root);
  root.querySelectorAll<HTMLElement>(".status").forEach(splitBadge);
}

export default function AssessmentScoreAssuranceGuard() {
  useEffect(() => {
    let frame = 0;
    const schedule = (root: ParentNode = document) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => processRoot(root));
    };

    schedule(document);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData" && mutation.target.parentElement) {
          schedule(mutation.target.parentElement);
          return;
        }
        for (const node of mutation.addedNodes) {
          if (node instanceof HTMLElement) {
            schedule(node);
            return;
          }
        }
      }
    });
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return null;
}
