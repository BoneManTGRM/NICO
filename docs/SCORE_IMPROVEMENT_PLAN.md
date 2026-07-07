# NICO Score Improvement Plan

This document tracks legitimate ways to raise NICO Express scores without weakening evidence rules.

## Current blockers

1. Frontend npm audit findings keep dependency evidence from going green.
2. Hosted Express assessment needs stronger scanner-artifact ingestion for security and static-analysis evidence.
3. JavaScript lockfile evidence is absent from the repository, so dependency reproducibility is weaker than it should be.

## Active remediation

PR #38 upgrades the frontend Next.js dependency from `14.2.23` to `16.2.10`, the fix target reported by npm audit. This should reduce or remove the critical Next.js audit finding if CI confirms the major upgrade is compatible.

PR #38 also adds a scanner-artifact scoring bridge. When an authorized GitHub token is configured, hosted Express scoring can read current GitHub Actions artifact JSON and map it into section evidence:

- `credential-scan.json` -> Secrets Exposure Review.
- `bandit.json` and `semgrep.json` -> Static Analysis.
- `pip-audit.json` and `npm-audit.json` -> Dependency / Library Ecosystem.
- Current evidence artifact sets -> CI/CD Analysis.

PR #38 also updates Node.js CI so frontend validation runs on `main` pushes, not only pull requests and the old foundation branch. This gives stronger current CI evidence after merge.

## Next improvements

- Add committed lockfile evidence after generating it from a clean `npm install` in `apps/web`.
- Add report UI fields showing which scanner artifacts directly affected each section score.
- Keep unavailable, stale, or failed scanner artifacts visible and do not treat them as green.

## Rule

Scores may improve only when actual evidence improves. Missing evidence, vulnerable dependencies, stale artifacts, and failed scans must remain visible.
