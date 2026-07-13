# Resilience Proof

The `Resilience Proof` workflow exercises NICO's durable scanner recovery and bounded operational degradation behavior against a real ephemeral PostgreSQL 16 service.

It proves that:

- a stale scanner run is reconciled to `recovery_required` without automatic resume;
- the exact scanner and parent-run identities survive a fresh storage adapter;
- recovery inventory reports attention required;
- an explicit operator resume claims the same scanner ID exactly once;
- a duplicate resume reuses the queued same-ID continuation instead of starting another worker;
- the resumed state survives another fresh storage adapter;
- memory fallback blocks durable recovery and discloses the Postgres requirement;
- operational event write and read failures produce degraded telemetry state rather than unhandled proof failure; and
- sensitive event metadata remains redacted.

## Truth boundary

The workflow uses synthetic records and a CI database. A pass does not prove that Railway restarted, that a production database backup is restorable, that a live scanner completed, or that a report is approved for client delivery.

Scanner recovery remains human-controlled. The proof never starts a real scanner subprocess, never permits automatic production changes, never approves a report, and never enables client delivery.

Production restart drills and live deployment history remain separate operator evidence.
