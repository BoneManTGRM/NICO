"use client";

import {useEffect} from "react";

const combinedScorePattern = /^(GREEN|YELLOW|RED)\s*[·•-]\s*(\d{1,3})\s*\/\s*100$/i;
const combinedNotScoredPattern = /^(SUPPLEMENTAL|GRAY)\s*[·•-]\s*NOT\s+SCORED$/i;
const separatedScorePattern = /^(EXCEPTIONAL|STRONG|MODERATE|WEAK|CRITICAL)\s*[·•-]\s*(\d{1,3})\s*\/\s*100$/i;

type Tone = "green" | "yellow" | "red" | "gray" | "blue";

function technicalBand(score: number): {label: string; tone: Tone} {
  if (score >= 90) return {label: "EXCEPTIONAL", tone: "green"};
  if (score >= 80) return {label: "STRONG", tone: "green"};
  if (score >= 70) return {label: "MODERATE", tone: "yellow"};
  if (score >= 55) return {label: "WEAK", tone: "red"};
  return {label: "CRITICAL", tone: "red"};
}

function assurance(status: string): {label: string; tone: Tone} {
  const normalized = status.toUpperCase();
  if (normalized === "GREEN") return {label: "VERIFIED", tone: "green"};
  if (normalized === "YELLOW") return {label: "REVIEW LIMITED", tone: "yellow"};
  if (normalized === "SUPPLEMENTAL") return {label: "SUPPLEMENTAL", tone: "blue"};
  if (normalized === "GRAY") return {label: "HUMAN REVIEW PENDING", tone: "gray"};
  return {label: "BLOCKED", tone: "red"};
}

function applyTone(element: HTMLElement, tone: Tone): void {
  element.classList.remove("green", "yellow", "red", "gray", "blue");
  element.classList.add(tone);
}

function removeOldAssurance(badge: HTMLElement): void {
  const parent = badge.parentElement;
  if (!parent) return;
  parent.querySelectorAll<HTMLElement>('[data-nico-assurance-for="score-badge"]').forEach((item) => item.remove());
}

function appendAssurance(badge: HTMLElement, canonicalStatus: string): void {
  const evidenceAssurance = assurance(canonicalStatus);
  const assuranceBadge = document.createElement("span");
  assuranceBadge.className = `status ${evidenceAssurance.tone} assurance-badge`;
  assuranceBadge.textContent = evidenceAssurance.label;
  assuranceBadge.dataset.nicoAssuranceFor = "score-badge";
  assuranceBadge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
  assuranceBadge.setAttribute("aria-label", `Evidence assurance: ${evidenceAssurance.label.toLowerCase()}`);
  badge.insertAdjacentElement("afterend", assuranceBadge);
  badge.parentElement?.classList.add("score-assurance-badges");
}

function splitBadge(badge: HTMLElement): void {
  if (badge.dataset.nicoAssuranceFor === "score-badge") return;
  const text = (badge.textContent || "").replace(/\s+/g, " ").trim();
  const scoreMatch = text.match(combinedScorePattern);
  if (scoreMatch) {
    const canonicalStatus = scoreMatch[1].toUpperCase();
    const score = Math.max(0, Math.min(100, Number(scoreMatch[2])));
    const band = technicalBand(score);
    removeOldAssurance(badge);
    badge.textContent = `${band.label} · ${score}/100`;
    badge.dataset.nicoScoreBand = band.label.toLowerCase();
    badge.dataset.nicoTechnicalScore = String(score);
    badge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    badge.setAttribute("aria-label", `Technical score ${score} out of 100, ${band.label.toLowerCase()}`);
    applyTone(badge, band.tone);
    appendAssurance(badge, canonicalStatus);
    return;
  }

  const notScoredMatch = text.match(combinedNotScoredPattern);
  if (notScoredMatch) {
    const canonicalStatus = notScoredMatch[1].toUpperCase();
    removeOldAssurance(badge);
    badge.textContent = "NOT SCORED";
    badge.dataset.nicoScoreBand = "not-scored";
    badge.dataset.nicoCanonicalStatus = canonicalStatus.toLowerCase();
    badge.setAttribute("aria-label", "Technical score: not scored");
    applyTone(badge, "gray");
    appendAssurance(badge, canonicalStatus);
    return;
  }

  const separatedMatch = text.match(separatedScorePattern);
  if (separatedMatch && !badge.nextElementSibling?.matches('[data-nico-assurance-for="score-badge"]')) {
    const canonicalStatus = String(badge.dataset.nicoCanonicalStatus || "").toUpperCase();
    if (canonicalStatus) appendAssurance(badge, canonicalStatus);
  }
}

function processDocument(): void {
  document.querySelectorAll<HTMLElement>(".status").forEach(splitBadge);
}

export default function AssessmentScoreAssuranceGuard() {
  useEffect(() => {
    let frame = 0;
    let scheduled = false;
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      frame = requestAnimationFrame(() => {
        scheduled = false;
        processDocument();
      });
    };

    schedule();
    const observer = new MutationObserver(() => schedule());
    observer.observe(document.body, {subtree: true, childList: true, characterData: true});
    window.addEventListener("pageshow", schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pageshow", schedule);
    };
  }, []);

  return null;
}
