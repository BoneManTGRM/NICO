# NICO Persisted Historical Comparison v1

## Purpose

The Historical Delta Engine can compare two decision-grade contracts, but a repeat assessment is only operationally useful when NICO can locate the correct prior contract automatically.

This binding reuses the existing `assessment_runs` storage path. Full-run persistence already retains the response and report package while removing duplicated PDF bytes. The selector searches those retained records for the newest compatible decision-grade contract.

## Compatibility rules

A prior record is eligible only when:

- it is inside the same authorized customer and project storage scope;
- it is not the current assessment run;
- it represents the full-assessment workflow;
- it contains a valid decision-grade contract;
- the repository identifier matches exactly, case-insensitively;
- the assessment type matches;
- the contract belongs to the same schema family as required by the delta engine.

The newest compatible contract is chosen using assessment completion time, followed by storage update and creation timestamps.

## Evidence and truth behavior

The selector records:

- records examined;
- compatible candidates;
- rejection counts by reason;
- selected assessment ID and commit SHA;
- storage adapter;
- whether persistence is available;
- whether deployment-surviving durability is verified;
- the exact selection rule.

Memory or other non-durable storage may support comparison during the current process, but it is not described as durable. Postgres with verified persistence is identified separately.

## Failure behavior

When no compatible prior contract exists, NICO emits `no_comparable_previous_assessment` and the delta engine does not create synthetic change language.

When storage lookup itself is unavailable, report generation continues without a historical comparison. The package records `history_store_unavailable`, preserves the failure boundary, and still forbids synthetic history.

## Production binding

The history wrapper runs before Comprehensive contract generation. When a compatible prior assessment exists, it supplies:

- `previous_comparable_assessment_id`;
- `previous_decision_grade_contract`;
- the previous structured assessment when retained.

The existing Historical Delta Engine then performs evidence-safe comparison. Public report metadata excludes the full prior contract and exposes only the selection audit record.
