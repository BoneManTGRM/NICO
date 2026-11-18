# Synthetic qualification only

This is a frozen copy of the execution-disabled scoped verifier candidate tied to
NICO source release `5eb768b5776f88bae86e972c76267915cc874c85`.
Its source manifest is materialized from the checked-out public repository and
verified before loading. The workflow uses preinstalled PostgreSQL 16 binaries,
creates a private temporary Unix-socket-only cluster, and populates synthetic rows.
No production credentials, backups, service connections, or artifacts are used.

`qualify_postgres.py` is a CI-only harness, not an approved restore runner. It does
not accept host, credential, SQL, or data inputs. All candidate dispatch guards
remain disabled. Passing verifies synthetic SQL, scope, decoding, and cleanup
behavior, not production permissions, backup lineage, restore readiness, or live
resource containment. The pipe adapter's status labels remain derived fixture
labels, not native protocol attestation. Output is a bounded synthetic summary in
the job log; no retained Actions artifact or cache is created.
