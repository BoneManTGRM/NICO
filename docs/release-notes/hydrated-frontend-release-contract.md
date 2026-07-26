# Hydrated frontend release contract

## Production evidence

After the custom-domain release-identity gate was merged, default-branch Unified Production Acceptance proved that:

- `/api/release` served the exact merge SHA;
- the deployment environment was `production`;
- the raw English and Spanish HTML contained the current copy contract;
- production persistence was ready.

The browser still observed `Run NICO Assessment` after client hydration. This isolated the remaining defect to a mixed or stale client-side frontend bundle rather than the production alias, server-rendered HTML, backend, or report generator.

## Repair

The assessment page now includes a client-only hydration sentinel bound to the server-observed release SHA. It marks the workspace verified only after the hydrated client DOM exposes:

- the exact release SHA;
- client contract `expert-engagement-hydrated-v1`;
- the canonical Comprehensive workspace identity;
- the exact English or Spanish engagement action;
- the exact localized engagement heading.

Unified Production Acceptance blocks service workers, sends no-store browser headers, adds a unique browser probe, waits for this hydrated contract, and only then starts the two live assessments.

The sentinel does not rewrite stale copy or accept legacy labels. It records the observed hydrated action and heading and fails closed when the browser bundle disagrees with the exact production release.
