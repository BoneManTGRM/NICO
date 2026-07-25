# Decision-Grade CI Reliability

Version: `nico.decision_grade_ci_reliability.v1`

NICO must not calculate CI reliability by treating every non-green workflow as the same kind of engineering failure. The classifier separates outcomes before any percentage is reported.

## Run classes

- `success`
- `code_or_test_failure`
- `infrastructure_failure`
- `timeout`
- `cancelled_expected`
- `cancelled_unclassified`
- `skipped_or_neutral`
- `unknown_non_success`

## Reliability denominator

The denominator includes only equivalent classified outcomes:

- success
- code or test failure
- infrastructure failure
- timeout

Expected concurrency cancellations, skipped or neutral runs, and unresolved non-success outcomes are excluded. They remain visible in the evidence ledger.

## Fail-closed behavior

Assurance is `REVIEW LIMITED` when:

- a cancellation is not proven expected;
- a non-success outcome cannot be attributed;
- a requested workflow has no observed evidence;
- no workflow evidence is available.

The classifier does not change the technical score, approve delivery, or infer that a repository is healthy.

## Report integration

The evidence package is written to:

- `ci_reliability_evidence` on the report result;
- the report package;
- canonical JSON;
- report quality metadata.

Each classified run retains its workflow name, immutable commit SHA when supplied, timestamps, raw conclusion, rationale, and evidence reference.

## Expected cancellation evidence

A cancellation is treated as expected only when the source explicitly identifies supersession, a newer run, or concurrency cancellation. A plain `cancelled` conclusion is not enough.
