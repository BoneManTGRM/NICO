# Evidence Health Reconciliation

Version: `nico.decision_grade_report_view.v1`

## Purpose

The Evidence Health Summary must never claim that no scanner failure was retained when the canonical findings register contains a scanner failure or incomplete scanner result.

## Sources

Evidence health is derived from two canonical sources:

1. Structured scanner execution records.
2. Retained canonical findings that explicitly describe scanner failure, timeout, unavailability, or incomplete output.

Structured execution records remain the preferred source. Finding-derived limitations are used only when an equivalent scanner/status pair is not already represented in the structured execution ledger.

## Required classification

A finding-derived scanner limitation is treated as required when the finding is P0, P1, or explicitly marked as a release blocker. Lower-priority scanner limitations remain visible but do not automatically become required failures.

## Supported states

- `failed`
- `partial`
- `timed_out`
- existing structured states such as stale, conflicted, and permission unavailable

## Output guarantees

The report view now exposes:

- whether structured scanner execution records exist;
- completed scanners from structured execution records;
- all incomplete scanner records;
- finding-derived scanner limitations;
- required scanner failures;
- a confidence-effect statement consistent with the retained evidence.

The summary may state that no scanner failure or limitation was retained only when neither source contains one.

## Safety boundary

This reconciliation does not invent successful scanner executions, promote assurance, change technical scores, or authorize delivery. It only prevents a false-negative evidence-health statement when retained findings already prove a scanner limitation.
