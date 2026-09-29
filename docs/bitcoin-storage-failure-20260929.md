# Bitcoin production failure, 2026-09-29

Run `comprun_f69892406e9792894da2f5df143a8fa8`, Bitcoin commit
`ced4c6e6ab472fe2a60ad5c379f76962b61b6f34`, remains blocked and unchanged.
Production release is `c28f497d77d79b3e4f696e503532b94567e93076`.

Read-only PostgreSQL inspection through the authenticated Railway Console found
two independent failures:

* Ordinary parent `scan_snapshot_cpp_2b48acb616ebdcac29b0979e7bec0eccb9d23275`
  has status failed, snapshot_match false, failure_type UntranslatableCharacter.
  Its retained Bandit and TruffleHog raw output includes escaped NUL characters.
  PostgreSQL JSONB cannot store decoded NUL strings. Existing scanner record
  persistence passes those strings unchanged. This is a storage defect, not a
  Bitcoin vulnerability or proof of successful ordinary scanner completion.
* C++ child `scan_worker_201eb69b483f6507914b228e372a1be55e8fd2d3` retained an
  incomplete receipt. Build/baseline tests are recorded true, but the generated
  snapshot failed at `src/test/data/sighash.json.h`: 32,230,555 bytes already
  captured, 1,323,877 bytes remaining, next regular single-link file 1,499,901
  bytes. Error `worker_generated_type_or_size_invalid`, initial_read phase.
  The aggregate cap remains 33,554,432 bytes. Later analysis was not completed.

Worker workflow 36562934494 succeeded in transport; scanner_status was failed.
Receipt SHA256:
`3d7066e4bd64987bba8ba711341534b49b111a2ad19f04662979586e0509b09b`.

## Focused change

After retaining and verifying original compressed scanner bytes, escape NUL and
lone surrogate codepoints in canonical display strings. Record the conversion
count and representation explicitly. Original raw bytes, compressed bytes,
hashes, findings count, statuses, identities and approval gates retain their
meaning. Normal Unicode and line breaks are preserved. Field names are never
renamed. Compute the canonical record hash after display conversion.

Regression failed before the change and passes afterwards. The 32 focused
storage/durability/proof tests pass locally. The existing native PostgreSQL CI
proof now includes these characters in both a display snippet and the retained
raw evidence, then verifies the record after reconnection. Local SQLite driver
tests are not a substitute for this native PostgreSQL gate.

## Remaining work

This patch does not solve the C++ aggregate capture limit, complete static/runtime
analysis, produce a report, or qualify a new production release. Inspect CI and
reviews before merge. Diagnose/report bounded unexecuted scope without raising
resource caps or granting completion credit. Do not retry the production run
unchanged or change its historical records.
