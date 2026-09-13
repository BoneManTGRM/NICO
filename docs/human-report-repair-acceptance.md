# Human evidence and report truth repair — acceptance ledger

Scope: human evidence export, exact-edition lifecycle presentation, absent metrics,
readable planning records, and assessment coverage labels. No client transmission.
No claim of completed specialist review, QC, accessibility, or runtime parity.

## Baseline identities

- Branch: main; checkout HEAD: `7fde559d83a37e35268cdc8ae8597a51625317ef`.
- Frontend `/api/release` and Vercel: same SHA, deployment `dpl_3dHEw1DJPctzTpa9e7kR3noXg3By`.
- Railway NICO production: same SHA, deployment `57588a18-cd2e-43bf-a46d-4324a60d237a`.
- Historical synthetic run: `comprun_754dcabf78c0e6aa17cea5e1534671ea`, reviewed 67, approved 68, authorized 69.
- Original reviewed PDF in supplied ZIP: `d91552a2dda50ea4ba76a774be71b1370006a4817ed1fba2c73cd6cd07ea155a`.
- Original authorized PDF in ZIP: `44dcb118a128c7a4c740bbdc1f3acd46886f02c2bbe86e4dfecbfa75fe91b553`.
- Separately saved NICO-Human-Workflow-Test-Final.pdf differs: `36b263647282017e1fffbaccefdd100e9cd90643229dd90ed31096491b9448c6`.
- Supplied minimal-input PDF SHA-256: `49882e92bb394586c6e454481d850d681d39061a8cee6196eef8dd57336ee2f0`.
- All originals retained unchanged. The actual minimal-input PDF independently reproduces the empty CI metrics, raw roadmap objects, contradictory delivery narrative, and separate-action guidance.

## Acceptance

| Criterion | Baseline and cause | Repair and local evidence | Production status |
|---|---|---|---|
| A: all ten modules | Canonical-only final publication bypasses legacy human-context wrapper; compact PDF composition drops module pages | Bind verified payload at canonical source, preserve exact raw subtree, inject readable stages, reserve dedicated PDF appendix; typed evidence CSV rows bind each module, supplier, observation time, source reference, and module hash | Pending deployment and new reviewed edition |
| B: missing evidence | Processing status is rendered as coverage despite existing assessment_dimensions | Stage projection uses explicit substantive coverage; execution status remains separately retained | Pending |
| C: exact lifecycle | Operator presentation misses separate approval-truth table cells; Markdown/HTML/JSON retain stale appendix states | Opt in only newly generated sources; update report-owned lifecycle nodes and appendix, retain specialist work and historical source; legacy rendering remains unchanged | Pending |
| D: metrics and roadmap | Falsy numeric zero becomes empty string; English planning renderer stringifies mappings | Preserve zero, label unavailable values, format stable planning references; separate specialist acceptance from delivery permission in prose | Pending |
| E: controls | Required gates include NICO CI quality and 12 isolated test shards, security audit | Focused new regression baseline: 6 failures, 1 pass before repair. Subsequent targeted runs: 32, 26, 81, and 26 passing tests (overlapping suites, not a unique count) | Required CI and affected production controls pending |

## Failed checks and decisive follow-up

1. Fresh scratch had no checkout; authenticated connector established repository access and public clone succeeded. Git push has no CLI credential; use the authorized GitHub connector for publishing.
2. Default Python lacked pytest. Created an isolated environment and installed repository-pinned dependencies; focused tests execute there.
3. Canonical-boundary test lacked supplied payload; traced production `v2_production_authority` to canonical builder and added retention there. Exact module comparison now passes.
4. Full finalizer retained JSON/Markdown but PDF lacked all ten suppliers. Traced compact composer; added reserved appendix. All ten suppliers now occur in the full finalized PDF (26-page local fixture).
5. A sparse canonical fixture failed an existing limited-review-count gate. Continued artifact verification using the existing finalizer fixture with valid report context; no gate was relaxed.
6. Spanish canonical preflight treated verified literal lines as report prose after its translator rebind. Reinstalled the existing client-literal guard after preflight installation. Raw supplied payload is explicitly excluded from localization.
7. An assembled Spanish test fixture initially omitted projected identity literals. Restored the canonical builder's supplied identity projection in that fixture; no fallback translations of client content were added. Full English and es-MX finalizer tests now pass, including all ten modules in PDF, exact canonical JSON, and CSV mapping (14 focused contract tests).

## Export schema

New editions carry `human_report_export_schema: nico.human_report_export.v1`.
`supplied_human_evidence` retains the digest-verified durable intake package exactly,
including all ten module states and digests. A verified transport digest establishes
integrity, not independent evidence validation. Supplied material remains unverified.
The evidence CSV v2 uses `record_type` to distinguish scanner candidates from human
module records. Human rows include exact structured evidence plus a canonical JSON
pointer and provenance. Findings/candidate registers remain scoped to findings and
scanner candidates; they do not manufacture findings from human input.

Original source editions, decisions, certificates, and delivered bytes are not
overwritten. Substantive corrected evidence requires a newly generated source edition
and fresh exact-edition review/approval. Delivery permission is not transmission.
