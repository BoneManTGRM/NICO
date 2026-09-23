# Current continuation — Bitcoin baseline build and all CTest entries verified

Continue PR #1641 on `feat/cpp-full-project-capacity`. Existing main/base is `faaa10b037eb58e4175561b96dadf0d929764df4`. The verified execution candidate is `a10e61a9f5b4871e0199be43a481ff576c963c71`; CI checked merge snapshot `814f582a94fdb9231b857bef8d38693066ee2be6`, tree `05b9b9b5ce8e69a54be7cb3ccfe5bc17c88512d9`. The containing documentation commit is recorded in the PR, not self-referenced here.

**BASELINE_EXECUTED is verified. The full C/C++ capability and production Bitcoin Comprehensive report are not complete.** No replacement PR, force push, gate bypass, production activation, automated human approval, or historical alteration is authorized by this result. The existing C0-C19 contract still governs.

## Actual retained Bitcoin result — 23 September 2026

Run `35905634809`, baseline job `107336456235`: terminal SUCCESS, including native execution, evidence upload and cleanup. Artifact `10771494731` is 960,249 bytes, ZIP SHA-256 `ec770a5ed0688e3bff35b50563e1c53ad1ebcb599aa42a0cf69e5cb96e11d816`. The artifact was downloaded and verified; its receipt reports BASELINE_EXECUTED, not production qualification.

- Exact target: `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`.
- Complete inventory: 3,248 entries; 3,031 materialized blobs; 49,729,651 source bytes. Source-transfer membership and population hash match the frozen receipt.
- Configuration: Linux Debug, wallet/tests/IPC ON; GUI/benchmarks/ZeroMQ OFF, as previously frozen. The default build was not reduced to selected targets.
- Compilation database: 475 commands, 445 distinct original files, 29 distinct generated files. One original has two contexts. Database SHA-256 `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`; byte-identical before and after the build. Cache SHA-256 `c2e2a1d2526635514d1125e7d55b462f64ae83684492d533e6d26b538a94c67f`.
- Tests: 377 discovered, 377 executed, 377 passed, zero skipped/failure/error entries. Post-build discovery contains no DISCOVERY_FAILURE placeholders. Actual JUnit was reparsed and matched every discovered name and projected result. JUnit SHA-256 `f28e4c22a89d0782a07cded406461fe24fc2c4f591a546d60a7f499bb78e456a`.
- Build: 834,085 ms, exit 0. Tests: 284,114 ms, exit 0. Total isolated execution: 1,133,673 ms. Peak cgroup memory: 8,652,201,984 bytes.
- Actual boundary and cleanup verified: 4 CPU, 12 GiB RAM, no swap, 256 PIDs, 9 GiB tmpfs. Build limit 1,200 seconds; suite 720 seconds; each case 180 seconds; executor 1,800 seconds plus ten cleanup seconds. Sufficiency is proved for this baseline, not for additional analysis/sanitizer workloads.
- Tool-image configuration: `sha256:5992ed31e8055deca6d85c1bfb2376ae9c9fd6838717bcc1bdd4dcc908257462`. Receipt SHA-256 `437cdd95588ffbbdd0f312afa6a7de49581050fd29362edd1e71caffe5456883`. All 21 retained operation-output hashes, exits, truncation/timeout flags, source and contract hashes, and image identity were checked.
- Pinned external unit-test data remains outside source, checksum `cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095`. No live peers, real wallets/funds, or external target services were used.

## Scheduling repair and verification retained

The parent run `35901039112` cancelled `owned-project-integration` under its five-minute allowance and skipped the baseline. The three-file correction at a10e61a9 changed only that job's outer allowance to ten minutes and its two scheduling assertions. All other limits, isolation, dependency ordering and required work remained unchanged. The corrected job `107334230703` succeeded in 301 seconds, from 18:59:14Z to 19:04:15Z, directly demonstrating the scheduling repair.

Hosted contract job `107333098765`: 632 passed, 37 warnings, 84.50 seconds. The 26 focused baseline/scheduling tests also passed locally in 2.50 seconds after initializing the exact downloaded source as a local Git fixture. The initial local no-.git attempt produced two fixture-environment failures and 24 passes; no assertion was relaxed. The local fixture commit is not an upstream release and was not pushed. Prior RED/GREEN evidence and the earlier incomplete local broad-suite run remain in PR comment `5801001427`; do not add overlapping counts.

