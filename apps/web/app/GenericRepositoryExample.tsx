"use client";

import {useEffect} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const PRIVATE_DEFAULTS = new Set(["BoneManTGRM/NICO", "bonemantgrm/nico"]);
const GENERIC_REPOSITORY_EXAMPLE = "your-org/your-repo";
const HERO_COPY = {
  eyebrow: "NICO Platform",
  poweredBy: "Powered by Reparodynamics",
  title: "NICO",
  lead: "Repair intelligence for authorized systems. Evidence-bound assessments, scanner workflows, client-ready reports, and approval-gated repair planning.",
  actions: ["Run Assessment", "Scanner Worker", "Repair Intelligence", "How to Use"],
};

let runtimeOpsStylesInjected = false;

type RuntimeConfig = {
  hero_eyebrow?: string;
  hero_powered_by?: string;
  hero_headline?: string;
  hero_lead?: string;
  default_repository_example?: string;
  primary_cta?: string;
  secondary_cta?: string;
  maintenance_banner?: string;
  source?: string;
  version?: number;
  feature_flags?: Record<string, boolean>;
};

function escapeHtml(value: unknown) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char] || char)); }
function setNativeInputValue(input: HTMLInputElement, value: string) { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set; setter?.call(input, value); input.dispatchEvent(new Event("input", {bubbles: true})); input.dispatchEvent(new Event("change", {bubbles: true})); }
function applyGenericRepositoryExample(example = GENERIC_REPOSITORY_EXAMPLE) { document.querySelectorAll<HTMLInputElement>("input").forEach((input) => { const value = input.value.trim(); if (PRIVATE_DEFAULTS.has(value)) setNativeInputValue(input, example); if (input.placeholder === "owner/repo" || input.placeholder === GENERIC_REPOSITORY_EXAMPLE) input.placeholder = example; }); }

function ensureRuntimeOpsStyles() {
  if (runtimeOpsStylesInjected || typeof document === "undefined") return;
  runtimeOpsStylesInjected = true;
  const style = document.createElement("style");
  style.dataset.nicoRuntimeOps = "true";
  style.textContent = `
    #runtime-commercial-ops { overflow: hidden; max-width: 100%; }
    #runtime-commercial-ops, #runtime-commercial-ops * { box-sizing: border-box; }
    #runtime-commercial-ops .section-head, #runtime-commercial-ops .inset-grid, #runtime-commercial-ops .mini-panel, #runtime-commercial-ops .help-body { min-width: 0; max-width: 100%; }
    #runtime-commercial-ops .two-col.inset-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1rem; overflow: hidden; }
    #runtime-commercial-ops .mini-panel { overflow: hidden; }
    #runtime-commercial-ops .json-block { display: block; width: 100%; max-width: 100%; min-width: 0; overflow-x: auto; overflow-y: hidden; white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }
    #runtime-commercial-ops .trend-card { display: grid; gap: .6rem; width: 100%; max-width: 100%; min-width: 0; overflow: hidden; }
    #runtime-commercial-ops .trend-row { display: grid; grid-template-columns: minmax(0, 7rem) minmax(0, 1fr); gap: .75rem; align-items: start; min-width: 0; max-width: 100%; }
    #runtime-commercial-ops .trend-key { color: #7dd3fc; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; font-size: .76rem; }
    #runtime-commercial-ops .trend-value { min-width: 0; max-width: 100%; overflow-wrap: anywhere; word-break: break-word; color: inherit; }
    @media (max-width: 640px) { #runtime-commercial-ops .trend-row { grid-template-columns: 1fr; gap: .22rem; } }
  `;
  document.head.appendChild(style);
}

function safeHeroHeadline(config?: RuntimeConfig) {
  const configured = (config?.hero_headline || "").trim();
  if (!configured) return HERO_COPY.title;
  const lowered = configured.toLowerCase();
  if (lowered.includes("repair intelligence") || lowered.includes("authorized systems")) return HERO_COPY.title;
  return configured;
}

