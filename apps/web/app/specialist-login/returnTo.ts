const PROTECTED_ROOTS = [
  "/assessment", "/es/assessment", "/operations", "/es/operations",
  "/operator", "/final-review", "/coverage-targets", "/setup-readiness", "/setup-actions",
];

/** Accept only unambiguous local specialist pages, never arbitrary redirect URLs. */
export function specialistReturnTo(search: string, locale: "en" | "es" = "en"): string {
  const fallback = `${locale === "es" ? "/es" : ""}/assessment?tier=comprehensive#assessment`;
  const values = new URLSearchParams(search).getAll("returnTo");
  if (values.length !== 1) return fallback;
  const value = values[0];
  if (!value || value.length > 8192 || !value.startsWith("/") || value.startsWith("//")) return fallback;
  if (Array.from(value).some(character => character === "\\" || character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127)) return fallback;
  try {
    // Decode only for validation. Return the original bytes so query identity is preserved.
    if (Array.from(decodeURIComponent(value)).some(character => character === "\\" || character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return fallback;
    const pathname = value.split(/[?#]/, 1)[0];
    if (pathname.includes("%") || pathname.includes("//")) return fallback;
    const parsed = new URL(value, "https://nico.invalid");
    if (parsed.origin !== "https://nico.invalid" || parsed.pathname !== pathname) return fallback;
    if (!PROTECTED_ROOTS.some(root => pathname === root || pathname.startsWith(`${root}/`))) return fallback;
    return value;
  } catch {
    return fallback;
  }
}
