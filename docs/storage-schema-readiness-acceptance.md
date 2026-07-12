# Storage Schema Acceptance Checklist

Use this checklist after the storage-schema readiness change is merged and deployed.

- [ ] Vercel and Railway both report the exact current `main` commit.
- [ ] `GET /operations/storage-schema` requires operator authentication.
- [ ] The endpoint reports `adapter=postgres`.
- [ ] `persistence_available=true`.
- [ ] `schema_ready=true`.
- [ ] `migration_ready=true`.
- [ ] `catalog.complete=true`.
- [ ] `catalog.missing_tables` is empty.
- [ ] `catalog.missing_columns` is empty.
- [ ] The current migration version is present.
- [ ] The current migration contract hash matches.
- [ ] `/operations/readiness` includes and passes `storage_schema_verified`.
- [ ] `/operations/observability` reports durable storage.
- [ ] `/operations/alerts` has no storage or readiness P0/P1 alert.
- [ ] The Production Release Gate passes for the exact deployment SHA.
- [ ] A fresh Mid run survives a normal backend restart before report generation.
- [ ] A fresh Full run survives a normal backend restart before report generation.
- [ ] Scanner, report, approval, delivery-grant, and receipt records remain readable after restart.
- [ ] No client delivery is resumed until the affected workflow is human-reviewed.

The last six restart/recovery checks belong to the next Phase 3 implementation stage. They are intentionally not claimed complete by schema verification alone.
