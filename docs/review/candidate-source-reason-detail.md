# Evidence-bound candidate source availability detail

Base: a8cf452a844ad6d1fc44f9acbe6e3868f6769a88. Separate from the published report/preparation integration 029c83a56232f3b39192698d543a5a0427e6b989.

## Behavior and compatibility

The existing `source_parse_unavailable` reason covers both missing captured observations and observations reporting unavailable parsing. It remains unchanged for compatibility. An additive versioned `source_availability_detail` records only supported distinctions: absent path (cause unknown), malformed collection, unusable candidate path, reported parse unavailability, reported size limit, reported invalid binding, conflicting observation binding, unknown observation status, or legacy detail not recorded.

Detail requires a valid five-field capture scope and the existing candidate identity checks. A foreign candidate repository cannot support detail. Supplied observation binding must match repository, commit and path. A missing observation never establishes a budget cause or parser failure. Recorded parse-unavailable status covers several parser exceptions and does not establish a specific syntax defect.

Display counts are rederived from fingerprint-validated packets; arbitrary retained count claims and status/error text are not rendered. New bilingual disclosures are in the existing reviewer UI and PDF client-summary/workload output. Markdown/HTML prose is unchanged; canonical exports retain the additive diagnostics. Existing reports are not rewritten and cannot acquire missing historical detail. No scores, raw candidates, dispositions, collection budgets, model calls or approval/delivery controls change.

## Qualification

Tests cover supported/unknown statuses, absent/malformed capture, foreign scope/repository/commit, stale fingerprints, forged aggregate counts, final enrichment, bilingual UI and installed final EN/ES PDFs. Installed tests run in owned subprocesses and validate exact artifact hashes, input nonmutation and human gates.

A synthetic 1,681-candidate fixture retains 899 completed analyses and 782 unresolved. Its 593 deliberately absent paths demonstrate classification only; its remaining 189 are synthetic unsupported cases, not a reconstruction of production causes. Production's 593 old parse-unavailable outcomes remain unclassified by this repair until supported fresh detail exists. No production assessment or historical rewrite was performed.

Local diagnostic projection timing: a synthetic 27,306,384-byte register, three unprofiled calls, 0.1607 / 0.1471 / 0.1504 seconds. This includes existing packet/register fingerprint validation. It is not full-report timing or a production speedup claim.

## Existing shared-process localization failures

The earlier integration's single-process aggregate produced 237 passes and three failures:

- `tests/test_spanish_canonical_report_parity_v87.py::test_spanish_not_applicable_scanner_evidence_is_fully_localized`
- `tests/test_spanish_canonical_report_parity_v87.py::test_spanish_scanner_limitations_localize_the_production_truth_contract`
- `tests/test_spanish_canonical_report_parity_v87.py::test_spanish_localizes_reachable_unavailable_evidence_contracts`

All three reproduced on unchanged a8cf452a after importing `nico.phase17_canonical_artifact_rebuild_v1`, installing `install_comprehensive_spanish_canonical_evidence_literals_v95()`, then calling those tests in the same interpreter. The installed v95 global translator protects colon-prefixed evidence literals; these direct-helper tests expect pre-installation translation. The parity file alone passed all 12 tests. Existing NICO CI runs each test file in a fresh pytest process; the integration's equivalent per-file run passed all 240 tests. This is an unresolved baseline shared-process state-isolation issue, not a new integration failure or an assertion waiver. This branch does not alter the translator or those tests.

## Next bounded opportunity and limits

Before trying to increase analysis coverage, compare candidate paths against the retained exact-scope observation inventory and aggregate capture accounting. Absent path alone cannot distinguish capped inventory, input/output/deadline exclusion, unsupported file, or missing file. Current capture accounting is aggregate, so individual budget attribution cannot be reconstructed honestly. A future bounded collector change could retain closed per-candidate/path outcome codes within the existing aggregate output limit, charging their bytes and handling exhaustion explicitly; it requires separate budget/equivalence qualification. Do not raise budgets or clear candidates to improve counts.

A separately reproducible repair opportunity is test-process localization state isolation described above, not evidence that production localization should bypass literal preservation. Preserve those security/evidence guards and test both installed and direct-helper contracts if addressed later.

Hosted Python 3.11 CI/security and production behavior remain unverified for this branch. Local validation uses Python 3.12 and installed Node/TypeScript dependencies. No PR creation, merge or deployment is included.

Final local verification:

