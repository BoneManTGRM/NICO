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
  lead: "Inteligencia de reparación para sistemas autorizados. Evaluaciones vinculadas a evidencia, flujos de análisis, informes preparados para el cliente y planificación de reparaciones sujeta a aprobación humana.",
  actions: ["Ejecutar evaluación", "Ejecutar analizadores", "Inteligencia de reparación", "Cómo utilizar NICO"],
};

const SPANISH_VALUE_MAP = new Map<string, string>([
  ["unavailable", "No disponible"],
  ["available", "Disponible"],
  ["fallback", "Alternativa"],
  ["default", "Predeterminado"],
  ["none", "Ninguno"],
  ["unknown", "Desconocido"],
  ["pending", "Pendiente"],
  ["running", "En ejecución"],
  ["complete", "Completo"],
  ["completed", "Completado"],
  ["failed", "Fallido"],
  ["blocked", "Bloqueado"],
  ["read-only", "Solo lectura"],
  ["trend data loads after project run history is available.", "Los datos de tendencias se cargarán cuando exista historial de ejecuciones del proyecto."],
  ["run and persist project assessments to build trend history.", "Ejecuta y conserva evaluaciones del proyecto para construir su historial de tendencias."],
  ["next_public_nico_api_url is not configured in vercel.", "NEXT_PUBLIC_NICO_API_URL no está configurada en Vercel."],
  ["backend /diagnostics returned a non-ok response.", "El endpoint /diagnostics del backend devolvió una respuesta no válida."],
  ["backend /diagnostics returned an empty response.", "El endpoint /diagnostics del backend devolvió una respuesta vacía."],
  ["backend /diagnostics request failed.", "Falló la solicitud al endpoint /diagnostics del backend."],
]);

const SPANISH_DIAGNOSTIC_KEYS = new Map<string, string>([
  ["status", "estado"],
  ["reason", "motivo"],
  ["response", "respuesta"],
  ["backend_url_configured", "url_del_backend_configurada"],
  ["backend_url", "url_del_backend"],
  ["http_status", "estado_http"],
  ["database", "base_de_datos"],
  ["storage", "almacenamiento"],
  ["adapter", "adaptador"],
  ["durable", "durable"],
  ["recorded", "registrado"],
  ["version", "versión"],
  ["source", "fuente"],
  ["features", "funciones"],
  ["feature_flags", "indicadores_de_funciones"],
  ["project", "proyecto"],
  ["history", "historial"],
  ["trend", "tendencia"],
  ["baseline", "línea_base"],
  ["note", "nota"],
]);

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

function isSpanishRoute() {
  if (typeof window === "undefined") return false;
  const pathname = window.location.pathname.toLowerCase();
  const language = new URLSearchParams(window.location.search).get("lang")?.toLowerCase();
  return pathname === "/es" || pathname.startsWith("/es/") || pathname.startsWith("/es-mx") || language === "es-mx" || language === "es";
}
function routeCopy(spanish: boolean) { return spanish ? HERO_COPY_ES_MX : HERO_COPY_EN; }
function escapeHtml(value: unknown) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char] || char)); }
function setNativeInputValue(input: HTMLInputElement, value: string) { const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set; setter?.call(input, value); input.dispatchEvent(new Event("input", {bubbles: true})); input.dispatchEvent(new Event("change", {bubbles: true})); }
function applyGenericRepositoryExample(example = GENERIC_REPOSITORY_EXAMPLE) { document.querySelectorAll<HTMLInputElement>("input").forEach((input) => { const value = input.value.trim(); if (PRIVATE_DEFAULTS.has(value)) setNativeInputValue(input, example); if (input.placeholder === "owner/repo" || input.placeholder === GENERIC_REPOSITORY_EXAMPLE) input.placeholder = example; }); }

