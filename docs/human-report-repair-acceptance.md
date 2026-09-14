# Human evidence and report truth repair — acceptance ledger

Scope: human evidence export, exact-edition lifecycle presentation, absent metrics,
readable planning records, and assessment coverage labels. No client transmission.
No claim of completed specialist review, QC, accessibility, or runtime parity.

## Current production continuation: mobile review contract

PR1597 merged as688ccb4254d2933a53063a2b453d2f072cb15d5f; both deployment
providers and the live frontend identify that release. All required CI passed.
Spanish production34800800422 passed fresh normal/exclusion publication and its
simulated browser matrix. Original artifact10331980172 has SHA256
50bbd3df4693ac3b8cc38f048317ff02f11bfd8a0740e69dcc27d1dc0d6594cb.
All-module run6b9a0d source65 -> approved66 -> authorized67 passes exact evidence,
provenance, final-PDF and fresh-state checks; specialist work remains unfinished,
transmission false. Minimal-input run7dc93d rendered on688ccb passes23 original-byte
checks, including preserved permission, absent descriptions and separate coverage.
Full identities and artifacts are retained in the external acceptance bundle.

Mobile Restart34801842005/job103845929106 then timed out at the read-only review
locale check: it waited for `accepted-edition-v2`, while the dedicated Comprehensive
page actually renders `final-report-independent-v1` and its corresponding localized
heading. The authenticated live page independently confirms this contract. The
same helper serves Chromium and WebKit. Two English/Spanish behavioral regressions
failed before updating only the selector and expected headings; five negative cases
preserve rejection of wrong run, language, heading and legacy workspace. All16
focused current-surface/single-dispatch/layout checks pass. No authentication,
approval, timeout, source-run mutation, app or report-renderer code changed.
The initial isolated test import required unavailable Playwright; extracting the
actual standalone helper from its AST avoids importing the browser launcher in unit
tests. This is a test setup correction. Integration and deployed consumer retest
remain pending at this checkpoint; no unchanged failed workflow was rerun.
CI34802476585 shard4/job103847755064 exposed a pre-existing assertion pinning
both mobile and desktop consumer helpers to the obsolete selector. The desktop
helper independently contained the same stale selector/headings and old boundary
copy. Its two current-page cases reproduced the absence; two disclosure-negative
cases also stopped at that absent workspace before reaching the disclosure check.
Update the desktop helper to the same observed page contract and assert the current
one-action/specialist-review/no-automatic-transmission disclosure. Update the
existing projection-wait assertion without removing its wait-before-read check.
All84 focused surface, handoff, single-dispatch and layout cases pass. Mandatory
CI must run again on the changed candidate.

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
| A: all ten modules | Canonical-only final publication bypasses legacy human-context wrapper; compact PDF composition drops module pages | Bind verified payload at canonical source, preserve exact raw subtree, inject readable stages, reserve dedicated PDF appendix; typed evidence CSV rows bind each module, supplier, observation time, source reference, and module hash | First deployed edition: exact ten-module canonical/PDF/Markdown/HTML/CSV comparison passes; spacing correction requires a fresh edition |
| B: missing evidence | Processing status is rendered as coverage despite existing assessment_dimensions | Stage projection uses explicit substantive coverage; execution status remains separately retained | Historical artifact reproduced; legitimate absent-input fixture passes locally; affected production edition pending |
| C: exact lifecycle | Operator presentation misses separate approval-truth table cells; Markdown/HTML/JSON retain stale appendix states | Opt in only newly generated sources; update report-owned lifecycle nodes and appendix, retain specialist work and historical source; legacy rendering remains unchanged | Production source 66 → approved 67 → authorized 68; downloaded hashes and fresh state agree; specialist review unfinished, no transmission |
| D: metrics and roadmap | Falsy numeric zero becomes empty string; English planning renderer stringifies mappings | Preserve zero, label unavailable values, format stable planning references; separate specialist acceptance from delivery permission in prose | Production metrics and roadmap readable; visual review found review-form background overlap, corrected below |
| E: controls | Required gates include NICO CI quality and 12 isolated test shards, security audit | Focused new regression baseline: 6 failures, 1 pass before repair. Subsequent targeted runs: 32, 26, 81, and 26 passing tests (overlapping suites, not a unique count) | All 12 shards, quality and Security Audit passed on merged repair; protected download rejects unauthenticated access; follow-up CI required |

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

