# Exact originals for export-substituted GitHub archives

## Production failure

Bitcoin assessment `comprun_2fcefb8f5e1d651144751690e8d6911d` reached the dedicated
worker on September 28, 2026. Workflow `36440525935`, job `108989507931`, passed
signed identity preflight and claimed its job, then failed acquisition with
`worker_source_archive_type_or_size_invalid`. No native execution completed.

At Bitcoin commit `05bc2f53ce0cb239c17dbdd6b261bd2db7d2a940`, root
`.gitattributes` marks two paths `export-subst`. GitHub's commit archive changes
`src/CMakeLists.txt` from 10,473 to 10,463 bytes and `src/clientversion.cpp` from
2,350 to 2,378 bytes. Rejecting these as exact original blobs was correct.

## Repair and boundaries

Before archive acquisition, verify committed `.gitattributes` files against the
pinned Git tree and plan separate exact-blob acquisition for literal relative
`export-subst` paths. Verify those originals against their Git blob IDs; selected
originals also retain the frozen SHA256 check or establish it before configuration.
The transformed archive bytes are consumed within the expansion budget but never
used as source. Record the original paths and actual network request count.

This is not fallback after arbitrary archive failure. All other members retain
their existing digest/size checks. Archive path, duplicate, special-file, symlink,
population, truncation, deadline and expansion checks remain enforced. Attribute
reads are bounded to 64 files of at most 64 KiB; originals to 32 files within
existing source/per-file budgets. No credentials or target code are used.

Only literal relative attribute paths are supported by this addition. Globs,
quoted patterns, macros and traversal grant no archive verification exception.
Repositories requiring additional Git attribute semantics remain unsupported when
their archive differs from committed bytes.

## Verification

- Regression fixture reproduced the previous type/size failure.
- 189 focused archive, consumer, launcher, receipt, configure-first and production
  selection tests passed (one existing Starlette deprecation warning).
- Real pinned Bitcoin acquisition: 3,042/3,042 regular files, 50,284,616 original
  source bytes, tree `7fa6a1a4dfa6ef3828b76e0cde17dffcb3c26504`.
- Seven public requests: commit, tree, two attribute files, two original blobs,
  and archive. Archive SHA256
  `05fa4b85486cf3fa7dcc6fbf84d870cc1f758dfd5db215899253420dc7ab0d18`,
  15,277,084 compressed / 52,746,240 expanded bytes.
- The real-source check used a bounded urllib transport through the workspace's
  network proxy. The production downloader disables environment proxies and could
  not connect locally. Thus this proves acquisition/materialization against real
  bytes, not production worker execution or its isolated download transport.

Production acceptance remains pending CI, merge, release qualification/alignment,
deployment and an authorized actual assessment. Preserve the failed run unchanged.
