# Postgres Restart Proof

The `Postgres Restart Proof` workflow exercises NICO's real `PostgresAdapter` against an ephemeral PostgreSQL 16 service.

It creates clearly synthetic, uniquely scoped records for:

- an authorized repository;
- an assessment run;
- a scanner run;
- an evidence item;
- a draft report;
- a pending human approval; and
- an audit record.

The proof discards the first adapter instance, creates a fresh adapter, and verifies that every critical record remains available with the same customer, project, and run identity. It also verifies exact tenant filtering, writes a post-restart assessment update, creates a third adapter, and confirms that the update survives while the pending human approval remains unchanged.

## Truth boundary

A passing artifact proves the Postgres adapter contract against the ephemeral CI database for that commit. It does not prove that Railway restarted successfully, that production credentials are configured correctly, or that a production backup can be restored.

The JSON artifact is synthetic and contains no database URL, password, admin token, client content, or live-production claim.

Production restart proof remains separate and must verify the deployed service and its configured durable database without exposing credentials or modifying a human approval decision.