function ensurePoweredByLine(hero: HTMLElement, eyebrow: HTMLElement | null, text: string) {
  let powered = hero.querySelector<HTMLElement>(".hero-powered-by");
  if (!powered) {
    powered = document.createElement("p");
    powered.className = "hero-powered-by";
    if (eyebrow?.nextSibling) eyebrow.parentNode?.insertBefore(powered, eyebrow.nextSibling);
    else hero.insertBefore(powered, hero.querySelector("h1"));
  }
  powered.textContent = text;
  powered.style.margin = "0.45rem 0 1rem";
  powered.style.fontSize = "clamp(1.2rem, 4.8vw, 2rem)";
  powered.style.lineHeight = "1.08";
  powered.style.letterSpacing = "0.18em";
  powered.style.textTransform = "uppercase";
  powered.style.fontWeight = "950";
  powered.style.color = "#67e8f9";
  powered.style.textShadow = "0 0 22px rgba(103,232,249,0.5)";
}

function styleHero(hero: HTMLElement, eyebrow: HTMLElement | null, title: HTMLElement | null, lead: HTMLElement | null) {
  hero.style.paddingTop = "clamp(2.9rem, 7vw, 5.5rem)";
  hero.style.paddingBottom = "clamp(2.6rem, 6vw, 4.8rem)";
  if (eyebrow) {
    eyebrow.style.margin = "0";
    eyebrow.style.fontSize = "clamp(0.9rem, 2.9vw, 1.2rem)";
    eyebrow.style.lineHeight = "1.1";
    eyebrow.style.letterSpacing = "0.22em";
    eyebrow.style.fontWeight = "900";
    eyebrow.style.color = "#38bdf8";
  }
  if (title) {
    title.style.margin = "0.85rem 0 0";
    title.style.fontSize = "clamp(5.4rem, 26vw, 12rem)";
    title.style.lineHeight = "0.82";
    title.style.letterSpacing = "0.08em";
    title.style.fontWeight = "950";
    title.style.color = "#ffffff";
    title.style.textShadow = "0 0 34px rgba(56,189,248,0.35), 0 12px 38px rgba(2,8,23,0.55)";
  }
  if (lead) {
    lead.style.maxWidth = "850px";
    lead.style.marginTop = "clamp(1.5rem, 4vw, 2.2rem)";
    lead.style.fontSize = "clamp(1.25rem, 4vw, 2.1rem)";
    lead.style.lineHeight = "1.34";
  }
}

function applyHeroCopy(config?: RuntimeConfig) {
  const hero = document.querySelector<HTMLElement>(".hero"); if (!hero) return;
  const eyebrow = hero.querySelector<HTMLElement>(".eyebrow"); const title = hero.querySelector<HTMLElement>("h1"); const lead = hero.querySelector<HTMLElement>(".lead");
  if (eyebrow) eyebrow.textContent = config?.hero_eyebrow || HERO_COPY.eyebrow;
  ensurePoweredByLine(hero, eyebrow, config?.hero_powered_by || HERO_COPY.poweredBy);
  if (title) title.textContent = safeHeroHeadline(config);
  if (lead) lead.textContent = config?.hero_lead || HERO_COPY.lead;
  styleHero(hero, eyebrow, title, lead);
  const actions = [config?.primary_cta || HERO_COPY.actions[0], config?.secondary_cta || HERO_COPY.actions[1], HERO_COPY.actions[2], HERO_COPY.actions[3]];
  hero.querySelectorAll<HTMLAnchorElement>(".hero-actions a").forEach((anchor, index) => { if (actions[index]) anchor.textContent = actions[index]; });
}

function valueToDisplay(value: unknown) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function trendRows(projectTrends?: Record<string, unknown>) {
  const trend = projectTrends || {status: "unavailable", note: "Trend data loads after project run history is available."};
  const rows = [
    ["Status", valueToDisplay(trend.status)],
    ["Baseline", valueToDisplay(trend.baseline || trend.current_score || trend.score || "Unavailable")],
    ["Trend", valueToDisplay(trend.trend || trend.direction || "Unavailable")],
    ["Note", valueToDisplay(trend.note || "Run and persist project assessments to build trend history.")],
  ];
  return rows.map(([key, value]) => `<div class="trend-row"><span class="trend-key">${escapeHtml(key)}</span><span class="trend-value">${escapeHtml(value)}</span></div>`).join("");
}

