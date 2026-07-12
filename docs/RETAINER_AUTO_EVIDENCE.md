# NICO Retainer Automatic Evidence

## Purpose

Retainer Operations must describe ongoing engineering work from verified sources. It must not depend on an operator manually retyping commits, pull requests, issues, workflow status, releases, deployments, or blockers.

The production Retainer workflow binds an authorized repository, optionally reuses an exact Express or Mid baseline, refreshes GitHub evidence, reconciles current blocker state, and produces section scores only when their required sources were successfully checked.

## Production endpoint

```text
POST /retainer/ops
```

The production route replaces the legacy manual technical-summary implementation. Exactly one POST route is registered.

## Operator inputs

Required or structural inputs:

- repository owner/name;
- explicit authorization confirmation;
- authorized-by identity;
- authorization scope;
- customer and project scope;
- optional exact baseline run ID;
- evidence timeframe.

Manual inputs are limited to information GitHub cannot prove:

- roadmap decisions and priorities;
- client-update context;
- business and success metrics;
- budget and priority context.

Legacy technical fields remain accepted for request compatibility, but a bound production run replaces them with GitHub-derived evidence.

## Automatically checked sources

NICO checks:

- repository metadata and default branch;
- current branch-head commit;
- commits within the selected timeframe;
- pull requests updated within the selected timeframe;
- issue activity within the selected timeframe;
- all current open issues without a timeframe cutoff;
- GitHub Actions workflow runs;
- the latest observed state of each workflow;
- CodeQL-related workflow runs;
- releases;
- deployment records.

Every source-ledger item includes:

- source ID;
- verified or unavailable status;
- checked timestamp;
- item count when available;
- bounded note;
- derived-from source when applicable.

Provider response bodies, credentials, tokens, raw exceptions, and source snippets are not returned through the public result.

## Baseline identity

NICO may reuse a matching Express, Mid, Full, or stored assessment baseline when repository, customer, and project scope match.

The Retainer source binding can retain:

- baseline run ID;
- snapshot ID;
- snapshot commit SHA;
- scanner ID;
- observed current repository commit.

When the operator supplies an explicit baseline run ID, NICO fails closed if that exact run cannot be found and matched. It does not silently substitute a different run or repository-only evidence.

## Current blocker truth

An empty input field is not blocker evidence.

Blocker verification requires both:

1. all current open GitHub issues were successfully checked; and
2. the latest observed state of each workflow was successfully checked.

Current blockers include:

- open issues carrying configured blocker, critical, high-priority, security, P0/P1, or severity labels;
- workflows whose newest observed run is unsuccessful.

A historical workflow failure is not kept as a current blocker after a newer successful run for the same workflow.

Blocker states are:

- `verified_clear`: required current-state sources were checked and no blocker was found;
- `verified_blockers`: required sources were checked and blocker evidence exists;
- `unverified`: one or more required sources were unavailable.

Only `verified_clear` can produce a clear blocker score.

## Score reconciliation

The Retainer section card and its supporting module use the exact same score and status.

Sections are:

- Weekly Delivery Status;
- Backlog Health;
- Release Readiness;
- Monthly Strategy;
- Blockers / Approval Needs.

Every section includes `score_calculated`.

When a required source is unavailable:

- the section score is 0 as a non-calculated placeholder;
- `score_calculated` is false;
- status is `unverified`;
- the UI and report display `score unavailable` rather than `0/100` as a maturity conclusion.

When no repository source is bound, all Retainer section scores, evidence-readiness score, and overall maturity score remain unverified. Operator-supplied business context alone cannot create an overall Retainer score.

## Partial evidence

A source may be unavailable while other sources remain verified. Partial evidence does not invalidate verified items, but it cannot be treated as complete or clean.

Examples:

- unavailable open-issue access prevents blocker-clear status;
- unavailable workflows prevent current workflow blocker verification;
- unavailable releases or deployments remain disclosed in Release Readiness;
- missing roadmap or client context leaves Monthly Strategy unavailable.

## Storage boundary

The production route stores a bounded Retainer record containing:

- repository and customer/project identity;
- authorization metadata;
- baseline and observed-commit identity;
- section score/status/calculated flags;
- maturity and evidence-readiness summaries;
- human-review and client-delivery denial flags.

It does not persist the operator's full business notes, raw GitHub payloads, provider response bodies, or report source text in this bounded record.

## Frontend workflow

The canonical page is:

```text
/retainer-ops
```

The page:

- removes manual technical-summary fields;
- accepts repository/baseline/authorization/timeframe inputs;
- accepts only operator-owned business context;
- shows source checked times and item counts;
- shows repository commit, baseline run, snapshot, and scanner identity;
- shows `score unavailable` for unverified sections;
- discloses human-review and client-delivery state.

The legacy Command Center Retainer form is hidden and replaced by a launcher to the canonical page.

## Safety and approval boundary

Retainer Operations remains advisory.

It does not:

- communicate with a client automatically;
- approve roadmap, scope, budget, or timeline changes;
- deploy code;
- change production systems;
- authorize client delivery;
- reinterpret missing evidence as success.

Human approval remains required for production deployment, roadmap commitments, material scope/budget/timeline changes, and major dependency upgrades.

## Acceptance procedure

1. Confirm Vercel and Railway run the same current `main` SHA.
2. Open `/retainer-ops`.
3. Enter the authorized repository and customer/project scope.
4. Optionally enter an exact matching baseline run ID.
5. Confirm authorization.
6. Enter only business context GitHub cannot prove.
7. Run the Retainer evidence refresh.
8. Verify the observed commit and baseline/snapshot/scanner identity.
9. Review every source-ledger status, timestamp, and item count.
10. Confirm a failed historical workflow with a newer success is not a current blocker.
11. Confirm an open labeled blocker is surfaced regardless of age.
12. Confirm unavailable blocker-bearing sources produce `unverified`, not clear.
13. Confirm each card score exactly matches its reconciled module score.
14. Keep client delivery blocked until the normal human-review process is complete.
