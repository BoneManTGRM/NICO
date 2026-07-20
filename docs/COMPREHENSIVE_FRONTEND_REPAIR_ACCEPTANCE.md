# Comprehensive frontend repair acceptance

This checklist is release-blocking for issue #672 and PR #673.

## Public service model

- The canonical React assessment component exposes exactly `Express` and `Comprehensive`.
- Legacy `mid`, `full`, and `deep` query values are accepted only as compatibility aliases and normalize before rendering.
- No DOM mutation layer renames or hides assessment tiers after render.
- Selecting Comprehensive can never invoke a Mid or Full public endpoint.

## Native Comprehensive lifecycle

- Frontend start uses the native Comprehensive intake.
- Intake binds repository, immutable commit SHA, run ID, evidence-ledger ID, customer, project, and explicit authorization.
- Status and continuation use the exact same Comprehensive run identity.
- Missing durable storage, identity resolution, or required providers fails closed with a customer-visible blocked state.
- No fallback starts a Mid or Full run.

## Report package

- Service ID and customer-facing title are Comprehensive in JSON, Markdown, HTML, PDF, filenames, run UI, and review records.
- The report contains every Comprehensive-only module required by the orchestration contract.
- Page count is an output of substantive content, not padding; a Mid 35-50 page artifact cannot satisfy Comprehensive acceptance by relabeling.
- Human review remains required and client delivery remains disabled.

## English and Spanish parity

- English and Spanish render the same component tree, service count, controls, states, routes, and disabled/enabled behavior.
- Copy is selected from static locale dictionaries, not MutationObserver translation.
- The Spanish route exposes only `Express` and `Integral`/`Comprehensive` according to the approved product translation; it never exposes legacy `Intermedia` and `Completa` as separate services.
- Dynamic stage, error, report, review, and evidence labels are localized from the same state model.

## Verification

- Unit tests prove two native services and no public Mid/Full routes.
- Frontend build and typecheck pass.
- English and Spanish mobile screenshots show the same structure.
- One deployed Comprehensive run returns a `comprehensive` service ID and non-Mid run identity.
- The downloaded report title and filename are Comprehensive.
- Two consecutive deployed runs pass exact-SHA identity, persistence, restart, cross-format, and review-gate checks.
