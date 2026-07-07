"use client";

import {useEffect} from "react";

const API_URL = (process.env.NEXT_PUBLIC_NICO_API_URL || "").replace(/\/$/, "");
const PRIVATE_DEFAULTS = new Set(["BoneManTGRM/NICO", "bonemantgrm/nico"]);
const GENERIC_REPOSITORY_EXAMPLE = "your-org/your-repo";
const HERO_COPY_EN = {
  eyebrow: "NICO Platform",
  poweredBy: "Powered by Reparodynamics",
  title: "NICO",
  lead: "Repair intelligence for authorized systems. Evidence-bound assessments, scanner workflows, client-ready reports, and approval-gated repair planning.",
  actions: ["Run Assessment", "Scanner Worker", "Repair Intelligence", "How to Use"],
};
const HERO_COPY_ES_MX = {
  eyebrow: "Plataforma NICO",
  poweredBy: "Impulsado por Reparodynamics",
  title: "NICO",
  lead: "Inteligencia de reparación para sistemas autorizados. Evaluaciones basadas en evidencia, workflows de scanner, reportes listos para cliente y planeación de reparación con aprobación humana.",
  actions: ["Correr evaluación", "Scanner worker", "Inteligencia de reparación", "Cómo usar"],
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

function isEsMxRoute() { return typeof window !== "undefined" && window.location.pathname.startsWith("/es-mx"); }
function routeCopy(isEsMx: boolean) { return isEsMx ? HERO_COPY_ES_MX : HERO_COPY_EN; }
function escapeHtml(value: unknown) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char] || char)); }
function setNativeInputValue(input: HTMLInputElement, value: string) { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set; setter?.call(input, value); input.dispatchEvent(new Event("input", {bubbles: true})); input.dispatchEvent(new Event("change", {bubbles: true})); }
function applyGenericRepositoryExample(example = GENERIC_REPOSITORY_EXAMPLE) { document.querySelectorAll<HTMLInputElement>("input").forEach((input) => { const value = input.value.trim(); if (PRIVATE_DEFAULTS.has(value)) setNativeInputValue(input, example); if (input.placeholder === "owner/repo" || input.placeholder === GENERIC_REPOSITORY_EXAMPLE) input.placeholder = example; }); }

function applyGlobalLanguageNav(isEsMx: boolean) {
  const labels = isEsMx
    ? new Map([["/easy", "Modo fácil"], ["/start-job", "Iniciar trabajo"], ["/scanner-workflow", "Scanner a Express"], ["/guided-workflow", "Guía"], ["/", "Centro de mando"]])
    : new Map([["/easy", "Easy Mode"], ["/start-job", "Start Job"], ["/scanner-workflow", "Scanner to Express"], ["/guided-workflow", "Guide"], ["/", "Command Center"]]);
  document.querySelectorAll<HTMLAnchorElement>(".global-links a").forEach((anchor) => {
    const path = new URL(anchor.href, window.location.origin).pathname;
    const label = labels.get(path);
    if (label) anchor.textContent = label;
  });
  const links = document.querySelector<HTMLElement>(".global-links");
  if (!links) return;
  let toggle = links.querySelector<HTMLAnchorElement>("[data-nico-language-toggle]");
  if (!toggle) {
    toggle = document.createElement("a");
    toggle.dataset.nicoLanguageToggle = "true";
    links.appendChild(toggle);
  }
  toggle.href = isEsMx ? "/" : "/es-mx";
  toggle.textContent = isEsMx ? "English" : "Español";
}

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

function safeHeroHeadline(config: RuntimeConfig | undefined, isEsMx: boolean) {
  const copy = routeCopy(isEsMx);
  const configured = (config?.hero_headline || "").trim();
  if (!configured || isEsMx) return copy.title;
  const lowered = configured.toLowerCase();
  if (lowered.includes("repair intelligence") || lowered.includes("authorized systems")) return copy.title;
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
  if (eyebrow) { eyebrow.style.margin = "0"; eyebrow.style.fontSize = "clamp(0.9rem, 2.9vw, 1.2rem)"; eyebrow.style.lineHeight = "1.1"; eyebrow.style.letterSpacing = "0.22em"; eyebrow.style.fontWeight = "900"; eyebrow.style.color = "#38bdf8"; }
  if (title) { title.style.margin = "0.85rem 0 0"; title.style.fontSize = "clamp(5.4rem, 26vw, 12rem)"; title.style.lineHeight = "0.82"; title.style.letterSpacing = "0.08em"; title.style.fontWeight = "950"; title.style.color = "#ffffff"; title.style.textShadow = "0 0 34px rgba(56,189,248,0.35), 0 12px 38px rgba(2,8,23,0.55)"; }
  if (lead) { lead.style.maxWidth = "850px"; lead.style.marginTop = "clamp(1.5rem, 4vw, 2.2rem)"; lead.style.fontSize = "clamp(1.25rem, 4vw, 2.1rem)"; lead.style.lineHeight = "1.34"; }
}

