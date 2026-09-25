# NICO — reconciled post-merge continuation, PR1644 and PR1645

This is the sole active mission-ledger path. All original full C/C++ and frozen Bitcoin C0–C19 requirements, resource/security boundaries, historical immutability and genuine human approval requirements remain binding. Neither corrective PR is mission completion.

## Immutable continuity and single-writer coordination

Preserve the complete prior PDF/native-diagnosis checkpoint at [41545933](https://github.com/BoneManTGRM/NICO/blob/415459333b4e4ad86ecf47bc1bb072a9b480e37f/NICO-Ship-Checkpoint.md), including its [31269344](https://github.com/BoneManTGRM/NICO/blob/312693443b1e70c8a065de2c4e9ca329281d162a/NICO-Ship-Checkpoint.md) and 1bae/cefff/3ff747f8 predecessors. Preserve the independently recovered runtime-correction checkpoint at [a928951f](https://github.com/BoneManTGRM/NICO/blob/a928951f7ea38db182cf717cdf1f63bb88e3eda3/NICO-Ship-Checkpoint.md). This reconciliation supersedes the earlier statement that no runtime correction exists; its actual native qualification remains unfinished.

Main was re-read as `312693443b1e70c8a065de2c4e9ca329281d162a`, tree `0373f40d585471162c674dc7870fa6dee3784571`. PR1641 is merged at `0f14a8dba3c0fa6d11d982e007492a7f543ccfb7`; PR1643 is merged at current main. Do not reopen either.

Existing [PR1644](https://github.com/BoneManTGRM/NICO/pull/1644), branch `fix/cpp-runtime-scratch-retention`, head `a928951f7ea38db182cf717cdf1f63bb88e3eda3`, is draft and unmerged. It contains the runtime reclamation/failure-retention correction. This continuation recovered it and did not modify that branch, cancel its run or create another runtime implementation.

[PR1645](https://github.com/BoneManTGRM/NICO/pull/1645), branch `fix/client-pdf-register-conservation`, is draft and unmerged. Tested application/test source is `798c49a8813a989b676c2699833526d5141f3f87`, preceded by test commit `10176d8bc11d8370f30229c57a3592761e8045a4`. Evidence was added at `fef6a20532934530ea77fd431b9c3e6c815bba30`; later checkpoint commits do not change tested source bytes.

Both PRs update the same ledger path. Reconcile their latest heads and verified facts before integration; do not blindly overwrite either version, force-push, launch competing writers or duplicate the active native campaign. A [bounded coordination/security-evidence comment](https://github.com/BoneManTGRM/NICO/pull/1644#issuecomment-5833375653) links the two corrections. GitHub branch/file writes have actually succeeded; a blanket source-publication tool blocker is obsolete.

## Frozen target and preserved subproofs

Target: `bitcoin/bitcoin` at `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Retain complete inventory/acquisition, all475 compiler contexts including generated/repeated configurations, all377 baseline tests, Linux Debug wallet/tests/IPC, substantive static/fallback analysis, the frozen functional/sanitizer/fuzz population and declared exclusions.

The distinct historical commit `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` remain unchanged. No final Bitcoin production run is inferred from a qualification, progress percentage or HTTP200.

Both retained failed native artifacts were downloaded and hash-verified: run36127119592/artifact10862967834, ZIP SHA256 `2a6056ce7b74ce1ec501c6b0777bf91f0a40a47ac8b5ae9df5da4fb606d0fe7b`; run36129521112/artifact10865403350, ZIP SHA256 `4249b1b26d0cabc76704e0f29b093c708acdc0736b87d4f0ba09a7ffa0f361df`.

They retain 3,031 materialized source files /49,729,651 bytes,377/377 baseline tests passed,475/475 compiler contexts checked, generated inputs and cleanup, plus6/6 functional tests passed including wallet migration and IPC. Their first failing runtime operation is the ASan build: exit2, no timeout/truncation, linker signal9 followed by explicit `No space left on device`. Each subsequently executes222/377 ASan tests with155 skipped; UBSan/fuzz and the fresh static stage do not execute. Runtime remains incomplete. Memory peak12,884,901,888 bytes and scratch capacity9,663,676,416 bytes are recorded; there is no retained OOM-event counter proving who killed the linker.

Exact data-only replay of the actual retained runtime plan and evidence reproduces the downstream validator failure at runtime-execution line430: required sanitizer kinds `[address, undefined]`, retained `[address]`. Plan SHA256 `09588b0e6222ec84538b9467c0c8366debbfee06accf22f54078a54c961976d1` agrees with receipt/evidence. No malformed evidence was accepted or completion flag changed.

## Existing runtime correction and active qualification — preserve, do not repeat

PR1644 reclaims only fixed completed baseline/functional/sanitizer directories after retained results and before subsequent phases. It uses descriptor-relative symlink-resistant removal and before/after space measurements; source, analyst snapshots and unit-test assets are not cleanup targets. It retains first failed operations before interpretation, prevents dependent execution after failure, and binds ordered cleanup through runtime-evidence v2 while preserving v1 reconstruction. No source/test population, resource ceiling, network/credential boundary or approval rule is reduced.

Its own retained verification records21 RED/identical GREEN cases,13 additional adversarial/legacy tests, and168 affected local passes. Those are the runtime author's recorded tests, not a fresh execution by this PDF continuation. See [exact runtime evidence](https://github.com/BoneManTGRM/NICO/blob/a928951f7ea38db182cf717cdf1f63bb88e3eda3/docs/evidence/cpp-runtime-reclamation-20260925/verification.json).

Fresh hosted metadata for [run36138550814](https://github.com/BoneManTGRM/NICO/actions/runs/36138550814) on a928 shows contract-regressions, toolchain inventory, exact source and owned-project integration successful. Combined native job `108086221842` is IN_PROGRESS in its execution step; evidence upload remains pending. This is not terminal native success. Do not cancel/retry or dispatch another campaign without changed inputs and justification.

## PDF correction and actual-input gap

PR1645 repairs reproduced unknown/shared-page/prose-prefix boundary losses while keeping the60-page fail-closed gate and mandatory canonical register/companion pages. Composer blob `8cd348edce7cbc549f699d30164e2f8d0e7bea4b` and new-test blob `8b28f284c371ec58573e8a8c0aa5284bd5cf46eb` match tested/published bytes. Existing tests were not weakened.

Exact-main RED:16failed/6passed. Identical new-suite GREEN:22passed. Disjoint affected groups37+14=51 distinct passes, zero failures/errors/skips;22 is included in37. Local Python3.13/pypdf5.9.0 is not pinned hosted golden parity. Two labeled synthetic five-page EN/es-MX controls were rendered and visually inspected: three retained primary pages pixel-identical to base, no off-page text spans. They are not Bitcoin reports or physical-iPhone evidence. Commands, source/artifact hashes and limits: [PDF verification index](docs/evidence/pr1643-register-conservation-20260925/verification.json).

Actual failing inputs/diagnostic PDF and immutable run contract for `comprun_29c30048215275ecbac35d179f71a1ed` have NOT been retrieved. Its historical1132-page exception does not establish that a PDF was stored. Unknown continuation content may safely retain extra pages and fail the unchanged budget; synthetic cases do not prove the actual production failure repaired. Do not merge solely on those cases or a green badge.

## Security gate — exact nonsecret finding identified, repair not applied here

PR1644 Security Audit Evidence run36138550945 failed. Retained artifact10864619748 is229931 bytes; ZIP SHA256 `b8f68ec097acc9615d6e8f2eebc49e674afde363ffbc12e81711e0a9527f0c16`. Its only blocker is TruffleHog RailwayApp, Verified=false, a928:NICO-Ship-Checkpoint.md:9. The exact Raw value equals the authenticated-Railway-metadata deployment ID `e045965c-ca52-42dc-858f-ef18bf563266`. Identifier SHA256 `1980b2f6dab7776d10baa4343cca6b20d8af6aaec1a99137932989a3a81fff37`.

The evidence and smallest exact path/detector/Verified=false/digest disposition were posted to the existing runtime PR. No disposition code was changed by this continuation. Require meaningful RED/GREEN adverse tests and unchanged-byte replay retaining all104 observations and other scanner/review outcomes. Never add a general UUID exemption or suppress the scanner. This remains a failed check, not an unresolved credential identity or passing gate.

## Serving identities and precise access boundary

Live Vercel alias `app.nicoaudit.com` resolves to production deployment `dpl_8peLtPtpFF839XWMbhwiQZkK2Dt1`, READY, main31269344. Railway deployment `e045965c-ca52-42dc-858f-ef18bf563266` is successful on the same source; its healthcheck succeeded2026-09-25 12:23:05UTC. These verify platform deployment mappings, not the full worker/image/execution chain. No redundant deployment was requested.

The protected Assessment Worker job already has a155-minute outer bound. Preserve the9,000-second runtime-capable durable contract,300-second renewable lease, one-attempt policy and inner limits; do not reintroduce the obsolete45-minute timeout. Combined corrected sufficiency remains to be qualified.

Railway read-only tools expose platform/configuration/log data, not NICO run records, canonical report inputs, diagnostic PDFs or artifact metadata. No database read or credential extraction occurred; target-run persistence/current state is UNPROVEN. HTTP200 /continue traffic for different run `comprun_702dd65cbc9013a81c1819ef68044f8b` proves traffic only, not source/stage/completion. No historical83% note is transferred to either run.

A read-only browser attempt requesting zero-data-retention handling was rejected because Firecrawl ZDR is not enabled for its team. No authenticated session/protected report input was obtained. Do not remove authentication, request secrets in chat, or assume a phone sign-in transfers a session to this tool. This is a scoped actual-input access boundary, not a universal block on permitted source work.

## Review accumulator

PDF-CONSERVATION-1: locally repaired and source-published; actual-input qualification still open.
NATIVE-CAPACITY-1: corrected candidate exists in PR1644; active native qualification unproven. Preserve both prior failures and the current run.
SECURITY-DEPLOYMENT-ID-1: exact nonsecret evidence established; narrow disposition/test/replay remains with the existing corrective process.
ACTUAL-PDF-REPLAY-1: blocked on legitimate authenticated run/input access.

PDF-SCOPED-REVIEW-1: a separate read-only Railway agent inspected exact base/candidate source. Its proposed persistent-discard change was tested in an isolated process:2failed/20passed, losing required Location content in both locales. The suggestion was rejected and withdrawn without changing candidate source. The reviewer retained NOT READY FOR MERGE because actual-input verification is missing. Inconsistent reviewer prose/counts are not accepted as evidence. This is limited source review, not independent execution or complete-capability approval.

INDEPENDENT-REVIEW-1: complete capability/final-corrections review remains open. Preserve prior allowance exhaustion and historic findings. No exhausted unchanged request, new credits, author-review substitution or review waiver was used.

## C0–C19 whole-row disposition

Retained baseline PASS rows keep their original frozen-native meaning; they do not assert production exercise, which is C18. Renderer-only edits do not invalidate unchanged native subproofs. Current runtime qualification is in progress; its old failures are not relabeled as passes.

| Predicate | Status | Evidence / remaining scope |
| --- | --- | --- |
| C0 | UNPROVEN | Current refs/authority/target/budgets recovered; actual production run contract/access and final qualification remain. |
| C1 | PASS | Retained complete frozen native inventory/acquisition unchanged; normal-production exercise remains C18. |
| C2 | UNPROVEN | Prior isolation/cleanup evidence retained; complete corrected combined workload still needs proof. |
| C3 | UNPROVEN | Final dedicated production worker/run/configuration/release receipt chain absent. |
| C4 | UNPROVEN | Owner-liveness repairs retained; final real-transport long-job recovery/fencing acceptance remains. |
| C5 | UNPROVEN | Current complete475-context substantive static/fallback qualification not terminal. |
| C6 | PASS | Retained frozen baseline build/generated inputs and475 compiler contexts; not production acceptance. |
| C7 | UNPROVEN | Prior ASan failures and missing UBSan/fuzz retained; corrected native runtime job is still running. |
| C8 | UNPROVEN | Actual final native/canonical/register/cross-format reconciliation remains. |
| C9 | UNPROVEN | Complete final runtime/static/report populations, exclusions and hashes remain. |
| C10 | UNPROVEN | Actual final-run score/assurance projection not verified; scoring unchanged. |
| C11 | UNPROVEN | Prior combined workload exhausted scratch; reclamation candidate's aggregate resource proof pending. |
| C12 | UNPROVEN | Hosted owned prerequisite reports success; corrected full production language controls remain. |
| C13 | UNPROVEN | Actual Bitcoin structured output/rendered PDFs and actual-input PDF repair verification unavailable. |
| C14 | UNPROVEN | Synthetic bilingual boundary tests pass; actual locale/mobile/progress/recovery/physical-device proof remains. |
| C15 | UNPROVEN | No human/history boundary changed; eligible exact-edition one-action proof remains. |
| C16 | FAIL | Existing exact-candidate security gate blocked; final checks and complete independent review not complete. |
| C17 | UNPROVEN | Main frontend/backend mappings verified; final corrected worker/image/release chain incomplete. |
| C18 | UNPROVEN | Qualified authorized normal-production frozen Bitcoin execution not verified. |
| C19 | UNPROVEN | Evidence indexed; actual bilingual artifact links/hashes, repeated retrieval and closeout absent. |

## EXACT NEXT ACTION

Use the existing PR1644/PR1645 pair, not replacement branches or a new native campaign. The runtime owner must resolve the exact security disposition under its current expected head, preserve run36138550814 and inspect terminal evidence when available. Qualify changed native inputs only where necessary; do not rerun unchanged native work for PDF or documentation revisions.

For PR1645, obtain the actual failed report inputs through a supported authenticated operation, replay exact base/candidate, inspect all mandatory rendered sections and finish applicable hosted/security/independent-review gates. Reconcile this single checkpoint with both latest heads before integration. No blind merge of the shared ledger hunk. Then finish qualified image/release binding, ordinary production control and frozen Bitcoin execution, bilingual repeated retrieval and genuine human approval boundaries.

No actual Bitcoin EN/es-MX artifact link/hash or final approval state has been verified here. This continuation did not start/alter a production assessment, import a receipt, enable qualification, change production settings, deploy, merge, approve a report or authorize delivery. Never declare SHIPPED from this checkpoint.