PR https://github.com/BoneManTGRM/NICO/pull/1593 merged as `64a2db8ff11fa2e336cf3a45e7f0e3c6b18dfd54`. Required CI run 34785533095 and Security Audit run 34785533116 passed. Provider deployment metadata, frontend release identity, backend native runtime identity, and the produced canonical package establish that merge as the actual producer. Stale configured release labels remain separately disclosed in the external acceptance evidence; they are not treated as deployed identities.

The new synthetic run `comprun_ffe046f757500c9eb2ed5198a8fa29f2` exercised intake-to-export without changing the historical immutable edition. All ten modules retain exact submitted fields, provenance, supplier, observation time and unverified status. A 2,282-character multiline value remains complete. Typed CSV and Markdown/HTML comparisons also pass. Source revision 66 PDF SHA-256: `50e285d0b094db7ebeb2c94c8ad0c7dd8fc97c2aa6cae852905a52276361487d`. The exact review download matched those bytes. One acknowledged approval action advanced through operator-approved revision 67 to authorized revision 68; a fresh read agrees. Authorized PDF SHA-256: `99036200eb7c3122eb2bdc97d74f504e0192afec619d09193637f8b02a8371ec`. Specialist review remains incomplete and actual transmission remains false.

16. Production visual review found a following boundary background partly covering the reviewer/date line. A drawn-coordinate regression failed on both English and Spanish in the legacy renderer. Increased only the boundary's preceding spacing. Runtime-path inspection then identified the installed polished renderer as the actual production path; extending the test reproduced the same overpaint there (2 failures, 4 passes). Applied the same narrowly scoped spacing correction there. All six geometry/companion tests pass, and the actual production canonical rendered through that path was visually inspected with a clear reviewer line. PDF-only golden fingerprints were refreshed after structural, reference and language assertions passed; Markdown/HTML and page counts did not change. No substantive evidence or lifecycle projection changed. The approved production edition is preserved; final visual acceptance requires a separately generated edition after deploying this correction.

## Export schema

### Post-merge production-proof follow-up

PR #1594 merged the spacing repair as `ee12b8d87215f40e09b78ba65381967290660abf`.
Its main CI and Security Audit passed. Spanish production proof run 34789064959
failed while exact-run telemetry for `comprun_98485dbe9f43c21c195e551ba8576e01`
still reported `running`, `terminal: false`, and background final-report publication.
The UI instead displayed a failed assessment. Mobile Restart 34789304769, iOS
WebKit 34789304736, and Unified Acceptance 34789304759 failed their successful
Spanish-source prerequisite; their live checks did not execute. The owner asked
to repair these failures. The original failure artifact is retained externally.

The global failure-response bridge did not enforce the explicit terminal marker
already required by the Comprehensive run controller. Behavioral tests reproduced
false failure events for a stale blocked status, a blocked report contract during
publication, and missing terminal authority (3 failed, 10 passed before repair).
The bridge now requires the top-level `terminal: true` before normalizing a
Comprehensive failure. Nested diagnostics cannot override that authority. Genuine
terminal failures, artifact-integrity blocking, pending human approval, transport
errors, and legacy Express behavior have independent regression cases. This is a
demonstrated projection defect and a candidate cause of the observed production
failure; production reproduction must establish whether another cause remains.
No proof timeout, recovery classification, scanner policy, persisted assessment,
report bytes, or approval contract changes in this follow-up.

The separately generated populated run `comprun_6b9a0dff45c60fa84e08e9869f88972b`
remains preserved for final visual/report acceptance. Its submitted fields were
compared before intake. Browser authentication expired before the exact report
could be downloaded and approved. Secure sign-in retries returned
`submission_failed` without a visible website error; authentication is unproven.
Criteria A–D still require affected final production artifact checks; E requires
the new branch gates and post-deployment production-proof results. Prior accepted
source 66 / authorized 68 evidence above remains valid for unchanged dependencies.

