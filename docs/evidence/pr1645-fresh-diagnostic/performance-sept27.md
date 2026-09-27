# Hosted deadline failure and measured performance repair

Run 36309099855 on published PDF head 52e1bd219bd200fea03f16f4881f12937cbae36b
failed at 2026-09-27 11:35:35 UTC. Both languages exhausted both existing bounded
attempts. Each final record retains `final_report_publication_deadline_exceeded`,
the process-local 900.003-second expiry, and confirmed physical worker exit.
Neither language produced a result capsule or a final PDF. The earlier successful
local English/Spanish replays remain local evidence; they did not prove this
hosted run would finish.

Original artifact 10930802779 has 35 ZIP members and 34,261,380 bytes. Its SHA256 is
`deb8d725f11a4be750732ee7f76d8cd565d4f1f31bfaa0eb0c08174d2f22f62e`.
All members, four exact input hashes, and sixteen compressed/raw scanner output
hashes were checked. Producer 46fd4e5c3a22cb7937a2b6f32a04f4782cc92128 has
main312693 and PDF52e1 parents and tree3e91a2bb0b9686a8aedef116d203d750707ef193.
The original archive is retained unchanged. These checks confirm failed evidence,
not report acceptance.

## Established redundant work

The diagnostic called `service.resume()` every two seconds while the isolated
renderer ran. Resume loaded the full record, and coordinator advance loaded it
again. On the actual 134,213,754-byte retained English record, each lossless decode
plus full record restoration/validation consumed 3.622/3.557 seconds wall time and
3.620/3.553 CPU seconds. That is approximately 7.1 CPU seconds per poll before
database transport. This is avoidable contention; its precise contribution to the
hosted deadline has not been established. Small lease heartbeat/watchdog reads
were not the heavy path.

The diagnostic now reads only canonical row metadata and the exact publication
lease in one query on its dedicated local database. It reuses the previous
integrity-validated record solely for progress while identity, revision, integrity,
status and terminal state remain identical and the lease is fresh, within its
existing deadline, and owned by a live local worker. Any change, expiry, missing
state, stopped worker or read error immediately takes the original bounded resume
path. Final acceptance still requires a refreshed full canonical result, retained
successful renderer capture, and all PDF/input/result bindings. There is no global
run cache, production database query, alternate acceptance or changed polling delay.

A bounded profile of the newly retained English input also measured repeated
standard deep copies and millions of generic Mapping checks in report projection.
Seven measured modules now opt into the already tested exact-JSON copy helper;
unsupported Python types still use standard deepcopy. Decision restoration uses
the equivalent collections.abc Mapping check directly. Four actual retained
canonical transformation comparisons produced identical output SHA256 values and
left input unchanged; this is an optimization, not a skipped projection.

The legacy risk/hotspot regular expressions are unchanged. Candidate-start scanning
avoids retrying impossible suffixes of failed path runs, preserving original match
objects, spans, groups, occurrence order and duplicates. The actual earlier input
scan improved from 14.194 to 4.997 seconds with the same sixteen records, SHA256
`69343bc34fd7f21e56b12977e030a1f7889b973f7f12a6e967c03e5ed5619f75`.
All 16,002 unique earlier-input strings had original match/group-span parity.

PDF bookmark selection reuses extracted text only for unchanged pages reached by
the original search. First matching page, TOC exclusion, fallback and final PDF
validation remain unchanged. A retained PDF produced byte-identical output before
and after the change, SHA256
`f46f34c539213ca19f01bd1d989dd8395d6a23def7ca35220161be7fef337e68`.

## Acceptance status

Independent focused review found no material defect and passed 109 affected tests
after the final polling-loop extraction. The combined C++43aa/report candidate
tree e2f3901b61c1d9516a744fe357c01b02d843f9b0 passed 440 distinct Python checks
in 43.96 seconds, with zero failures, errors or skips. Subsequent edits to this
evidence note do not change that tested source. Both complete historical ledgers
remain present and the combined merge tree is clean.
New monitoring regressions cover canonical revision/identity/integrity/state changes,
lease expiry and failure, missing state, stopped workers, database errors and final
canonical refresh. Actual PostgreSQL integration remains a hosted requirement.
The 900-second renderer deadline, 60-page cap, resources, evidence populations,
source-table exports, approval/delivery gates and production hold remain unchanged.

The new isolated-worker replay and subsequent hosted English/es-MX assessment must
finish and be checked before report acceptance. No native C++ rerun is required;
its completed-collection acceptance and unresolved UBSan finding remain unchanged.
Neither PR is declared ready or merged by these performance measurements.
