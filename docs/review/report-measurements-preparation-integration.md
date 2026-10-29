# Report measurement and preparation integration

Base: a8cf452a844ad6d1fc44f9acbe6e3868f6769a88 (verified remote main before integration).

Original reviewed changes, preserved on their branches:
- 4a867c7452085f38a204d3ac861c531814700006: bind retained measurement scope before display identity cleanup.
- cbcc48fc00f37cd49f90b1143f15fd40dcbfd304: avoid redundant scanner-normalization assessment copies when ownership is certified.
- 40076198e5e75ea86f059d73ffd7ce18208bcf25: reuse privately owned nested stage evidence during top-level narrative normalization.

All three cherry-picked without conflicts. Integration-only test changes use the supplied production run/repository/SHA and default customer/project identity in the installed EN/ES fixture, verify normalized historical reports remain unavailable both before and after cleanup, and compare complete artifacts with all three copy optimizations disabled together. Fixture measurements are synthetic production-shaped inputs, not a replay or modification of the historical report.

## Intended behavior and limits

Future producer reports retain their original five-field measurement scope before placeholder identity presentation. PDF/Markdown/HTML can then show genuinely bound values even when displayed customer/project identities say Not supplied. Scope schema, all five identity fields, metric provenance and measurement validation remain enforced. Existing normalized reports that lack the preserved scope cannot recover authority from their measurement envelopes and remain unavailable. Numeric architecture/velocity scoring is unchanged.

Performance changes only reuse already isolated private trees; aliased/opaque inputs keep legacy copying. Root and assessment stage mirrors remain independently mutable. No transformation or integrity check is skipped. The documented local component improvements are not a combined or production latency guarantee and do not resolve the entire slow first Spanish export.

No database migration or backfill. Rollback is a normal source revert/redeployment through existing reviewed release procedures; no retained report mutation is needed. No deployment is performed by this integration work.

## Qualification

Use the per-file process isolation in `.github/workflows/nico-ci.yml`, retaining every selected test. The qualification command is recorded below. It covers installed EN/ES measurement values and hashes, full artifact equivalence, identity conflicts, malformed context, historical non-inference, source nonmutation, alias isolation, unchanged candidate rejection, approval/delivery gates and candidate freshness. Independent full-range review found no blocker. Hosted exact-head CI/security and production release qualification are still required; local Python 3.12 results do not establish hosted Python 3.11 success.

The initial aggregate run found three direct-translator tests affected by globally installed v95 literal protection. The same three failures reproduced on unchanged base a8cf452a when that installer was active; the parity file alone passed 12 tests. The new installed-render and installed rejection tests now run in bounded owned worker processes, preserving all assertions and avoiding installer leakage. Production localization was not changed, and this does not claim to resolve the preexisting difference between direct and installed translation behavior. The targeted isolation sequence passed all 42 tests. The full shared-process rerun still returned 237 passed / 3 baseline translator-state failures because existing render tests also install global guards. This run is not reported as green. Final local qualification therefore follows NICO CI's explicit per-file subprocess model; independent review confirmed this does not waive or remove any test. The preexisting difference between direct and fully installed localization remains outside this patch.

CI-model qualification command (one fresh pytest process per file):

```sh
for test_file in \
  tests/test_retained_section_measurements.py \
  tests/test_scanner_truth_owned_copy.py \
  tests/test_stage_truth_evidence_ownership.py \
  tests/test_scanner_applicability_v2.py \
  tests/test_comprehensive_authoritative_scanner_truth_v62.py \
  tests/test_owned_report_preparation_copy.py \
  tests/test_report_json_copy.py \
  tests/test_comprehensive_report_language_truth_v77.py \
  tests/test_comprehensive_human_review_package_cleanup_v1.py \
  tests/test_comprehensive_client_identity_publication_guard_v2.py \
  tests/test_comprehensive_human_review_package_cleanup_compat_v1.py \
  tests/test_v2_premium_report_renderer.py \
  tests/test_spanish_canonical_report_parity_v87.py \
  tests/test_candidate_investigation_finalization_v1.py
do
  python -m pytest -q "$test_file" || exit 1
done
```

Final local CI-model qualification: all 14 files exited zero; **240 tests passed, zero failures, zero errors, zero skips** on Python 3.12. Per-file JUnit and logs were retained locally. This does not change the separately disclosed shared-process result or establish hosted CI success. All six production source files exactly match their corresponding reviewed source commits.