Source artifact `10770433556`, ZIP SHA-256 `37c6ce58038c617ec7130fa8b2632b2efeea39c0410bc1b5e884316d46741fa2`: inner archive checksum and all 2,437 regular source-file bytes were verified. Control artifact `10770724666`, SHA-256 `f33ebbe09e781e673e09a52aec136f0601bc1bad6d3137d6a127fae6f8bb19fd`, retains positive/negative owned controls, persistence and bilingual control-report evidence. Controls do not substitute for a production Bitcoin report.

This transition changes documentation only. It does not invalidate the unchanged baseline source/tool/target/configuration fingerprints or authorize another expensive baseline run. No new Bitcoin execution was started during this evidence-verification continuation.

## Earliest remaining implementation gap

The current `nico.assessment_cpp_full_project._database` parser only accepts original `/work/source/` units and compares that population to the configured original list. A data-only call with the actual captured database, its 445 original units and `nested=True` reproduces `worker_full_project_database_path_invalid` at generated `/work/build/` entries. No production parser change was made in this continuation.

The remaining adapter must preserve all original/generated and multiple-context entries, bind generated bytes and header dependencies immutably, and carry real configuration-aware analysis through native receipts and coverage. Do not filter away generated files, collapse contexts, weaken command/path validation, or promote configuration capture to analyzed coverage.

## Review and release boundaries

Independent complete review of `faaa10b037eb58e4175561b96dadf0d929764df4...a10e61a9f5b4871e0199be43a481ff576c963c71` was requested in PR comment `5802036311`. The actual bot reply `5802038248` at 20:03:01Z says the Codex code-review usage limit is reached. No independent review occurred. Do not retry unchanged requests, buy credits, change accounts, or waive review. This affects the review gate, not the already verified build and not independently permitted implementation.

No merge or deployment was performed. Last platform observations remain Vercel preview `dpl_6r9EEqL2dACUd1WMy11E1fqDAJis` READY at a10e61a9 and Railway production deployment `c6d476c4-e692-4030-9e6b-831df24231ff` SUCCESS at main faaa10b0; those are not a shipped full-project worker. Unrelated Railway staged changes remain untouched.

C6 has a supported-baseline build subproof, C7 has a complete native CTest subproof, and C11 has a measured baseline-resource subproof. No whole C0-C19 predicate is promoted solely from this result. Actual static/header analysis, declared functional/sanitizer/fuzz scope, production worker/profile and report integration, independent review, exact release deployment and the actual bilingual production report remain required. Historical authorization, specialist/operator approval, client-delivery and artifact-integrity controls remain unchanged.

## EXACT NEXT ACTION

Continue the existing original/generated/multiple-context compiler-evidence integration on this branch with a small owned reproduction and bounded, versioned compatibility tests. Qualify real configuration-aware static/header execution before promoting coverage. Then complete the declared functional/sanitizer/fuzz scope, durable production integration, independent full-range review, final required checks, gated merge/deployment and authorized bilingual production Bitcoin report/retrieval. Reuse the verified baseline where its inputs remain unchanged; do not restart it to replace missing analysis evidence. Genuine human approval must remain human. Do not declare SHIPPED until all required C0-C19 evidence exists.

## Immutable predecessor and historical failures

The complete predecessor is preserved at `a10e61a9f5b4871e0199be43a481ff576c963c71:NICO-Ship-Checkpoint.md`, blob `091699d61ad0eceeeb1670766730d3ce6db80999`, SHA-256 `1647f1fb859917e2defee1a2b7b331ea5cefca711cedf4cb7cd2bc7346b55d25`, 8,878 bytes. It retains the earlier failed/partial baseline run `35893519801`, the successful configuration evidence, budget corrections and complete earlier checkpoint reference at `1ebc4d77293296125faa80a5977392de2eaa56d2`. That chain retains PR1627, original C0-C19 definitions, accepted/failed evidence, worker/database/production and approval history. Earlier missing-Capnp, timeout, skip and truncation outcomes remain historical failures; the successful new run does not rewrite them. This file remains the only active mission ledger.
