# Current continuation — post-build test population and retained CTest evidence

Continue PR #1641 on `feat/cpp-full-project-capacity`. No replacement PR, force push, production activation or automatic human approval.

## Measured baseline, run 35893519801 job 107294832419

Build succeeded in about 836 seconds, peak cgroup memory 8,643,104,768 bytes, boundary and cleanup verified. Qualification stayed UNPROVEN. Pre-build `ctest --show-only` froze 161 names, including `noverify_tests_DISCOVERY_FAILURE` and `tests_DISCOVERY_FAILURE`. Those are secp256k1 `discover_tests` placeholders: the include runs the test binary at ctest time, so the runnable list does not exist until after the build. The test process itself reported 377 entries: 372 passed, `script_assets_tests` skipped, and `cluster_linearize_tests`, `coins_tests_dbbase`, `random_tests`, `coinselector_tests` each hit the 60-second case limit. The skip is `DIR_UNIT_TEST_DATA` unset; Bitcoin prints `skipping script_assets_test` and its own CTest rule treats that as a skip. The JSON is not in the pinned source. It is qa-assets blob `b33d85102d169b54d966ea315ad81a636680aefa` (`script_assets_test.json`, 9,243,520 bytes, SHA-256 `cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095`). The four timeouts were still inside Boost suites when CTest killed them. That is a Debug budget miss, not a demonstrated Bitcoin defect. Their `--output-on-failure` logs then crossed the 1 MiB controller stream limit. The runner killed CTest (exit 125, `output_truncated`) before `tests_executed` or the JUnit read, so the receipt said the tests had not run.

## Correction

Discover and freeze CTest names only after the build and the unchanged compile-commands check. Reject any `DISCOVERY_FAILURE` name instead of treating it as a test. Run the same full CTest command with stdout left on the work tmpfs, then retain a bounded log and the JUnit file even when CTest exits non-zero or the retained log is truncated. `tests_executed` is recorded as soon as that command returns. A truncated stream is no longer able to skip the JUnit. Case budget is 180 seconds and the suite budget is 720, still inside the 300/900 contract ceiling and the 1,800-second execution envelope. The pinned qa-assets file is staged at `/work/unit_test_data` outside the assessed source and exported only on the CTest process as `DIR_UNIT_TEST_DATA`. A skip, timeout, truncation, or non-zero CTest exit remains UNPROVEN. This does not claim BASELINE_EXECUTED, static/header evidence, sanitizers, fuzz, production integration, review, deployment, or the bilingual report. The next hosted job is the measurement.

## Previous continuation

Publication parent of the prior checkpoint text remains the historical chain below. The 475-command Debug configure evidence is unchanged: database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`, wallet/tests/IPC on, GUI/benchmarks/ZeroMQ off, target `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`.

## Prior plan retained for the measurement it recorded

## Actual Bitcoin configuration now succeeds

Run `35888870184`, native job `107276978245`, artifact `10764685006` completed the pinned dependency image, owned controls and exact Bitcoin configuration. Downloaded ZIP 1,365,740 bytes; SHA-256 `c9cd97e57c0352eb9a46eb31d507176abf720db778a67d61438af4a1b7640a5c` verified. Target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`.

Configure exit 0 in 12,239 ms, total 14,566 ms, cgroup memory peak 237,072,384 bytes; boundary and cleanup verified. Result CONFIGURATION_CAPTURED is not a project build, tests, static/sanitizer/fuzz analysis or production qualification. The previous missing-Capnp run stays failed. Capnp source 1,869,727 bytes matches 1.5.0 and its frozen upstream hash.

The captured database has 475 commands, 445 distinct original and 29 distinct generated files. One original has two compilation contexts. Preserve all commands and generated sources. Database SHA-256 `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`; cache `c2e2a1d2526635514d1125e7d55b462f64ae83684492d533e6d26b538a94c67f`; image config `sha256:67fdc11f44c2639d628810ec46548c810bc2d2a8721f7b523d145275a1f99aa2`. Wallet, tests and IPC ON. GUI/benchmarks/ZeroMQ exclusions unchanged.