PR #1595 passed all 12 test shards, quality, Security Audit, and supporting gates,
then merged as `dea3e33d9063cc127d4ba9046f664e56209f8c60`. Both deployment providers
and the live frontend release endpoint identify that exact merge. Fresh protected
download, review, and authorization probes still reject unauthenticated requests.
Production proof 34792745228 then reached a genuine terminal failure for
`comprun_f1c059ec310641d8dcce6769adec4271`: Spanish publication rejected
`Historical genuine-failure rate: Unavailable.`. Delivery stayed blocked. This
refines the earlier hypothesis: the browser projection gap was real, but the
renderer also lacked a contract for the newly explicit availability label.

The compact CI stage emits capitalized `Unavailable`, while strict Spanish
structured-prose rules recognized lowercase availability only for the historical
rate and did not handle the compact missing-value forms of required-check health.
Other compact metric labels could remain partly untranslated. A generated-stage
regression reproduced 52 failures and 9 passes across missing and numeric values.
Translate only the recognized compact labels and scalar/availability forms;
preserve zero and retained health states, and keep malformed structured prose
rejected. Canonical evidence and report lifecycle state are unchanged.

The same operational-stage review independently reproduced two value-loss paths:
an outcome-class zero became empty text, and a recorded false default-branch
required-check result became unavailable. Three additional regression cases failed
before correction. Preserve numeric outcome counts, render that recorded boolean as
green/not_green, and translate historical outcome-class names with strict validation.
Booleans are still not accepted as measured counts or rates. Assessment permission,
operator approval, and delivery authorization are separate and unchanged.

The added compact-finalizer smoke test initially expected every intermediate
metric line in a renderer that consolidates CI context. Inspection established
that fixture mismatch. Exact field/label comparisons remain in the generated-stage
tests; the finalizer test instead verifies publication, canonical zero/absence,
Spanish prose and the unchanged approval boundary. Existing bilingual parity and
PDF geometry tests pass without golden-file updates. The next production proof
must confirm publication before the dependent workflows can establish acceptance.

The combined parity run then exposed a real installed-translator interaction:
v98 replaced metric labels before v87 could validate and translate the whole line,
leaving English `Unavailable` behind (19 failures). A focused installed-chain
regression independently reproduced it. v98 now delegates complete metric lines
to the strict canonical grammar before phrase substitution; unknown values still
fail closed. The decisive combined canonical parity/metric retest passed 82 tests.
No golden artifacts were updated. Final required CI and production proof follow.
An adversarial multiline metric input then reproduced a whole-block grammar
rejection. The same strict translator now handles each line while preserving CRLF
and LF endings. The focused regression failed before the two-line correction.
CI then found the existing standalone-label contract also matched the new metric
guard. The existing v98 regression reproduced this locally. Require the colon
separator for metric validation; standalone translated headings remain valid.

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

### Percentage publication follow-up

After PR1596 deployed, authenticated inspection of retained synthetic run
`comprun_8373581b34ac0416da9a6b5171f3f7de` exposed the exact final-stage error:
`unrecognized Spanish presentation contract: Observed job success rate: 100%.`
The transient active-publication observation did not establish a UI defect. The
persisted terminal error identifies an omitted percentage grammar in v87.

Four focused cases reproduced rejection of 0%, 12.5%, 100%, and 100.0%. A four-line
grammar addition accepts percentages from 0 through 100 only for observed job
success rate, preserving exact digits and the percent unit. Counts, malformed
values, out-of-range percentages and appended untrusted prose remain rejected.
The generated-stage and installed-v98 tests retain canonical evidence unchanged.
Retest: 101 passed across metric availability, existing worker-copy contracts and
current report truth parity. No golden, lifecycle, scanner, or authentication
changes. Required CI and production acceptance remain pending for this follow-up.