function ensureCommercialOpsPanel(config?: RuntimeConfig, diagnostics?: Record<string, unknown>, projectTrends?: Record<string, unknown>) {
  ensureRuntimeOpsStyles();
  const target = document.querySelector<HTMLElement>(".status-panel") || document.querySelector<HTMLElement>(".section.panel"); if (!target?.parentElement) return;
  const flags = config?.feature_flags || {}; const banner = config?.maintenance_banner ? `<p class="warning-box">${escapeHtml(config.maintenance_banner)}</p>` : "";
  let panel = document.getElementById("runtime-commercial-ops") as HTMLElement | null;
  if (!panel) { panel = document.createElement("section"); panel.id = "runtime-commercial-ops"; panel.className = "section panel"; target.insertAdjacentElement("afterend", panel); }
  panel.innerHTML = `
    <div class="section-head"><div><p class="eyebrow">Commercial Ops</p><h2>Runtime config, project history, and diagnostics</h2></div><span class="status blue">${escapeHtml(config?.source || "fallback")}</span></div>
    ${banner}
    <div class="grid three inset-grid"><article><b>Runtime config</b><span>Source: ${escapeHtml(config?.source || "fallback")} · Version: ${escapeHtml(config?.version || "default")}</span></article><article><b>Default repository</b><span>${escapeHtml(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE)}</span></article><article><b>Admin writes</b><span>Read-only unless server admin token is configured</span></article></div>
    <div class="two-col inset-grid"><div class="mini-panel"><p class="eyebrow">Feature visibility</p><ul class="tight-list">${Object.entries(flags).slice(0, 8).map(([key, value]) => `<li>${escapeHtml(key)}: ${value ? "on" : "off"}</li>`).join("") || "<li>Default feature set active</li>"}</ul></div><div class="mini-panel"><p class="eyebrow">Project trend baseline</p><div class="trend-card">${trendRows(projectTrends)}</div></div></div>
    <details class="help-details"><summary>Safe diagnostics</summary><div class="help-body"><pre class="json-block">${escapeHtml(JSON.stringify(diagnostics || {status:"unavailable"}, null, 2))}</pre></div></details>
    <details class="help-details"><summary>Admin Config / Runtime Settings</summary><div class="help-body"><p>Runtime config can update harmless public copy without redeploy. Write actions are read-only unless backend admin authentication is configured. Backend enforcement still controls authorization and approval gates.</p></div></details>`;
}

async function fetchJson(path: string) { if (!API_URL) return null; const response = await fetch(`${API_URL}${path}`, {cache: "no-store"}); if (!response.ok) return null; return response.json(); }

export default function GenericRepositoryExample() {
  useEffect(() => {
    let cancelled = false; let attempts = 0;
    const applyHostedUiPolish = (config?: RuntimeConfig, diagnostics?: Record<string, unknown>, trends?: Record<string, unknown>) => { attempts += 1; applyGenericRepositoryExample(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE); applyHeroCopy(config); ensureCommercialOpsPanel(config, diagnostics, trends); if (attempts >= 20) window.clearInterval(timer); };
    const timer = window.setInterval(() => applyHostedUiPolish(), 250); applyHostedUiPolish();
    Promise.all([fetchJson("/config/runtime"), fetchJson("/diagnostics"), fetchJson("/projects/default_project/trends")]).then(([configPayload, diagnosticsPayload, trendsPayload]) => { if (cancelled) return; const config = (configPayload?.config || {}) as RuntimeConfig; applyHostedUiPolish(config, diagnosticsPayload || undefined, trendsPayload || undefined); }).catch(() => applyHostedUiPolish());
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
  return null;
}
