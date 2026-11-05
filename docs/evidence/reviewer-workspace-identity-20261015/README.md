# Exact-run reviewer workspace repair

Base: 2e8b4fdbcfd1c397bb87dd559447f86792e84cc6. Branch fix/reviewer-workspace-identity. Local only; no actual review/disposition, production request, publication, merge or deployment.

## Reproduced defects

The real page's three panels held independent run IDs. A top selection change left the action panel's old identity and target in place. ReviewWorkPanel and ReviewQueueBrowser converted JSON parse failures to empty objects and accepted wrong-run or malformed projections; candidates={} crashed the browser filter. Sibling counts did not refresh after writes. A late GET could populate an obsolete selection. The initial whole-page synthetic harness reproduced all 12 cases as failures; baseline output is retained.

## Repair boundary

ReviewerWorkspace holds one selected run ID with a synchronous identity reference. All panels receive that identity; keyed panels discard old form targets, projections and filters on selection changes. Selection changes make no server requests. Cookie/session transport and explicit human action payloads remain unchanged. Each response must still belong to the selected live scope before publication; older requests cannot overwrite a newer read or selected run.

The shared parser rejects invalid JSON, wrong-run identity, missing canonical identity, malformed candidate/cluster arrays, incomplete count/maps and invalid human-review/client-delivery flags. It preserves received evidence; it does not generate dispositions or approve delivery. Backend response details are not exposed through the new localized error boundary. Existing server v2 projection supplies the required fields. ReviewerQueue keeps its existing canonical parity and terminal gates.

Successful writes trigger exact-run scoped sibling GET refreshes. A network failure, server failure or unverified success response triggers a GET to reconcile saved state without repeating the POST. The outcome remains explicitly unconfirmed even if that read succeeds; failed reconciliation leaves actions blocked. The mutation guard prevents duplicate concurrent submission from one panel. Switching runs discards stale write completion and does not refresh the new run.

Independent review found an additional race: a sibling refresh could supersede another panel's pending mutation. A new regression reproduced premature unlocking. Refreshes now coalesce while a mutation or its reconciliation is pending; after settlement only the current run performs the deferred read. Success and malformed-write variants both pass; the failing race evidence is retained.

## Verification

- 53 JavaScript checks passed: 23 whole-workspace cases plus 30 existing cookie/session/proxy cases. Controls cover canonical response validation, identity changes, current/old read order, auth denial, pending write duplicate suppression, unchanged human authorization fields, failed reconciliation, persistent uncertainty, and visible sibling pending-count refresh.
- 38 Python checks passed across workspace wrapper, locale contracts, producer/consumer routing and phase2 review/runtime boundaries. The Python count includes a wrapper that reruns the 23 JavaScript cases; these are not 38 additional independent browser tests.
- npm run lint (tsc --noEmit) passed using existing installed dependencies; no exact-lock installation or Next build was performed.
- Independent read-only verifier passed 23 workspace tests and git diff --check, confirmed v2 schema compatibility, and found no remaining blocker after the race correction.
- Standard pytest discovery includes tests/test_reviewer_workspace_identity.py; no skips or authorization gates weakened. Existing source-location contract tests were updated for the shared wrapper/parser, and existing cookie tests now supply valid projections and explicitly load them before submitting.

This is a synthetic component/hook boundary harness with real shipped TypeScript functions and mocked HTTP. It is not a real-browser or production acceptance claim. Scoring formulas/provenance, C++ and the database pilot are untouched.

## Separate release prerequisite

Read-only GitHub checks confirmed main2e8b4fdb and 25 exact-SHA Actions runs, none Node.js CI. Workflow-specific runs URL was unsupported by the connector; its supported Actions-run collection succeeded. No workflow-dispatch action is exposed by the available connector. The earlier forbidden GitHub CLI route was not retried and no credentials were changed. No dispatch was attempted; parent needs another supported route to produce the exact-main receipt. This prerequisite does not affect local reviewer test results.

## HTTP 408 parsing correction

PR1744 head954c64c3654cb62513b002b0b510b2c1db6e45cf was verified open/draft on fix/reviewer-workspace-identity before edits. Its tree matches localaf891b4f. Non-JSON HTTP408 responses took the JSON parse-error path, which omitted the ambiguity classification already applied to parsed HTTP408. One expression now includes status408 in both paths. No other production behavior changes.

Eight component regressions cover both disposition and QC-sampling writes with JSON, empty, HTML and truncated408 bodies. Baseline:2passed/6failed. Candidate:61focused JavaScript checks passed (31workspace plus30existing transport checks), Python wrapper1passed (reruns31workspace checks), and tsc --noEmit passed. Each new case requires exactly one POST, GET-only same-run reconciliation with cookie transport, persistent uncertainty notice and unchanged human authorization flags. Existing selected-run, stale response, pending-mutation, authorization-denial and approval/delivery controls remain passing. No production requests or decisions were performed.
