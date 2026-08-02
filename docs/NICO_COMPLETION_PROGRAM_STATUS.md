# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

Earlier exact production observations remain available in the `docs/production-*observation.json` files and immutable workflow artifacts.

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, security, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Current production main: `9d26a71f8ac70bf0d0fb8129e8d7ac5654b14130`

Current continuation: PR #998, branch `codex/canonical-maturity-label-truth`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge production failure

PR #997 retained compact exact-SHA scanner evidence during the scanner stage and removed final-stage scanner-store reads, repository cloning, scanner execution, raw findings, and output previews. It passed every exact-head check and merged as `9d26a71f8ac70bf0d0fb8129e8d7ac5654b14130`. Vercel and Railway exact production identity were verified.

The mandatory Mobile Restart proof created exact run `comprun_07f23ee3e93341e9b2508b5881f4e0cd`. The final stage now returned a bounded retained diagnostic instead of timing out. Canonical source preparation took 0.004 seconds.

The strict semantic publisher stopped the report with:

`v2_production_publication_failed:ValueError:client report retained a maturity label conflicting with Exceptional: maturity_level: Senior`

The former final-stage scanner-store timeout is no longer the active root cause. The run is blocked because the report contains contradictory maturity taxonomies.

## Verified maturity-truth defect

The final client-readiness contract classifies maturity as `Exceptional`. Older internal stage evidence still contains the explicit alias `maturity_level: Senior`.

Stage evidence is flattened into report surfaces before final semantic validation. The validator correctly rejects the resulting Markdown, HTML, JSON, and PDF package rather than delivering a report that simultaneously says `Exceptional` and `Senior`.

This is a maturity-label sequencing defect. It is not a reason to weaken or bypass the semantic gate.

## Active continuation

PR #998:

- derives one authoritative maturity label from `client_readiness_contract.maturity_label` before report stage evidence is flattened;
- synchronizes explicit structured aliases including `maturity_label`, `maturity_level`, `maturity_rating`, `maturity_tier`, and maturity-signal `level` and `label`;
- synchronizes only explicit text aliases such as `maturity_level: Senior` and `maturity label = Senior`;
- does not perform a general replacement of the word `Senior`;
- preserves unrelated reviewer seniority, role descriptions, and ordinary prose;
- leaves source stage evidence unmodified;
- does not traverse already-rendered report artifacts;
- retains a machine-readable maturity-label truth manifest in the assessment, canonical JSON, report package, and source envelope;
- preserves the strict semantic validator, single authoritative v2 renderer, atomic publication boundary, and retained scanner evidence path;
- changes no score, scanner result, finding, report design, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #998 exact-head CI, CodeQL, security, frontend, Postgres, resilience, report, Mobile Restart, iOS WebKit, and production-acceptance check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- post-merge Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass;
- two distinct fresh Comprehensive runs reach expert review without manual stage recovery;
- status endpoints remain responsive during final report publication;
- canonical and rendered maturity labels agree in Markdown, HTML, JSON, and PDF;
- final report generation completes inside the atomic boundary with one authoritative render and no final-stage scanner-store read;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked or running contract is presented as current truth;
- all approval and client-delivery boundaries remain visible.
