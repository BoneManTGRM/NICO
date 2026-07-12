# Phase 3.1 Scope — Storage Schema Readiness

This change covers only structural Postgres readiness and migration-contract identity.

Included:

- version-controlled required table/column contract;
- deterministic contract SHA-256;
- migration ledger;
- startup verification;
- admin-authenticated readiness endpoint;
- required semantic-readiness check;
- safe failure disclosure;
- operator migration and rollback documentation.

Not included:

- automatic destructive migration;
- backup creation or restore execution;
- automatic workflow resume;
- queue replay;
- scanner restart;
- report regeneration;
- approval mutation;
- delivery mutation;
- client-delivery authorization;
- assessment score changes.

The next stage must implement restart/resume and duplicate-prevention verification against durable records.
