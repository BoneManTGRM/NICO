"use client";

import {useEffect} from "react";

/**
 * Legacy entry point retained only so old bookmarks cannot enter the retired Express
 * final-review workflow. NICO has one client assessment product: Comprehensive. Preserve
 * the caller's exact run/language query string and move immediately to the canonical
 * protected review workspace.
 */
export default function FinalReviewLegacyRedirect() {
  useEffect(() => {
    const query = window.location.search || "";
    window.location.replace(`/operations/final-review${query}`);
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Comprehensive</p>
        <h1>Opening the current internal final review…</h1>
        <p className="lead">The legacy review page has been retired. Your exact run context is being preserved.</p>
      </section>
    </main>
  );
}
