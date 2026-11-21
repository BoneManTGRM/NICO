# Local proposal: bounded pinned unit-test asset staging

## Observed failure

PR #1712 run 42037204449, job 127307108030, failed before assessment. The fixed qa-assets URL returned HTTP 504 on all four original curl attempts. This is transport evidence, not native qualification evidence. No live recovery has been demonstrated.

## Proposed change

Replace only the asset transfer command with `scripts.stage_cpp_unit_test_asset`, retaining the exact qa-assets revision b33d85102d169b54d966ea315ad81a636680aefa, URL, SHA256 cd789a58ec45916e1721cdd14e82ca4c93100959f1cef4e229b22e3bf539f095 and 9,243,520-byte size. Existing workflow hash and size checks remain after staging, and its existing test selection gains the new helper tests.

At most four attempts share a 90-second deadline. Each transfer is capped at 20 seconds plus one second subprocess grace, with a 5-second connect cap. Backoff is 2/4/8 seconds. Retry only timeouts or HTTP 408/429/500/502/503/504; do not retry TLS failures, authentication errors, missing files, hash/size failures or unsupported responses. Disable curl's default configuration so it cannot silently introduce extra URLs/retries. No alternate source or mirror is used.

Each attempt starts with a new private partial file. Accept only a regular no-follow file, read no more than the expected size plus one byte, verify exact size/hash, then write the verified bytes into a separate private file. Atomically link it to the final path without replacing existing files or links. Deadline checks precede publication. An outer 90-second timeout plus 1-second kill grace bounds a stalled filesystem operation as well. Normal failures clean private files; an externally terminated process may leave private temporary files, but cannot make them accepted evidence. The workflow stops on failure and retains its independent hash/size checks.

## Verification

Synthetic adversarial controls cover transient recovery/exhaustion, retry allowlist, malformed HTTP status, TLS/authentication failures, corrupt/oversized payloads, symlink/FIFO/directory/missing transfer files, existing destinations, aggregate time including subprocess grace/backoff, and sanitized nonzero CLI failures. A mutation-after-verification test exposed a publication race in the initial draft; publishing a separate verified-byte file repairs it. A real process timeout test stalls the filesystem seam and confirms no final asset is published.

Focused checks: 98 passed. Independent final review: 66 passed, no remaining blockers. Full existing workflow selection: 2,189 passed, 5 skipped, 43 warnings in 93.44 seconds. Warnings were dependency deprecations; the complete log is retained locally at `/tmp/cpp-asset-local-contracts.log`.

No actual network download, hosted rerun, publication, security-setting change, or frozen-source modification was performed. This proposal improves bounded staging but does not prove a persistent HTTP 504 will recover.

## Native qualification remains separate

Latest #1727 run 42037242796 collected 577 compiler contexts without timeouts. Context 289 remains a validated generated-source #error failure; it is not a harmless pass. Static completion remains 14/577 with 12 primary timeouts and 604 unvisited headers. UBSan still fails at the observed src/streams.cpp:99:24 location. Owned GCC O0/O2 controls reproduce the empty/null write mechanism and a guarded control, but do not establish the hosted cause. Neither this patch nor these controls qualify the native target.