function applyGlobalLanguageNav(spanish: boolean) {
  const labels = spanish
    ? new Map([["/easy", "Modo fácil"], ["/start-job", "Iniciar trabajo"], ["/scanner-workflow", "Analizadores a Express"], ["/guided-workflow", "Guía"], ["/", "Centro de mando"]])
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
  toggle.href = spanish ? "/assessment?tier=express#assessment" : "/es/assessment?tier=express#assessment";
  toggle.textContent = spanish ? "English" : "Español";
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

function safeHeroHeadline(config: RuntimeConfig | undefined, spanish: boolean) {
  const copy = routeCopy(spanish);
  const configured = (config?.hero_headline || "").trim();
  if (!configured || spanish) return copy.title;
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
  const spanish = isSpanishRoute();
  const copy = routeCopy(spanish);
  const hero = document.querySelector<HTMLElement>(".hero"); if (!hero) return;
  const eyebrow = hero.querySelector<HTMLElement>(".eyebrow"); const title = hero.querySelector<HTMLElement>("h1"); const lead = hero.querySelector<HTMLElement>(".lead");
  if (eyebrow) eyebrow.textContent = spanish ? copy.eyebrow : config?.hero_eyebrow || copy.eyebrow;
  ensurePoweredByLine(hero, eyebrow, spanish ? copy.poweredBy : config?.hero_powered_by || copy.poweredBy);
  if (title) title.textContent = safeHeroHeadline(config, spanish);
  if (lead) lead.textContent = spanish ? copy.lead : config?.hero_lead || copy.lead;
  styleHero(hero, eyebrow, title, lead);
  const actions = spanish ? copy.actions : [config?.primary_cta || copy.actions[0], config?.secondary_cta || copy.actions[1], copy.actions[2], copy.actions[3]];
  hero.querySelectorAll<HTMLAnchorElement>(".hero-actions a").forEach((anchor, index) => { if (actions[index]) anchor.textContent = actions[index]; });
}

function localizeSpanishText(value: string): string {
  const direct = SPANISH_VALUE_MAP.get(value.trim().toLowerCase());
  if (direct) return direct;
  return value
    .replace(/Trend data loads after project run history is available\.?/gi, "Los datos de tendencias se cargarán cuando exista historial de ejecuciones del proyecto.")
    .replace(/Run and persist project assessments to build trend history\.?/gi, "Ejecuta y conserva evaluaciones del proyecto para construir su historial de tendencias.")
    .replace(/Diagnostics request did not return data\.?/gi, "La solicitud de diagnósticos no devolvió datos.")
    .replace(/Backend \/diagnostics returned a non-OK response\.?/gi, "El endpoint /diagnostics del backend devolvió una respuesta no válida.")
    .replace(/Backend \/diagnostics returned an empty response\.?/gi, "El endpoint /diagnostics del backend devolvió una respuesta vacía.")
    .replace(/Backend \/diagnostics request failed\.?/gi, "Falló la solicitud al endpoint /diagnostics del backend.");
}

function valueToDisplay(value: unknown, spanish = false) {
  if (value === null || value === undefined || value === "") return spanish ? "No disponible" : "Unavailable";
  if (Array.isArray(value)) return value.length ? value.map((item) => spanish && typeof item === "string" ? localizeSpanishText(item) : String(item)).join(", ") : spanish ? "Ninguno" : "None";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  return spanish ? localizeSpanishText(text) : text;
}

function localizeDiagnosticValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(localizeDiagnosticValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [SPANISH_DIAGNOSTIC_KEYS.get(key) || key, localizeDiagnosticValue(item)]));
  }
  if (typeof value === "string") return localizeSpanishText(value);
  return value;
}

function trendRows(projectTrends?: Record<string, unknown>, spanish = false) {
  const trend = projectTrends || {status: "unavailable", note: spanish ? "Los datos de tendencias se cargarán cuando exista historial de ejecuciones del proyecto." : "Trend data loads after project run history is available."};
  const rows = spanish
    ? [["Estado", valueToDisplay(trend.status, true)], ["Línea base", valueToDisplay(trend.baseline || trend.current_score || trend.score || "Unavailable", true)], ["Tendencia", valueToDisplay(trend.trend || trend.direction || "Unavailable", true)], ["Nota", valueToDisplay(trend.note || "Ejecuta y conserva evaluaciones del proyecto para construir su historial de tendencias.", true)]]
    : [["Status", valueToDisplay(trend.status)], ["Baseline", valueToDisplay(trend.baseline || trend.current_score || trend.score || "Unavailable")], ["Trend", valueToDisplay(trend.trend || trend.direction || "Unavailable")], ["Note", valueToDisplay(trend.note || "Run and persist project assessments to build trend history.")]];
  return rows.map(([key, value]) => `<div class="trend-row"><span class="trend-key">${escapeHtml(key)}</span><span class="trend-value">${escapeHtml(value)}</span></div>`).join("");
}