function applyHeroCopy(config?: RuntimeConfig) {
  const isEsMx = isEsMxRoute();
  const copy = routeCopy(isEsMx);
  const hero = document.querySelector<HTMLElement>(".hero"); if (!hero) return;
  const eyebrow = hero.querySelector<HTMLElement>(".eyebrow"); const title = hero.querySelector<HTMLElement>("h1"); const lead = hero.querySelector<HTMLElement>(".lead");
  if (eyebrow) eyebrow.textContent = isEsMx ? copy.eyebrow : config?.hero_eyebrow || copy.eyebrow;
  ensurePoweredByLine(hero, eyebrow, isEsMx ? copy.poweredBy : config?.hero_powered_by || copy.poweredBy);
  if (title) title.textContent = safeHeroHeadline(config, isEsMx);
  if (lead) lead.textContent = isEsMx ? copy.lead : config?.hero_lead || copy.lead;
  styleHero(hero, eyebrow, title, lead);
  const actions = isEsMx ? copy.actions : [config?.primary_cta || copy.actions[0], config?.secondary_cta || copy.actions[1], copy.actions[2], copy.actions[3]];
  hero.querySelectorAll<HTMLAnchorElement>(".hero-actions a").forEach((anchor, index) => { if (actions[index]) anchor.textContent = actions[index]; });
}

function valueToDisplay(value: unknown, isEsMx = false) {
  if (value === null || value === undefined || value === "") return isEsMx ? "No disponible" : "Unavailable";
  if (Array.isArray(value)) return value.length ? value.join(", ") : isEsMx ? "Ninguno" : "None";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  if (!isEsMx) return text;
  if (text.toLowerCase() === "unavailable") return "No disponible";
  if (text.toLowerCase() === "available") return "Disponible";
  return text;
}

function trendRows(projectTrends?: Record<string, unknown>, isEsMx = false) {
  const trend = projectTrends || {status: "unavailable", note: isEsMx ? "Los datos de tendencia cargan después de que exista historial de runs del proyecto." : "Trend data loads after project run history is available."};
  const rows = isEsMx
    ? [["Estado", valueToDisplay(trend.status, true)], ["Línea base", valueToDisplay(trend.baseline || trend.current_score || trend.score || "Unavailable", true)], ["Tendencia", valueToDisplay(trend.trend || trend.direction || "Unavailable", true)], ["Nota", valueToDisplay(trend.note || "Corre y guarda evaluaciones del proyecto para construir historial de tendencia.", true)]]
    : [["Status", valueToDisplay(trend.status)], ["Baseline", valueToDisplay(trend.baseline || trend.current_score || trend.score || "Unavailable")], ["Trend", valueToDisplay(trend.trend || trend.direction || "Unavailable")], ["Note", valueToDisplay(trend.note || "Run and persist project assessments to build trend history.")]];
  return rows.map(([key, value]) => `<div class="trend-row"><span class="trend-key">${escapeHtml(key)}</span><span class="trend-value">${escapeHtml(value)}</span></div>`).join("");
}