- `python -m pytest -q tests/test_candidate_source_reason_detail.py tests/test_candidate_investigation_pipeline_v1.py tests/test_candidate_investigation_finalization_v1.py tests/test_candidate_source_observations_v1.py`: 120 passed before adding one further real-collector test; that added test passed separately with `-k real_capture` (1 passed). No production code changed between these runs.
- `python -m pytest -q tests/test_candidate_workspace_capture_v1.py tests/test_candidate_export_truth_v1.py tests/test_report_scope_and_summary_truth.py`: 110 passed, four existing pypdf deprecation warnings.
- `node --test tests/js/candidate-review-assistance.test.cjs`: 36 passed.
- `apps/web/node_modules/.bin/tsc --noEmit` from the web project: exit 0.
- Independent read-only review: foreign-repository attribution issue corrected and tested; final review found no remaining blocker for the stated PDF/UI/canonical scope.

## Follow-up: observed per-path capture outcomes

`candidate_workspace_capture_v1` now records `nico.candidate-path-capture-outcomes.v1` inside the existing exact-scope capture envelope. `path_sha256_reasons` keys are SHA-256 of the normalized UTF-8 candidate path, not source contents. Values are closed codes for a boundary actually visited: missing/unsupported regular-file inventory entry, invalid inventory size, per-file or aggregate input limit, blob integrity failure, retained-output limit, observed deadline, or an unspecified capture-operation failure. No raw errors, paths or source are added. The existing investigator maps a candidate to its path digest only after scope/identity checks, and only when its observation is absent.

This is path-level evidence shared by candidates at that exact path, not an assertion that every candidate was individually analyzed. It does not record successful paths redundantly. It does not infer reasons for paths outside a capped candidate inventory, paths never visited after a timeout, an inventory operation that failed globally, or entries omitted after metadata exhaustion. Legacy/malformed/foreign evidence remains unknown. `recording_truncated` describes only the metadata cap, not inventory completeness.

Outcome serialization is capped at 16,384 UTF-8 bytes **within the existing 32,768-byte envelope reservation**, with unchanged 2 MiB total output, 8 MiB input, 256 KiB file and five-second cooperative deadline limits. Diagnostic work uses the same invocation and elapsed deadline. Whole-envelope overflow removes individual outcomes rather than retaining invalid allocation attribution. No additional source fetch, capture pass or source execution occurs.

Fixed synthetic comparison (1,681 candidates, 899 small valid Python files, 593 missing paths, 189 unsupported synthetic records): old/new order O,N,N,O,O,N. Capture seconds: O .02028, N .02363, N .02462, O .02162, O .02175, N .02543. Both made exactly 899 reads and charged 15,283 source bytes; observations, aggregate reasons, populations and capture completeness fields were equal. Output increased from approximately 341,526 to 357,582 bytes, including 16,028 bytes of outcome metadata. Final validated projection remains 899 completed / 782 unresolved. It explains 153 synthetic missing paths and leaves the other 440 unknown because metadata is capped. This is measured diagnostic overhead, not a speedup or a production-cause reconstruction.

### Test-local localization isolation correction

The three direct-helper tests named above now execute their **unchanged original assertions** in owned, timeout-bounded interpreters through a test-only decorator. No translator is removed/rebound and no production module changes for this purpose. After explicitly installing the previously contaminating v95 global guard, the entire parity file passes 12 tests. Installed PDF language/evidence tests remain separate acceptance coverage. Thus the documented shared-process failure is corrected by test isolation rather than weakening literal preservation or redefining real locale behavior.

### Remaining blocker

No retained production per-path outcomes exist for the old 593 cases. This code cannot retroactively supply them. Even future runs can exhaust diagnostic metadata; those candidates remain unknown. A real source-coverage repair requires observed per-path causes and exact source evidence; none is established merely by this diagnostic change. Hosted qualification and any deployment remain separate. Published integration head 029c83a is untouched.

Follow-up qualification: the combined nine-file Python suite passed 262 tests (four existing pypdf warnings), including the formerly order-sensitive parity tests in the same process. After the final malformed-Unicode path guard, the capture/detail suite passed 50 tests; final outcome-only recheck passed 20 tests. These counts overlap and are not summed. The JavaScript reviewer suite passed 38 tests; TypeScript exited 0. An explicitly v95-preinstalled parity run also passed all 12 tests. Independent read-only review found no remaining blocker, including the final invalid UTF-8 / null-digest rejection. No assertion was disabled. The original three assertion bodies are unchanged.
