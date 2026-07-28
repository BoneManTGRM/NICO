# Phase 5: Report Truth and Outcome Verification

## Mission

Make the Comprehensive report visibly reflect real system improvements while preserving evidence integrity. No score, scanner state, finding, limitation, readiness label, or client-delivery posture may be changed unless the exact-SHA evidence supports the change.

## Non-negotiable truth rules

1. Never replace a failed, partial, unavailable, unknown, or review-limited result with a clean or completed result.
2. Never raise a score because a workflow passed unless the report control consumed the same retained evidence for the same immutable commit.
3. Never suppress a real finding. False positives may be removed only through a traceable rule correction and an exact-SHA rerun.
4. Never classify historical workflow outcomes without retained workflow, job, conclusion, actor, event, timing, and commit provenance.
5. Never claim a complexity reduction unless the report's production analyzer measures the reduction on the final commit.
6. Never mark a report client-ready without all configured delivery gates and authorized human approval.
7. English and Spanish packages must carry equivalent evidence, findings, scores, limitations, and delivery posture.

## Baseline report

The Phase 5 baseline is the Comprehensive assessment for commit `b376f6807953de5a41e41b3e408e79da715bfa0c`, run `comprun_88bbe05a25c24d2cbfa5b806e0d6a373`.

Observed baseline conditions include:

- Technical maturity: 85/100.
- Evidence-adjusted readiness: 83/100.
- Client-ready: No.
- Bandit and ESLint reported failed.
- Gitleaks and OSV reported partial.
- Disabled-TLS candidate reported at `nico/scanner_evidence_pipeline_v1.py:478`.
- Historical workflow non-success count reported without report-visible cause classification.
- Mutable GitHub Action references reported.
- Named Python and TypeScript complexity hotspots remain above target.

These values are observations, not targets to manipulate.

## Outcome packages

### Package A — Scanner/report reconciliation

- Trace the exact artifact consumed by the Comprehensive report for every required scanner.
- Make report scanner status derive from the retained exact-SHA artifact, not a separate CI-only qualification result.
- Repair Bandit, ESLint, Gitleaks, and OSV execution or retain accurate failure/partial status with a precise reason.
- Require two deterministic exact-SHA passes before reporting a required scanner as completed.

Acceptance:

- The generated report's scanner table matches the retained scanner artifact byte-for-byte by tool, status, commit, run, version, finding count, and artifact hash.
- No scanner is shown as completed when its retained evidence is incomplete.

### Package B — False-positive-safe security remediation

- Review the disabled-TLS location and distinguish executable production behavior from analyzer/configuration text.
- Remove the finding only if exact-source review proves it is not executable insecure behavior and the corrected rule no longer reports it.
- Repair any genuine TLS-verification disablement instead of suppressing it.

Acceptance:

- Every disposition records the exact file, line, rule, rationale, reviewer state, and rerun result.
- The P1 disappears only when the exact-SHA evidence supports closure.

### Package C — CI history integration

- Feed Phase 3 workflow classifications into the report data path.
- Separate genuine failures, cancellations, superseded runs, skipped outcomes, infrastructure faults, manual stops, and unknown outcomes.
- Unknown or contradictory outcomes remain review-required.

Acceptance:

- The report shows classified counts and provenance rather than only a raw non-success total.
- The displayed totals reconcile to the retained workflow window.

### Package D — Workflow supply-chain truth

- Inventory every `uses:` reference in active workflows.
- Pin references to immutable full commit SHAs or record a controlled exception with owner and rationale.
- Ensure the report analyzer recognizes immutable references correctly.

Acceptance:

- Mutable-reference findings disappear only for references that are actually immutable or explicitly approved as exceptions.

### Package E — Real complexity reduction

- Decompose the named report builders and frontend workspaces using behavior-preserving characterization tests.
- Measure using the same production analyzer used by the Comprehensive report.
- Do not count tests, comments, renaming, wrappers, or file movement as a complexity reduction.

Acceptance:

- Each repaired hotspot shows an exact before/after complexity, LOC, nesting, and method comparison in the newly generated report.
- No target is declared complete solely because CI passed.

### Package F — Before/after report proof

- Generate a new Comprehensive package from the final validation commit.
- Compare baseline and final report values by stable finding ID and control ID.
- Preserve unchanged risks and limitations without cosmetic hiding.

Acceptance:

- The PR cannot merge without an attached machine-readable delta showing added, removed, changed, and unchanged findings with reasons.
- The PDF, Markdown, JSON, and CSV packages reconcile to the same final truth ledger.

## Merge policy

Phase 5 remains open until a newly generated Comprehensive report demonstrates the intended outcomes. Green CI alone is insufficient. A change is complete only when implementation, retained exact-SHA evidence, report rendering, and cross-format verification agree.