function renderCommercialOpsMarkup(config?: RuntimeConfig, diagnostics?: Record<string, unknown>, projectTrends?: Record<string, unknown>) {
  const isEsMx = isEsMxRoute();
  const flags = config?.feature_flags || {};
  const banner = config?.maintenance_banner ? `<p class="warning-box">${escapeHtml(config.maintenance_banner)}</p>` : "";
  const labels = isEsMx ? {
    eyebrow: "Operaciones comerciales", title: "Config runtime, historial del proyecto y diagnósticos", runtime: "Config runtime", source: "Fuente", version: "Versión", defaultRepo: "Repositorio default", admin: "Admin writes", adminText: "Solo lectura salvo que el token admin del backend esté configurado", feature: "Visibilidad de funciones", defaultFeature: "Set default de funciones activo", trends: "Línea base de tendencia del proyecto", diagnostics: "Diagnósticos seguros", settings: "Admin Config / Ajustes runtime", settingsText: "La config runtime puede actualizar copy público seguro sin redeploy. Las escrituras siguen en solo lectura salvo que la autenticación admin del backend esté configurada. El backend conserva los controles de autorización y aprobación."
  } : {
    eyebrow: "Commercial Ops", title: "Runtime config, project history, and diagnostics", runtime: "Runtime config", source: "Source", version: "Version", defaultRepo: "Default repository", admin: "Admin writes", adminText: "Read-only unless server admin token is configured", feature: "Feature visibility", defaultFeature: "Default feature set active", trends: "Project trend baseline", diagnostics: "Safe diagnostics", settings: "Admin Config / Runtime Settings", settingsText: "Runtime config can update harmless public copy without redeploy. Write actions are read-only unless backend admin authentication is configured. Backend enforcement still controls authorization and approval gates."
  };
  return `
    <div class="section-head"><div><p class="eyebrow">${labels.eyebrow}</p><h2>${labels.title}</h2></div><span class="status blue">${escapeHtml(config?.source || "fallback")}</span></div>
    ${banner}
    <div class="grid three inset-grid"><article><b>${labels.runtime}</b><span>${labels.source}: ${escapeHtml(config?.source || "fallback")} · ${labels.version}: ${escapeHtml(config?.version || "default")}</span></article><article><b>${labels.defaultRepo}</b><span>${escapeHtml(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE)}</span></article><article><b>${labels.admin}</b><span>${labels.adminText}</span></article></div>
    <div class="two-col inset-grid"><div class="mini-panel"><p class="eyebrow">${labels.feature}</p><ul class="tight-list">${Object.entries(flags).slice(0, 8).map(([key, value]) => `<li>${escapeHtml(key)}: ${value ? "on" : "off"}</li>`).join("") || `<li>${labels.defaultFeature}</li>`}</ul></div><div class="mini-panel"><p class="eyebrow">${labels.trends}</p><div class="trend-card">${trendRows(projectTrends, isEsMx)}</div></div></div>
    <details class="help-details"><summary>${labels.diagnostics}</summary><div class="help-body"><pre class="json-block">${escapeHtml(JSON.stringify(diagnostics || {status:"unavailable", reason:"Diagnostics request did not return data."}, null, 2))}</pre></div></details>
    <details class="help-details"><summary>${labels.settings}</summary><div class="help-body"><p>${labels.settingsText}</p></div></details>`;
}

function setTrustedEscapedMarkup(target: HTMLElement, markup: string) { target.textContent = ""; target.insertAdjacentHTML("afterbegin", markup); }
function ensureCommercialOpsPanel(config?: RuntimeConfig, diagnostics?: Record<string, unknown>, projectTrends?: Record<string, unknown>) {
  ensureRuntimeOpsStyles();
  const target = document.querySelector<HTMLElement>(".status-panel") || document.querySelector<HTMLElement>(".section.panel"); if (!target?.parentElement) return;
  let panel = document.getElementById("runtime-commercial-ops") as HTMLElement | null;
  if (!panel) { panel = document.createElement("section"); panel.id = "runtime-commercial-ops"; panel.className = "section panel"; target.insertAdjacentElement("afterend", panel); }
  setTrustedEscapedMarkup(panel, renderCommercialOpsMarkup(config, diagnostics, projectTrends));
}

async function fetchJson(path: string) { if (!API_URL) return null; try { const response = await fetch(`${API_URL}${path}`, {cache: "no-store"}); if (!response.ok) return null; return response.json(); } catch { return null; } }
async function fetchDiagnostics() {
  if (!API_URL) return {status: "unavailable", backend_url_configured: false, reason: "NEXT_PUBLIC_NICO_API_URL is not configured in Vercel."};
  try {
    const response = await fetch(`${API_URL}/diagnostics`, {cache: "no-store"});
    const data = await response.json().catch(() => null);
    if (!response.ok) return {status: "unavailable", backend_url_configured: true, backend_url: API_URL, http_status: response.status, reason: "Backend /diagnostics returned a non-OK response.", response: data};
    return data || {status: "unavailable", backend_url_configured: true, backend_url: API_URL, reason: "Backend /diagnostics returned an empty response."};
  } catch (error) {
    return {status: "unavailable", backend_url_configured: true, backend_url: API_URL, reason: error instanceof Error ? error.message : "Backend /diagnostics request failed."};
  }
}

export default function GenericRepositoryExample() {
  useEffect(() => {
    let cancelled = false; let attempts = 0;
    const applyHostedUiPolish = (config?: RuntimeConfig, diagnostics?: Record<string, unknown>, trends?: Record<string, unknown>) => {
      attempts += 1;
      const isEsMx = isEsMxRoute();
      applyGlobalLanguageNav(isEsMx);
      applyGenericRepositoryExample(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE);
      applyHeroCopy(config);
      ensureCommercialOpsPanel(config, diagnostics, trends);
      if (attempts >= 20) window.clearInterval(timer);
    };
    const timer = window.setInterval(() => applyHostedUiPolish(), 250); applyHostedUiPolish();
    Promise.all([fetchJson("/config/runtime"), fetchDiagnostics(), fetchJson("/projects/default_project/trends")]).then(([configPayload, diagnosticsPayload, trendsPayload]) => { if (cancelled) return; const config = (configPayload?.config || {}) as RuntimeConfig; applyHostedUiPolish(config, diagnosticsPayload || undefined, trendsPayload || undefined); }).catch(() => applyHostedUiPolish());
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
  return null;
}
