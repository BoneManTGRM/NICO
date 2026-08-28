import type {CanonicalLocale, Locale, ReportLocale} from "./assessmentTypes";

export const UI_LOCALE_STORAGE_KEY = "nico.ui-locale.v1";
export const REPORT_LOCALE_STORAGE_KEY = "nico.report-locale.v1";
export const UI_LOCALE_CHANGE_EVENT = "nico:ui-locale-change";
export const REPORT_LOCALE_CHANGE_EVENT = "nico:report-locale-change";

export function normalizeCanonicalLocale(value: unknown): CanonicalLocale {
  const token = String(value || "").trim().toLowerCase();
  return token === "es" || token === "es-mx" || token.startsWith("es-")
    ? "es-MX"
    : "en-US";
}

export function canonicalLocale(value: Locale | string | null | undefined): CanonicalLocale {
  return normalizeCanonicalLocale(value);
}

export function routeLocale(pathname: string): CanonicalLocale | null {
  const normalized = String(pathname || "").trim();
  if (
    normalized === "/es"
    || normalized.startsWith("/es/")
    || normalized === "/es-mx"
    || normalized.startsWith("/es-mx/")
  ) return "es-MX";
  if (normalized === "/assessment" || normalized.startsWith("/assessment/")) return "en-US";
  return null;
}

function safeLocalStorageGet(key: string): string {
  if (typeof window === "undefined") return "";
  try {
    return String(window.localStorage.getItem(key) || "").trim();
  } catch {
    return "";
  }
}

function safeLocalStorageSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // URL state remains authoritative when browser storage is unavailable.
  }
}

export function preferredUiLocale(
  pathname: string,
  browserLocale = "",
): CanonicalLocale {
  const explicit = safeLocalStorageGet(UI_LOCALE_STORAGE_KEY);
  if (explicit) return normalizeCanonicalLocale(explicit);
  return routeLocale(pathname) || normalizeCanonicalLocale(browserLocale || "en-US");
}

export function persistUiLocale(locale: CanonicalLocale): void {
  safeLocalStorageSet(UI_LOCALE_STORAGE_KEY, locale);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(UI_LOCALE_CHANGE_EVENT, {detail: {locale}}));
  }
}

export function reportLocaleForRequest(uiLocale: Locale): ReportLocale {
  if (typeof window !== "undefined") {
    const explicitUrl = new URL(window.location.href).searchParams.get("report_locale");
    if (explicitUrl) return normalizeCanonicalLocale(explicitUrl);
    const explicitStored = safeLocalStorageGet(REPORT_LOCALE_STORAGE_KEY);
    if (explicitStored) return normalizeCanonicalLocale(explicitStored);
  }
  return normalizeCanonicalLocale(uiLocale);
}

export function reportLanguageForRequest(uiLocale: Locale): "en" | "es-MX" {
  return reportLocaleForRequest(uiLocale) === "es-MX" ? "es-MX" : "en";
}

export function persistReportLocale(locale: ReportLocale): void {
  safeLocalStorageSet(REPORT_LOCALE_STORAGE_KEY, locale);
  if (typeof window !== "undefined") {
    const url = new URL(window.location.href);
    url.searchParams.set("report_locale", locale);
    window.history.replaceState(
      window.history.state,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    );
    window.dispatchEvent(new CustomEvent(REPORT_LOCALE_CHANGE_EVENT, {detail: {locale}}));
  }
}

export function localePreservingHref(
  pathname: string,
  search: string,
  hash: string,
  targetLocale: CanonicalLocale,
): string {
  const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const spanish = targetLocale === "es-MX";
  const assessmentRoute = pathname === "/assessment"
    || pathname.startsWith("/assessment/")
    || pathname === "/es/assessment"
    || pathname.startsWith("/es/assessment/")
    || pathname === "/es-mx"
    || pathname.startsWith("/es-mx/");

  let targetPath = pathname;
  if (assessmentRoute) {
    const sourcePrefix = pathname.startsWith("/es/assessment")
      ? "/es/assessment"
      : pathname.startsWith("/es-mx")
        ? "/es-mx"
        : "/assessment";
    const suffix = pathname.slice(sourcePrefix.length);
    targetPath = `${spanish ? "/es/assessment" : "/assessment"}${suffix}`;
    params.set("tier", "comprehensive");
    params.delete("lang");
  } else if (spanish) {
    params.set("lang", "es-MX");
  } else {
    params.delete("lang");
  }

  const query = params.toString();
  const normalizedHash = String(hash || "").trim();
  return `${targetPath}${query ? `?${query}` : ""}${normalizedHash}`;
}
