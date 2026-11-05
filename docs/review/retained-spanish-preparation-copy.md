# Retained report preparation: bounded copy reduction

Base: a8cf452a844ad6d1fc44f9acbe6e3868f6769a88. This does not include the separate retained-measurement display fix.

## Diagnosis and limits

Reported production timings for request 3e2d26f4bb1b4deab19df51c6a9fdc1c were 99.912 seconds installed completion (98.784 CPU) within 131.752 seconds artifact preparation (130.199 CPU). These are inclusive phases, not additive. They support a CPU-bound preparation bottleneck, not a network hang. This change does not establish the complete production cause or solve the first-download timeout.

A local cProfile of `_prepare_client_artifact_package` with 1,681 synthetic retained evidence rows (1,590,922 JSON bytes) took 14.209 seconds under profiling. Copy-tree traversal accounted for 5.380 cumulative seconds; installed completion accounted for 11.468 seconds. Profiling overhead is substantial; these are diagnostic timings, not benchmark results.

Two normalization boundaries copied the complete canonical tree and then independently copied its assessment subtree again. The repair uses existing `copy_with_tree_ownership` certification to reuse that private assessment only for unaliased plain JSON trees. Aliases, opaque values, and fallback cases retain independent-copy behavior. No reconciliation, scanner rule, validation, hash, locale, score or approval step is skipped. There is no persistent cache or shared source mutation.

## Fixed-condition local measurements

Python 3.12, installed dependencies, same process and same immutable Spanish fixture, input constructed before timing. The fixture uses `_package('es-MX')` and adds 1,681 rows under `assessment.performance_probe`; each row has 16 synthetic text/index records. It measures bulk retained-tree handling, not real candidate investigations. Baseline forces the existing fast tree copier to return ownership=false; candidate enables ownership. This isolates the redundant subtree copy without changing the copy engine. Every alternating result was equal to the baseline canonical output.

No test processes were running during the final measurements. Order and all final samples:

| Mode | Wall seconds | CPU seconds |
| --- | ---: | ---: |
| baseline | 4.581343 | 4.580203 |
| candidate | 4.013687 | 4.013498 |
| candidate | 4.279818 | 4.276151 |
| baseline | 4.765699 | 4.765440 |
| baseline | 4.541367 | 4.540820 |
| candidate | 4.259809 | 4.259657 |

Median preparation wall time: 4.581 to 4.260 seconds (7.0% lower locally). Preliminary measurements overlapped tests and are excluded. Process-wide RSS is cumulative, so it was not attributed to individual alternating samples.

Separate fresh processes, sequential baseline/candidate/candidate/baseline, same fixture and preparation timer:

| Mode | Wall seconds | CPU seconds | Process peak RSS KiB |
| --- | ---: | ---: | ---: |
| baseline | 4.116335 | 4.116020 | 177532 |
| candidate | 4.103674 | 4.103537 | 172112 |
| candidate | 4.111994 | 4.111805 | 172112 |
| baseline | 4.346310 | 4.346231 | 177524 |

Fresh-process timing overlaps substantially; peak RSS is about 5.3 MiB lower in these samples. Import/fixture construction is excluded from preparation timing but included in process RSS. No end-to-end production speedup, confidence interval, or scalable-load claim follows from these small synthetic measurements. Recommendation: adopt as a small verified allocation reduction, not as resolution of slow Spanish export. Larger preparation and finalization work remains.

## Correctness verification

103 tests passed, including installed English/Spanish complete artifact equality (PDF bytes, canonical values, manifests and hashes), alias graph equality, source isolation, and copy-count checks:

```
python -m pytest -q tests/test_scanner_truth_owned_copy.py tests/test_scanner_applicability_v2.py tests/test_comprehensive_authoritative_scanner_truth_v62.py tests/test_owned_report_preparation_copy.py tests/test_report_json_copy.py
```

43 existing pypdf/fixture warnings were reported. An initial invalid synthetic fixture omitted scanner totals and correctly failed population validation; the fixture was corrected with a reconciled one-candidate total, without altering validators. Independent review found no semantic or isolation blocker. Hosted Python 3.11 CI and production timing remain unverified. No report was rewritten, assessment started, or deployment performed.
