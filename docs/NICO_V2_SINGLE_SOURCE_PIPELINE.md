# NICO v2 single-source assessment pipeline

## Decision

NICO must stop repairing report surfaces after they are generated. JSON, Markdown, PDF, CSV, and UI must consume one immutable canonical assessment object and one assessment state.

## Required pipeline

1. Capture one immutable repository snapshot.
2. Run scanners against that exact snapshot.
3. Normalize every scanner into `ScannerResult`.
4. Build one canonical evidence population.
5. Build one semantic finding population.
6. Reject duplicate findings before scoring or rendering.
7. Score and prioritize only canonical findings and normalized scanner evidence.
8. Render JSON, Markdown, PDF, CSV, and UI projections from the same canonical object.
9. Bind every output to the same canonical truth SHA-256.
10. Fail closed if any output hash, commit identity, finding population, or lifecycle state disagrees.

## Scanner contract

Every scanner must supply:

- scanner name
- immutable commit SHA
- normalized state
- completed and verified flags
- artifact SHA-256
- findings
- duration
- stdout and stderr summaries
- failure reason
- exit code

A findings exit code is not automatically an execution failure. Bandit, ESLint, Gitleaks, and TruffleHog may complete with findings only when a valid exact-SHA artifact exists. Missing binaries, timeouts, malformed output, wrong working directories, absent artifacts, and commit mismatches remain explicit failures.

## Finding contract

A semantic finding is identified by category, normalized source location, normalized decision title, and observed evidence. Legacy IDs and prioritized IDs for the same evidence become aliases on one canonical finding. Acceptance criteria are deduplicated independently of method and target-commit annotations.

Publishing is forbidden when duplicate semantic findings remain.

## Lifecycle contract

The only allowed states are:

- `running`
- `analyzing`
- `generating_report`
- `review_required`
- `client_ready`
- `failed`
- `cancelled`

A complete package awaiting approval is `review_required`, never `failed`. UI labels, API status, persistence records, and artifact metadata must derive from this one state.

## Release gates

The release must fail when any of the following is true:

- a scanner marked verified lacks an exact-SHA artifact hash
- duplicate semantic findings exist
- acceptance criteria repeat
- client artifacts use different canonical hashes
- UI state conflicts with package/review state
- report filenames contain duplicated approval-state suffixes
- PDF or Markdown was rendered before canonicalization
- a report contains a finding population different from canonical JSON

## Migration rule

Existing Phase 9 through Phase 17 repair layers may remain temporarily as compatibility adapters, but they may not independently mutate findings, scanner state, lifecycle state, or client artifacts after the v2 canonical object is built. They should be removed after production parity is proven.
