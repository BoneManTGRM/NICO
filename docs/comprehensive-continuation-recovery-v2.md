# Comprehensive continuation recovery v2

Production Comprehensive continuation requests must not own provider execution lifetime.

The Postgres production runtime commits a small exact-run running marker for the next stage and returns the continuation response before invoking the provider to completion. The detached worker may publish only while its lease remains the canonical marker for that stage. A repeated continuation while the marker is fresh returns the same canonical run and does not launch a duplicate provider invocation.

If the serving process disappears, the running marker remains in durable run storage. After the bounded orphan interval, a later continuation may replace that marker through optimistic revision control. A late superseded worker cannot overwrite the replacement because publication requires the original lease id to remain canonical.

Final report generation retains its dedicated atomic publication coordinator. Human review remains required and client delivery remains blocked until the existing approval path succeeds.

This boundary exists specifically so browser, proxy, or mobile transport timeouts cannot be the normal execution limit for repository assessment stages.