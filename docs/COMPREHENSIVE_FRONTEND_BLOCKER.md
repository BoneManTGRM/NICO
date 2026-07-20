# Comprehensive frontend and locale blocker

Status: release-blocking for issue #672 and PR #673.

## Reproduced production defect

A customer selecting the visible `Comprehensive` service can receive a real Mid assessment:

- the browser run identity starts with `midrun_`;
- the live stage UI says `Mid Assessment` and `Mid instructions`;
- the downloaded artifact is named `nico-mid-assessment-*`;
- the PDF title is `NICO MID TECHNICAL DILIGENCE ASSESSMENT`;
- the PDF uses the Mid 35-50 page contract rather than the Comprehensive orchestration contract.

The Spanish workspace also continues to expose `Express`, `Intermedia`, and `Completa`, while the English workspace appears to expose only `Express` and `Comprehensive`.

## Confirmed root cause

1. `apps/web/app/assessment/page.tsx` is still the legacy three-tier React state machine (`express | mid | full`).
2. `apps/web/app/TwoServiceAssessmentGuard.tsx` does not replace that state machine. It mutates rendered button text, hides extra buttons, and normalizes the URL after mount. The visible `Comprehensive` button can therefore retain the original `mid` click handler and start `/assessment/mid-run`.
3. `apps/web/app/es/assessment/SpanishAssessmentLocalization.tsx` is a second DOM-mutation layer over the English page. It explicitly translates `Mid` to `Intermedia` and `Full` to `Completa`, and its whole-page mutation observers do not share one canonical two-service locale model.
4. `apps/web/app/api/nico/[...path]/route.ts` does not allow the native `/assessment/comprehensive-run` routes through the frontend proxy.
5. The native Comprehensive runtime exists, but production capability providers and a customer intake/bootstrap that resolves the immutable commit identity remain part of WP-4. The UI must not silently fall back to Mid while those providers are incomplete.

## Required repair

- replace the public three-tier state type with a native `express | comprehensive` component;
- remove the two-service DOM rewrite from the production layout;
- replace Spanish DOM mutation with shared static locale dictionaries passed into the same component;
- add the native Comprehensive start/status/continue routes to the bounded frontend proxy;
- add a fail-closed Comprehensive intake/bootstrap that binds repository, immutable commit SHA, run ID, evidence ledger, customer, and project before execution;
- bind all required production capability providers or return a truthful blocked state;
- render one Comprehensive report package with Comprehensive branding and all required deeper modules;
- add English/Spanish parity, mobile, exact-route, run-identity, report-title, page-content, and cross-format regression tests;
- require a fresh deployed Express run and Comprehensive run before release acceptance.

No merge or client-ready claim is allowed while a visible Comprehensive selection can create a Mid run or while the Spanish and English service models diverge.