## BASELINE-EXECUTION-1

Extend the existing configure-first executor with an explicit baseline execution contract. Default configuration-only behavior and all older worker profiles remain unchanged. The optional v2 preparation result cannot pass normal production receipt validation or select a production profile. Do not call it full qualification.

Before building, require the exact captured database hash. The initial plan also froze CTest names before the build and bounded tests at 480 seconds/60 per case. Run 35893519801 showed that freeze captured discovery placeholders and that 60 seconds killed four Debug suites; the current continuation above replaces those two rules. Run the full default CMake build without selecting a reduced target set; require unchanged database bytes afterward. Execute every discovered test without regex exclusions. Retain native exits, outputs, JUnit and exact executed/passed/skipped populations. Any failure, skip, truncation, mismatch, interruption or unverified cleanup stays UNPROVEN, preserving completed prior stages. BASELINE_EXECUTED means this bounded build/CTest pass only, not static-analysis or sanitizer/production acceptance.

The measured 475-command Debug scope motivates a separately named initial capacity trial, not a claim of measured sufficient capacity: four CPU, 12 GiB cgroup RAM, no swap, 256 PIDs and 9 GiB tmpfs scratch. Scratch is charged to cgroup memory; real runtime cgroup/scratch boundaries must agree. Old 256 MiB and 2 GiB profiles and all original four CI jobs remain unchanged. The exact input contract initially bounded build at 1,200 seconds, tests at 480 seconds/60 per case, and execution at 1,800 seconds plus ten cleanup seconds. The case and suite ceilings are now 300 and 900; the published contract uses 180 and 720. One sequential standard Ubuntu public-repository job, 40-minute outer deadline, no services/production credentials, contents:read only, no registry mutation. Existing per-branch workflow concurrency serializes the campaign. New source/tool/benchmark mutations invalidate dependent native proof.

The owner's execution contract sections 1/5/7 authorize necessary bounded capacity work and prohibit preserving an unsuitable older report-repair limit. GitHub's official standard-runner reference (https://docs.github.com/en/actions/reference/runners/github-hosted-runners) states public ubuntu-24.04 uses four CPU/16 GiB and standard execution is free. No paid runner or cloud entitlement was enabled. The new job builds the unchanged pinned image in its own fresh VM because no unqualified registry or large image-storage handoff is introduced. These are initial enforced budgets; sufficiency requires the actual result, not this plan.

## Verification and continuation

Missing baseline behavior RED: 16 cases. Missing measured scratch binding RED: one case. Fresh focused combined suites: 190 passed in 5.91 seconds. AST, every workflow shell block and diff checks pass. The full hosted predecessor retains every original test/exporter and adds baseline tests. No new native baseline build is claimed by local tests. Earlier full local timed-out invocations remain unproved; do not add overlapping counts.

Publish this source increment non-force only after rechecking head and blob identities. Inspect the new automatic serial baseline job and preserve its first real failure. Do not raise limits or drop required components merely to get green. After successful build/CTest, finish actual configuration-aware static/header evidence for original/generated/multiple-context populations, scoped functional integration, supported sanitizer/fuzz, durable production worker integration and report ingestion. Complete independent full-range review, final CI, gated merge, coordinated release deployment and the actual authorized bilingual Bitcoin report. C0-C19 still governs; no SHIPPED claim before all mandatory evidence exists. Human review/approval and genuine platform boundaries stay intact.

## Immutable historical chain

The complete previous checkpoint is preserved at `1ebc4d77293296125faa80a5977392de2eaa56d2:NICO-Ship-Checkpoint.md`, Git blob `73d79bcd350d6b57bee05c68af4120a906dedda4`, SHA-256 `cdb4da8ab7bc2c7a9833184851f46851ef557a691dc2b06cdda63d59e150fe64`, 4871 bytes. It retains the 99fe/d7/59/a40/b08/370/934/0b9/PR1627 evidence, failures, production/worker/database history, target identities, approval history and original C0-C19 definitions. There remains one active checkpoint.
