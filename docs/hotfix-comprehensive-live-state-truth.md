# Comprehensive live-state truth hotfix

This hotfix corrects three production-facing inconsistencies observed during an active Comprehensive run:

1. Durable persistence metadata disappeared after the first continuation response, causing the UI to show `Not verified` even though the run was stored durably.
2. PostgreSQL JSONB object ordering could render later stages before completed prerequisites.
3. The completed authorization stage did not include a customer-readable summary or bounded evidence.

The persisted canonical record, immutable identity, integrity hash, human-review requirement, and client-delivery block remain unchanged.
