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
8. Final syntax check caught a translation inserted into a dict comprehension. Moved the explicit entry into a separate update; all 14 contract tests passed before PR publication.
9. Adversarial cross-format review found remaining draft banners and escaped literal span tags in the final HTML renderer. Added two failing language-path regressions; preserve inert evidence spans and project lifecycle prose outside them. Both now pass.
10. A 70-line evidence value crossed a PDF page. The full-value comparison failed on inserted page decorations; inspection confirmed every line retained in sequence. Strip only known page headers/footers in the comparison. Exclude duplicate raw human stage pages from generic PDF lifecycle projection, retaining the complete protected appendix. Contract plus Spanish integrity suites: 21 passed.

11. Initial CI completed: quality (including frontend/build/Docker) and nine shards passed; three shards failed in two stale separate-action-copy tests and the report golden/parity test. Updated copy assertions to the supported authenticated final action. The parity test additionally exposed missing nested work-package aliases in the readable roadmap summary; retain those references and assert nested mapping behavior. Refreshed only the changed artifact fingerprints after the remaining bilingual structural/reference assertions passed; page counts remain 21/39/20.
12. New-source lifecycle test exercises actual approval, authorization, integrity validation, and fresh persisted read. Source package remains byte-for-byte unchanged; approval/authorization advance revisions while specialist review and actual transmission remain false. All 17 focused contract tests pass; related copy/contract suite passed 43 tests.
13. Adversarial supplied text containing `artifact_schema`, `stage_execution.`, and `AUTOMATED FINAL` caused the final sanitizer to drop a human evidence page in both full language finalizers. Preserve dedicated supplied-evidence appendix pages verbatim at that sanitizer boundary. This is a source-retention fix, not a relaxation of internal-page cleanup elsewhere.
14. Once retained, that quotation triggered the report-prose finality gate. Partition renderer-owned prose from inert literal spans and renderer-marked PDF pages for presentation validation. Page ownership uses PDF metadata assigned by the appendix renderer, so text cannot impersonate it. Localization and approval presentation retain these marked pages. A missing `re` import was caught and fixed locally. The decisive full-language, lifecycle, and sanitizer suite passed 22 tests.

15. All 12 CI shards and quality/build passed on b1dd9f9d. Security Audit run 34784500203 blocked on the public Railway deployment ID recorded above. Fresh provider metadata confirmed the exact value; the owner explicitly authorized the proposed single-value disposition. A new regression failed before the change (1 failed, 13 passed). Add only the exact path/detector/value-hash exception, retain the finding, and preserve rejection of verified findings, other values, other detectors and other paths. No scanner execution, threshold, or unrelated disposition changed.

PR: https://github.com/BoneManTGRM/NICO/pull/1593. Required CI will rerun on the revised commit. No merge or corrected production acceptance claimed yet.
The prepared ten-module synthetic run is necessary to exercise the corrected intake-to-export path without modifying the already approved historical source edition. It has not yet been submitted.

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
