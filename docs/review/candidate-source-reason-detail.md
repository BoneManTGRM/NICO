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
