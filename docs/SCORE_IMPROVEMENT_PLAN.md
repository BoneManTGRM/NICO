# NICO Score Improvement Plan

This document tracks legitimate ways to raise NICO Express scores without weakening evidence rules.

## Current blockers

1. Frontend npm audit findings keep dependency evidence from going green.
2. Hosted Express assessment needs stronger scanner-artifact ingestion for security and static-analysis evidence.
3. JavaScript lockfile evidence is absent from the repository, so dependency reproducibility is weaker than it should be.

## Active remediation

PR #38 upgrades the frontend Next.js dependency from `14.2.23` to `16.2.10`, the fix target reported by npm audit. This should reduce or remove the critical Next.js audit finding if CI confirms the major upgrade is compatible.

## Next improvements

- Add committed lockfile evidence after generating it from a clean `npm install` in `apps/web`.
- Ingest Security Audit Evidence artifacts into hosted Express scoring:
  - `credential-scan.json` should support secret-scanning evidence.
  - `bandit.json` and `semgrep.json` should support static-analysis evidence.
  - `npm-audit.json` and `pip-audit.json` should support dependency evidence.
- Add report UI fields showing which scanner artifacts directly affected each section score.
- Keep unavailable, stale, or failed scanner artifacts visible and do not treat them as green.

## Rule

Scores may improve only when actual evidence improves. Missing evidence, vulnerable dependencies, stale artifacts, and failed scans must remain visible.
