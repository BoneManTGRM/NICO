# Bounded retained PDF preparation lifecycle

Source baseline: ce694923bdc8fc0866968ccc94acea2a8b1613fe.
Reconciled main: 4114d25442599ee5d99d265ee13263ec3039bc7c.
Rollout remains OFF. No production acceptance, deployment or assessment is claimed.

## Reproduction and repair

The preserved synthetic reproduction produced four failing assertions on the
published baseline: initial restoration could spawn after lease expiry; initial
restoration did not consume the child's allowance; a blocked heartbeat prevented
physical child termination for cancellation and deadline expiry. Two additional
baseline diagnostics exposed final-restoration lease loss and attempt exhaustion.

The coordinator now renews ownership independently across initial/final full
restoration, fingerprinting and preparation. Each phase consumes the original
900-second wall budget; immediately before spawning, the database ownership and
remaining budget are read again. The 30-second lease, two-attempt policy, full
source restoration, source row/history lock, checksum checks, draft approval and
blocked client-delivery semantics remain unchanged.

Admission and retrieval have bounded observation, while slow Python/database
calls retain their existing capacity until physical completion. Source work is
not falsely described as forcibly stopped. Child cancellation/deadline handling
is independent of database heartbeat completion. Private temporary files remain
quarantined until outstanding file operations and physical child exit finish.

COMMIT decision and timeout classification are synchronized. A COMMIT already
in flight can finish after its caller's deadline: this is explicitly an unknown
outcome, not a claim of rollback or successful publication. Capacity stays
quarantined until completion. Authenticated GET recovery rechecks the current
source/policy and existing download gates. A lost POST response saves a request
marker and resumes through GET lookup, without another admission request.
Transient 503 retains recovery state. An uncertain admission lookup 404 retains
its versioned original-deadline marker; only job-specific 404 or definitive
409/422 clears stale state. Reload does not reset the uncertain-admission window.
After expiry, an explicit click permits one bounded GET without another POST.
Approved-source alternate-language reapproval retains its existing ordinary route.

## Verification and limits

- 23 synthetic lifecycle regressions, including expired/cancelled/reclaimed
  captures, slow serialization/output/publication, blocked heartbeat, uncertain
  admission/publication commits, atomic commit registration and late child writes.
- 129 focused Python checks passed, including real isolated synthetic Spanish PDF
  rendering, API/ledger/Postgres SQL contracts and proof-safety tests.
- 118 JavaScript review/proxy/localization/workspace checks and TypeScript passed.
- 652 security checks passed for the separately approved exact nonsecret scanner
  occurrence. No npm dependency changes were imported into this branch.
- Two independent read-only reviews found no remaining blockers.

The earlier real PostgreSQL CI run 38615352718, job 116028913460, succeeded on
ce694923. It qualifies ledger ownership only, not the entire retained restoration,
source-lock, ready-publication and retrieval lifecycle. New-head CI remains to be
observed. The actual private retained report and independent persisted run/history
commitment are unavailable in this executor. No actual retained-render or input
hash/semantic equivalence claim is made. A permanently blocked native/database
operation may retain quarantined capacity indefinitely. Production/mobile
acceptance remains with the owner; no activation or deadline increase occurred.

## Published-head review correction

A second independent review of b71ebc28 identified two additional races. Both
were reproduced before modification: delayed heartbeat thread start could release
capacity while its call remained active; POST 503 followed by lookup 404 erased
an uncertain admission marker before late COMMIT became visible.

Completion events now track scheduled calls before thread start, and quarantine
joins the stopped lease supervisor before its final outstanding-operation check.
The UI retains uncertain intent through lookup misses, bounds polling by the
original persisted deadline, and permits GET-only explicit recovery afterward.
Both reviewers accepted their scoped corrections. Current-main-pin verification:
129 focused Python, 118 JavaScript and TypeScript passed. No new production or
actual retained-render acceptance is claimed.
