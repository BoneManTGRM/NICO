"use client";

import {useEffect} from "react";

// Match only an actually empty score denominator. Numeric values such as 85/100
// must never be rewritten as NOT SCORED.
const EMPTY_SCORE = /(?:^|\s*·\s*)(?:null|undefined|nan)?\s*\/100\s*$/i;
const RAW_RUN_ID = /^(express_run_|midrun_|mid_run_|full_run_|comprun_)[a-z0-9_-]+$/i;
const POLISH_STYLE_ID = "nico-comprehensive-ui-polish";
const ACTIVE_SCOPE_LABEL = "Active authorized repository";

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
  const normalized = runId.toLowerCase();
  if (normalized.startsWith("comprun_")) return "Comprehensive Run";
  if (normalized.startsWith("express_run_")) return "Express Run";
  if (normalized.startsWith("full_run_")) return "Full Run";
  return "Mid Run";
}

function normalizeRunIdentity(root: ParentNode) {
  root.querySelectorAll<HTMLElement>("h1, h2, h3, p, span").forEach((element) => {
    const current = element.textContent?.trim() || "";
    const title = element.getAttribute("title")?.trim() || "";
    const technicalRunId = RAW_RUN_ID.test(current) ? current : RAW_RUN_ID.test(title) ? title : "";
    if (!technicalRunId) return;

    element.style.overflowWrap = "anywhere";
    element.style.wordBreak = "break-word";

    if (element.matches("h1, h2, h3")) {
      const displayLabel = friendlyTierLabel(technicalRunId);
      element.dataset.technicalRunId = technicalRunId;
      element.title = `Technical run ID: ${technicalRunId}`;
      element.setAttribute("aria-label", `${displayLabel} · ${ACTIVE_SCOPE_LABEL}`);
      element.textContent = displayLabel;
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

function ensurePolishStyles() {
  if (document.getElementById(POLISH_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = POLISH_STYLE_ID;
  style.textContent = `
    main.shell[data-assessment-service-count] {
      max-width: 1180px;
      padding-bottom: 72px;
    }

    main.shell[data-assessment-service-count] .section.panel,
    main.shell[data-assessment-service-count] .result-card,
    main.shell[data-assessment-service-count] .target-grid article {
      min-width: 0;
      overflow: hidden;
    }

    main.shell[data-assessment-service-count] #assessment > .summary-box {
      max-width: 860px;
      margin: 16px 0 18px;
      padding: 18px 20px;
      line-height: 1.55;
    }

    main.shell[data-assessment-service-count] .results-grid {
      gap: 16px;
    }

    main.shell[data-assessment-service-count] .result-card {
      padding: 22px;
      border-radius: 20px;
    }

    main.shell[data-assessment-service-count] .result-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: start;
      gap: 14px;
    }

    main.shell[data-assessment-service-count] .result-head > b {
      min-width: 0;
      line-height: 1.2;
      text-wrap: balance;
    }

    main.shell[data-assessment-service-count] .result-head .status {
      max-width: 260px;
      white-space: normal;
      text-align: center;
      line-height: 1.2;
    }

    main.shell[data-assessment-service-count] .result-card p,
    main.shell[data-assessment-service-count] .result-card li,
    main.shell[data-assessment-service-count] .result-card pre,
    main.shell[data-assessment-service-count] .result-card code,
    main.shell[data-assessment-service-count] .help-details li,
    main.shell[data-assessment-service-count] .help-details pre {
      max-width: 100%;
      overflow-wrap: anywhere;
      word-break: break-word;
    }

    main.shell[data-assessment-service-count] .json-block {
      white-space: pre-wrap;
    }

    main.shell[data-assessment-service-count] .help-details {
      margin-top: 14px;
      border-radius: 16px;
      overflow: hidden;
    }

    main.shell[data-assessment-service-count] .help-details summary {
      padding: 14px 16px;
      line-height: 1.25;
    }

    main.shell[data-assessment-service-count] .report-actions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 12px;
      align-items: stretch;
    }

    main.shell[data-assessment-service-count] .report-actions button {
      width: 100%;
      min-height: 50px;
    }

    @media (max-width: 760px) {
      main.shell[data-assessment-service-count] {
        padding-inline: 10px;
        padding-bottom: 56px;
      }

      main.shell[data-assessment-service-count] .section.panel {
        padding: 20px 16px;
        border-radius: 20px;
      }

      main.shell[data-assessment-service-count] .section-head {
        gap: 12px;
      }

      main.shell[data-assessment-service-count] .section-head h2 {
        max-width: 100%;
        font-size: clamp(28px, 8.5vw, 38px);
        line-height: 1.08;
        overflow-wrap: anywhere;
      }

      main.shell[data-assessment-service-count] #assessment > .summary-box {
        margin: 12px 0 16px;
        padding: 16px;
        font-size: 17px;
        line-height: 1.5;
      }

      main.shell[data-assessment-service-count] .results-grid {
        gap: 14px;
      }

      main.shell[data-assessment-service-count] .result-card {
        padding: 20px 16px;
        border-radius: 18px;
      }

      main.shell[data-assessment-service-count] .result-head {
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 10px;
      }

      main.shell[data-assessment-service-count] .result-head > b {
        font-size: clamp(22px, 6vw, 28px);
      }

      main.shell[data-assessment-service-count] .result-head .status {
        max-width: 46vw;
        padding: 9px 12px;
        font-size: 13px;
        letter-spacing: 0.06em;
      }

      main.shell[data-assessment-service-count] .result-card > p,
      main.shell[data-assessment-service-count] .result-card li {
        font-size: 17px;
        line-height: 1.55;
      }

      main.shell[data-assessment-service-count] .help-details summary {
        padding: 13px 14px;
        font-size: 17px;
      }

      main.shell[data-assessment-service-count] .help-details ul,
      main.shell[data-assessment-service-count] .help-details ol,
      main.shell[data-assessment-service-count] .help-details pre {
        margin-inline: 14px;
        padding-left: 18px;
      }

      main.shell[data-assessment-service-count] .report-actions {
        grid-template-columns: 1fr;
        margin-top: 18px;
        padding: 0;
        border: 0;
        background: transparent;
      }

      main.shell[data-assessment-service-count] .report-actions button {
        min-height: 54px;
        border-radius: 14px;
      }
    }
  `;
  document.head.appendChild(style);
}

function normalizePresentation() {
  ensurePolishStyles();
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
