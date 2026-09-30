# Bitcoin final-report expanded storage capacity

The preserved run `comprun_bef5c30980944b6b975039be9dfb17fd` assesses
`bitcoin/bitcoin` at `e7aef7e86da79000aa42f5ba6d13b0d123d9da7c`.
Its final-report publication exceeded the 512 MiB expanded storage cap.
The renderer exited successfully, but this alone did not establish publication
or final-artifact validity.

## Production measurement

Release `a0a5775c3b628337584438a3fd894c2331e8423f` dispatched the bounded
v13 recovery. The workflow initially misclassified the old terminal projection
returned with a background acknowledgement as the new result. The backend
continued independently and emitted this content-free measurement at
`2026-09-30T05:36:48.138046011Z`:

| Measurement | Bytes |
| --- | ---: |
| Exact attempted canonical record | 748,581,807 |
| Previous expanded cap | 536,870,912 |
| Current-process lifetime peak RSS | 4,538,740,736 |

Measurement completed in 8.839 seconds. RSS covers the observing process's
lifetime, not the isolated renderer or aggregate service memory. The Railway
service has a 24 GiB memory limit; sampled service metrics cannot exclude
short-lived peaks. No record content or dynamic exception text was retained.

## Bounded repair and qualification

The expanded cap becomes 1 GiB (1,073,741,824 bytes), providing roughly 43%
headroom above this observed record. The 128 MiB compressed cap, envelope
schemas, exact length and SHA-256 checks, corruption checks, canonical record
integrity, immutable review history and delivery gates remain enforced.
No scanner evidence or report aliases are discarded.

The PostgreSQL restart workflow runs
`scripts/postgres_run_storage_capacity_proof.py` for both v2 token references
and v3 chunk references. Each synthetic fixture exceeds 960 MiB; publication
uses the canonical run store and a separate Python process reloads the stored
run. Every alias, identity, revision and integrity hash must match, review must
remain required and delivery prohibited. Each process must stay below 6 GiB
peak RSS. The database URL comes only from the CI test database environment.
Local SQLite qualification is supplementary to the required native PostgreSQL
qualification and is not production acceptance.

Recovery generation v14 grants one attempt after v13 collected the measurement.
Older attempts remain in history; another failure in v14 stays bounded. The
recovery workflow prepares the rewind with zero stages, then observes a newer
persisted terminal revision instead of treating a stale acknowledgement as an
outcome. Continuation failures log only allow-listed static codes and types.

A merge or passing synthetic qualification does not certify this Bitcoin run.
Production recovery must still persist the result, pass downstream artifact
verification and reach the review boundary. Human approval and client delivery
are separate actions. This change does not independently qualify all C++
repositories or their runtime execution.
