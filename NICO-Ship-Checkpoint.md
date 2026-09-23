# Current continuation — frozen whole-project baseline execution

Continue PR #1641 on `feat/cpp-full-project-capacity`. Publication parent `1ebc4d77293296125faa80a5977392de2eaa56d2`, tree `ddd04f61f7db840f2bc0157f294110f6b56d93eb`; observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. No replacement PR, force push, production activation or automatic human approval.

## Actual Bitcoin configuration now succeeds

Run `35888870184`, native job `107276978245`, artifact `10764685006` completed the pinned dependency image, owned controls and exact Bitcoin configuration. Downloaded ZIP 1,365,740 bytes; SHA-256 `c9cd97e57c0352eb9a46eb31d507176abf720db778a67d61438af4a1b7640a5c` verified. Target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`.

Configure exit 0 in 12,239 ms, total 14,566 ms, cgroup memory peak 237,072,384 bytes; boundary and cleanup verified. Result CONFIGURATION_CAPTURED is not a project build, tests, static/sanitizer/fuzz analysis or production qualification. The previous missing-Capnp run stays failed. Capnp source 1,869,727 bytes matches 1.5.0 and its frozen upstream hash.

The captured database has 475 commands, 445 distinct original and 29 distinct generated files. One original has two compilation contexts. Preserve all commands and generated sources. Database SHA-256 `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`; cache `c2e2a1d2526635514d1125e7d55b462f64ae83684492d533e6d26b538a94c67f`; image config `sha256:67fdc11f44c2639d628810ec46548c810bc2d2a8721f7b523d145275a1f99aa2`. Wallet, tests and IPC ON. GUI/benchmarks/ZeroMQ exclusions unchanged.

## BASELINE-EXECUTION-1

Extend the existing configure-first executor with an explicit baseline execution contract. Default configuration-only behavior and all older worker profiles remain unchanged. The optional v2 preparation result cannot pass normal production receipt validation or select a production profile. Do not call it full qualification.

Before building, require the exact captured database hash and freeze the entire discovered CTest name population. Run the full default CMake build without selecting a reduced target set; require unchanged database bytes afterward. Execute every discovered test without regex exclusions. Retain native exits, outputs, JUnit and exact executed/passed/skipped populations. Any failure, skip, truncation, mismatch, interruption or unverified cleanup stays UNPROVEN, preserving completed prior stages. BASELINE_EXECUTED means this bounded build/CTest pass only, not static-analysis or sanitizer/production acceptance.

The measured 475-command Debug scope motivates a separately named initial capacity trial, not a claim of measured sufficient capacity: four CPU, 12 GiB cgroup RAM, no swap, 256 PIDs and 9 GiB tmpfs scratch. Scratch is charged to cgroup memory; real runtime cgroup/scratch boundaries must agree. Old 256 MiB and 2 GiB profiles and all original four CI jobs remain unchanged. The exact input contract bounds build at 1,200 seconds, tests at 480 seconds/60 per case, and execution at 1,800 seconds plus ten cleanup seconds. One sequential standard Ubuntu public-repository job, 40-minute outer deadline, no services/production credentials, contents:read only, no registry mutation. Existing per-branch workflow concurrency serializes the campaign. New source/tool/benchmark mutations invalidate dependent native proof.

The owner's execution contract sections 1/5/7 authorize necessary bounded capacity work and prohibit preserving an unsuitable older report-repair limit. GitHub's official standard-runner reference (https://docs.github.com/en/actions/reference/runners/github-hosted-runners) states public ubuntu-24.04 uses four CPU/16 GiB and standard execution is free. No paid runner or cloud entitlement was enabled. The new job builds the unchanged pinned image in its own fresh VM because no unqualified registry or large image-storage handoff is introduced. These are initial enforced budgets; sufficiency requires the actual result, not this plan.

## Verification and continuation

Missing baseline behavior RED: 16 cases. Missing measured scratch binding RED: one case. Fresh focused combined suites: 190 passed in 5.91 seconds. AST, every workflow shell block and diff checks pass. The full hosted predecessor retains every original test/exporter and adds baseline tests. No new native baseline build is claimed by local tests. Earlier full local timed-out invocations remain unproved; do not add overlapping counts.

Publish this source increment non-force only after rechecking head and blob identities. Inspect the new automatic serial baseline job and preserve its first real failure. Do not raise limits or drop required components merely to get green. After successful build/CTest, finish actual configuration-aware static/header evidence for original/generated/multiple-context populations, scoped functional integration, supported sanitizer/fuzz, durable production worker integration and report ingestion. Complete independent full-range review, final CI, gated merge, coordinated release deployment and the actual authorized bilingual Bitcoin report. C0-C19 still governs; no SHIPPED claim before all mandatory evidence exists. Human review/approval and genuine platform boundaries stay intact.

## Immutable historical chain

The complete previous checkpoint is preserved at `1ebc4d77293296125faa80a5977392de2eaa56d2:NICO-Ship-Checkpoint.md`, Git blob `73d79bcd350d6b57bee05c68af4120a906dedda4`, SHA-256 `cdb4da8ab7bc2c7a9833184851f46851ef557a691dc2b06cdda63d59e150fe64`, 4871 bytes. It retains the 99fe/d7/59/a40/b08/370/934/0b9/PR1627 evidence, failures, production/worker/database history, target identities, approval history and original C0-C19 definitions. There remains one active checkpoint.
