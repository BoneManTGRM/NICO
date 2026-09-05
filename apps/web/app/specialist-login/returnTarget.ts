const RETURN_ORIGIN = "https://nico-return.invalid";
const PROTECTED_PATHS = [
  "/assessment", "/es/assessment", "/operations", "/es/operations",
  "/operator", "/final-review", "/coverage-targets", "/setup-readiness", "/setup-actions",
];

/** Accept only an unambiguous, local protected-page destination, never an API or login URL. */
export function resolveSpecialistReturnTarget(search: string, fallback: string): string {
  const values = new URLSearchParams(search).getAll("next");
  if (values.length !== 1) return fallback;
  const value = values[0];
  if (!value.startsWith("/") || value.startsWith("//") || value.length > 8192 || /[\\\u0000-\u0020\u007f]/.test(value)) {
    return fallback;
  }
  try {
    const url = new URL(value, RETURN_ORIGIN);
    const rawPath = value.split(/[?#]/, 1)[0];
    // Reject encoded/path-normalized alternatives instead of interpreting them differently at each boundary.
    if (url.origin !== RETURN_ORIGIN || rawPath !== url.pathname || rawPath.includes("%")) return fallback;
    if (!PROTECTED_PATHS.some((root) => url.pathname === root || url.pathname.startsWith(root + "/"))) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}

/** Carry the same run through language selection; only these routes have translated counterparts. */
export function specialistLoginLanguageHref(search: string, language: "en" | "es"): string {
  const prefix = language === "es" ? "/es" : "";
  const fallback = prefix + "/assessment?tier=comprehensive#assessment";
  const target = new URL(resolveSpecialistReturnTarget(search, fallback), RETURN_ORIGIN);
  const unlocalized = target.pathname.replace(/^\/es(?=\/(?:assessment|operations)(?:\/|$))/, "");
  if (/^\/(?:assessment|operations)(?:\/|$)/.test(unlocalized)) target.pathname = prefix + unlocalized;
  return prefix + "/specialist-login?" + new URLSearchParams({next: target.pathname + target.search + target.hash});
}
