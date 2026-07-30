# NICO report remediation execution plan

This plan is evidence-bound. Scores are never edited directly. A score may rise only after the underlying control is repaired, rerun against an immutable commit, and accepted by the canonical scoring engine.

## Phase 1: stop current production failures

- Support every approved premium scorecard heading in the final report-quality gate.
- Preserve English and Spanish report layouts.
- Require every canonical control row and score in the final PDF.
- Run NICO CI, production acceptance, mobile restart, iOS WebKit, security, report/scanner proof, and comprehensive production proof.

## Phase 2: scanner completion and provenance

- Make Bandit produce a retained exact-SHA artifact on clean and finding-bearing runs.
- Make Gitleaks use a version-compatible command path and retain a clean `[]` artifact when no leaks are found.
- Require full-history verification for Gitleaks and TruffleHog before history coverage is called complete.
- Fix ESLint dependency preparation and exact local parser resolution.
- Add two consecutive exact-SHA scanner reliability runs.

## Phase 3: finding truth and deduplication

- Deduplicate findings by canonical source location, rule, and evidence fingerprint.
- Keep test-only `exec`, TLS fixtures, and synthetic failure fixtures out of production risk scoring while retaining them in audit evidence.
- Require exact locations for dependency candidates or classify them as review-only, never material.
- Remove positive verification statements from limitation lists.
- Eliminate stale score-contract mismatch records after synchronized score truth is verified.

## Phase 4: dependency remediation

- Resolve or explicitly disposition every material npm, pip, and OSV finding.
- Upgrade constrained dependencies, regenerate lockfiles, and rerun all dependency scanners.
- Keep accepted residual risks documented with rationale and expiry.

## Phase 5: complexity reduction

Prioritize the report's highest actionable hotspots:

1. `apps/web/app/operations/page.tsx`
2. `nico/comprehensive_report_spanish_artifacts_v51.py`
3. `nico/comprehensive_report_spanish_text_v51.py`
4. `nico/retainer_evidence_ingestion.py`
5. `nico/retainer_modules.py`
6. `scripts/build_phase6_verification_package.py`
7. `scripts/production_assessment_browser_smoke.py`

Each refactor requires characterization tests, targeted tests, full regression, and a measured complexity rerun.

## Phase 6: CI reliability and report quality

- Classify historical non-success runs by cancellation, infrastructure, product defect, or obsolete workflow.
- Remove recurring genuine failures.
- Require current default-branch check health and two clean acceptance windows.
- Verify no duplicated risk cards, acceptance criteria, roadmap links, control characters, overlapping text, or stale delivery language.

## Completion gate

Work is complete only when:

- every required exact-head workflow is green;
- post-merge production acceptance is green;
- Bandit, Gitleaks, ESLint, Semgrep, TruffleHog, dependency scanners, and TypeScript have retained exact-SHA evidence;
- a fresh full report has no false production risks, duplicate findings, missing locations, stale contradictions, or layout defects;
- score changes are traceable to real remediation evidence.
