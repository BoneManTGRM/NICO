# Improvement Opportunities

This file summarizes active improvement areas. The authoritative tracked backlog is GitHub issue #340, and current maturity is documented in `docs/PROJECT_STATUS.md`.

## Critical reliability and truth work

- Prove Express, Mid, and Full through repeatable authorized production E2E runs bound to exact deployment and run identities.
- Ensure every requested scanner executes or is returned explicitly as unavailable, failed, or timed out.
- Parse scanner-native results so severity and finding counts are not inferred only from exit codes or text fragments.
- Remove stale, conflicting, or legacy route labels that can misidentify Full output as Express or Mid.
- Expand restart, durable-storage, recovery, and duplicate-artifact tests.

## Productization

- Keep `/assessment` as the single normal start path for Express, Mid, and Full.
- Consolidate review, approval, delivery, recovery, diagnostics, and operations into clear advanced operator workflows.
- Improve empty, pending, not-loaded, unavailable, failed, and blocked state presentation.
- Add stable golden fixtures and recorded synthetic demonstration runs.

## Maintainability

- Split `nico/cli.py` into configuration, scanning, scoring, repair, drift, reporting, verification, and persistence services.
- Reduce compatibility and patch layers after canonical behavior is protected by regression tests.
- Keep canonical architecture and operator documentation synchronized with code.
- Add a supported console entry point and cleaner package metadata.

## Developer and deployment experience

- Add a one-command local full-stack setup with documented persistent storage.
- Expand environment examples without exposing secrets.
- Validate clean installation on supported Python and Node versions.
- Keep Railway, Vercel, CI, and exact-SHA release checks independent but mutually verifiable.

## Governance and public readiness

- Maintain contribution, security-reporting, issue, and pull-request standards.
- Publish stable, operational, experimental, legacy, and planned module status.
- Clearly distinguish synthetic evidence, live evidence, inferences, and unverified claims.
- Do not describe Reparodynamics as independently validated science until independent evidence supports that claim.
