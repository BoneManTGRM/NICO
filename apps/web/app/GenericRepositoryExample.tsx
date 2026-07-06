"use client";

import {useEffect} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const PRIVATE_DEFAULTS = new Set(["BoneManTGRM/NICO", "bonemantgrm/nico"]);
const GENERIC_REPOSITORY_EXAMPLE = "your-org/your-repo";
const HERO_COPY = {
  eyebrow: "NICO",
  poweredBy: "Powered by Reparodynamics",
  title: "Repair intelligence for authorized systems",
  lead: "Evidence-bound technical assessments, scanner workflows, client-ready reports, and approval-gated repair planning.",
  actions: ["Run Assessment", "Scanner Worker", "Repair Intelligence", "How to Use"],
};

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

function ensurePoweredByLine(hero: HTMLElement, eyebrow: HTMLElement | null, text: string) {
  let powered = hero.querySelector<HTMLElement>(".hero-powered-by");
  if (!powered) {
    powered = document.createElement("p");
    powered.className = "hero-powered-by";
    if (eyebrow?.nextSibling) eyebrow.parentNode?.insertBefore(powered, eyebrow.nextSibling);
    else hero.insertBefore(powered, hero.querySelector("h1"));
  }
  powered.textContent = text;
  powered.style.margin = "0.35rem 0 0.85rem";
  powered.style.fontSize = "0.92rem";
  powered.style.letterSpacing = "0.16em";
  powered.style.textTransform = "uppercase";
  powered.style.fontWeight = "800";
  powered.style.color = "#7dd3fc";
}

function applyHeroCopy(config?: RuntimeConfig) {
  const hero = document.querySelector<HTMLElement>(".hero"); if (!hero) return;
  const eyebrow = hero.querySelector<HTMLElement>(".eyebrow"); const title = hero.querySelector<HTMLElement>("h1"); const lead = hero.querySelector<HTMLElement>(".lead");
  if (eyebrow) eyebrow.textContent = config?.hero_eyebrow || HERO_COPY.eyebrow;
  ensurePoweredByLine(hero, eyebrow, config?.hero_powered_by || HERO_COPY.poweredBy);
  if (title) title.textContent = config?.hero_headline || HERO_COPY.title;
  if (lead) lead.textContent = config?.hero_lead || HERO_COPY.lead;
  const actions = [config?.primary_cta || HERO_COPY.actions[0], config?.secondary_cta || HERO_COPY.actions[1], HERO_COPY.actions[2], HERO_COPY.actions[3]];
  hero.querySelectorAll<HTMLAnchorElement>(".hero-actions a").forEach((anchor, index) => { if (actions[index]) anchor.textContent = actions[index]; });
}

function ensureCommercialOpsPanel(config?: RuntimeConfig, diagnostics?: Record<string, unknown>, projectTrends?: Record<string, unknown>) {
  const target = document.querySelector<HTMLElement>(".status-panel") || document.querySelector<HTMLElement>(".section.panel"); if (!target?.parentElement) return;
  const flags = config?.feature_flags || {}; const banner = config?.maintenance_banner ? `<p class="warning-box">${escapeHtml(config.maintenance_banner)}</p>` : "";
  let panel = document.getElementById("runtime-commercial-ops") as HTMLElement | null;
  if (!panel) { panel = document.createElement("section"); panel.id = "runtime-commercial-ops"; panel.className = "section panel"; target.insertAdjacentElement("afterend", panel); }
  panel.innerHTML = `
    <div class="section-head"><div><p class="eyebrow">Commercial Ops</p><h2>Runtime config, project history, and diagnostics</h2></div><span class="status blue">${escapeHtml(config?.source || "fallback")}</span></div>
    ${banner}
    <div class="grid three inset-grid"><article><b>Runtime config</b><span>Source: ${escapeHtml(config?.source || "fallback")} · Version: ${escapeHtml(config?.version || "default")}</span></article><article><b>Default repository</b><span>${escapeHtml(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE)}</span></article><article><b>Admin writes</b><span>Read-only unless server admin token is configured</span></article></div>
    <div class="two-col inset-grid"><div class="mini-panel"><p class="eyebrow">Feature visibility</p><ul class="tight-list">${Object.entries(flags).slice(0, 8).map(([key, value]) => `<li>${escapeHtml(key)}: ${value ? "on" : "off"}</li>`).join("") || "<li>Default feature set active</li>"}</ul></div><div class="mini-panel"><p class="eyebrow">Project trend baseline</p><pre class="json-block">${escapeHtml(JSON.stringify(projectTrends || {status:"unavailable", note:"Trend data loads from /projects/default_project/trends"}, null, 2))}</pre></div></div>
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