function diagnosticsFallback(spanish: boolean) {
  return spanish ? {estado: "no disponible", motivo: "La solicitud de diagnósticos no devolvió datos."} : {status: "unavailable", reason: "Diagnostics request did not return data."};
}

function renderCommercialOpsMarkup(config?: RuntimeConfig, diagnostics?: Record<string, unknown>, projectTrends?: Record<string, unknown>) {
  const spanish = isSpanishRoute();
  const flags = config?.feature_flags || {};
  const bannerText = config?.maintenance_banner ? valueToDisplay(config.maintenance_banner, spanish) : "";
  const banner = bannerText ? `<p class="warning-box">${escapeHtml(bannerText)}</p>` : "";
  const source = valueToDisplay(config?.source || "fallback", spanish);
  const version = valueToDisplay(config?.version || "default", spanish);
  const labels = spanish ? {
    eyebrow: "Operaciones comerciales", title: "Configuración de ejecución, historial del proyecto y diagnósticos", runtime: "Configuración de ejecución", source: "Fuente", version: "Versión", defaultRepo: "Repositorio predeterminado", admin: "Escrituras administrativas", adminText: "Solo lectura, salvo que esté configurado el token administrativo del servidor", feature: "Visibilidad de funciones", defaultFeature: "Conjunto predeterminado de funciones activo", trends: "Línea base de tendencias del proyecto", diagnostics: "Diagnósticos seguros", settings: "Configuración administrativa y ajustes de ejecución", settingsText: "La configuración de ejecución puede actualizar textos públicos seguros sin volver a desplegar. Las acciones de escritura permanecen en modo de solo lectura salvo que esté configurada la autenticación administrativa del backend. El backend conserva los controles de autorización y aprobación."
  } : {
    eyebrow: "Commercial Ops", title: "Runtime config, project history, and diagnostics", runtime: "Runtime config", source: "Source", version: "Version", defaultRepo: "Default repository", admin: "Admin writes", adminText: "Read-only unless server admin token is configured", feature: "Feature visibility", defaultFeature: "Default feature set active", trends: "Project trend baseline", diagnostics: "Safe diagnostics", settings: "Admin Config / Runtime Settings", settingsText: "Runtime config can update harmless public copy without redeploy. Write actions are read-only unless backend admin authentication is configured. Backend enforcement still controls authorization and approval gates."
  };
  const diagnosticDisplay = spanish ? localizeDiagnosticValue(diagnostics || diagnosticsFallback(true)) : diagnostics || diagnosticsFallback(false);
  return `
    <div class="section-head"><div><p class="eyebrow">${labels.eyebrow}</p><h2>${labels.title}</h2></div><span class="status blue">${escapeHtml(source)}</span></div>
    ${banner}
    <div class="grid three inset-grid"><article><b>${labels.runtime}</b><span>${labels.source}: ${escapeHtml(source)} · ${labels.version}: ${escapeHtml(version)}</span></article><article><b>${labels.defaultRepo}</b><span>${escapeHtml(config?.default_repository_example || GENERIC_REPOSITORY_EXAMPLE)}</span></article><article><b>${labels.admin}</b><span>${labels.adminText}</span></article></div>
    <div class="two-col inset-grid"><div class="mini-panel"><p class="eyebrow">${labels.feature}</p><ul class="tight-list">${Object.entries(flags).slice(0, 8).map(([key, value]) => `<li>${escapeHtml(key)}: ${value ? (spanish ? "activo" : "on") : (spanish ? "inactivo" : "off")}</li>`).join("") || `<li>${labels.defaultFeature}</li>`}</ul></div><div class="mini-panel"><p class="eyebrow">${labels.trends}</p><div class="trend-card">${trendRows(projectTrends, spanish)}</div></div></div>
    <details class="help-details"><summary>${labels.diagnostics}</summary><div class="help-body"><pre class="json-block">${escapeHtml(JSON.stringify(diagnosticDisplay, null, 2))}</pre></div></details>
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
      const spanish = isSpanishRoute();
      applyGlobalLanguageNav(spanish);
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
