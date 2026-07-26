# NICO engagement workspace acceptance

The assessment interface represents an expert-led technical advisory engagement rather than a self-service scanner.

## Required public behavior

- One semantic assessment workspace: `data-workspace="assessment"` and `data-engagement-type="comprehensive"`.
- No visible Express/Comprehensive selector.
- Repository authorization remains explicit.
- Optional human evidence remains fail-closed: omitted modules are Not assessed.
- Readiness is checked before an engagement is created.
- A blocked preflight renders one client-safe notice and does not claim that a run failed.
- An accepted run keeps its exact run ID and resumes that run after a transient interruption.
- Raw persistence, database, backend-route, and deployment details are not rendered to public users.
- Automated output remains subject to expert review and approval before client delivery.

## Mobile behavior

At 375px and 430px:

- The primary action remains reachable and full width.
- Human-evidence intake is collapsed by default.
- Modules use compact summaries and explicit Add evidence controls.
- Metadata and evidence fields stack to one column.
- Service failures use a compact amber or red-accent notice, not multiple full red panels.
- Retry targets are at least 44px high.
- No horizontal scrolling is introduced.

## Visual direction

- Graphite background and restrained elevated surfaces.
- Cyan reserved for active actions and evidence relationships.
- Emerald reserved for verified completion.
- Amber reserved for attention and recoverable blockers.
- Red reserved for actual failures and critical risk.
- Geist Sans for interface typography and Geist Mono for technical identifiers.
- Motion is restrained and disabled when reduced motion is requested.
