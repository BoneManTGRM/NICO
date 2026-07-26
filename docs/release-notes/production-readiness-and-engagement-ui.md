# Production readiness and engagement UI

## Root causes addressed

The public assessment attempted a persistence preflight before creating a Comprehensive run. When the backend reported `comprehensive_sqlite_persistent_volume_required`, the frontend converted the blocked preflight into a generic failed-run state, rendered the raw storage diagnostic near the action, and rendered a second generic backend-unreachable error in the status panel. No intake request was sent and no run ID existed.

The production acceptance workflow then reported only that the browser did not expose a run ID. It did not fail early with the persistence-readiness reason, which made repeated releases look like unstable two-service browser failures instead of one persistent deployment blocker.

## Application changes

- Added explicit readiness phases separate from failed runs.
- Preserved structured API status, code, retryability, and request IDs.
- Normalized client-safe service-unavailable and configuration-blocked states.
- Rendered one authoritative alert.
- Added exact-run recovery so retry resumes an accepted run instead of starting a duplicate.
- Replaced count-based workspace identity with semantic engagement attributes.
- Repositioned public copy around expert-led technical advisory work.
- Collapsed and simplified optional human-evidence intake.
- Added compact mobile behavior and production typography.

## Acceptance changes

- Bound live proof to semantic workspace and action selectors.
- Kept the existing branch-protection status context for compatibility.
- Added a readiness gate before installing browser dependencies or attempting a live run.
- Added regression contracts for blocked preflight, exact-run retry, one-alert presentation, mobile evidence intake, and external deployment requirements.

## External production action still required

The repository cannot provision the production database or persistent volume. Production acceptance will remain blocked until the backend receives either a valid Postgres connection or a verified mounted SQLite volume. Follow `docs/production-assessment-readiness.md` before rerunning the live release gate.
