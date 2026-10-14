# Trusted ESLint unavailable presentation

Parent's inspected diagnostic run 38606592923 reported Spanish publication failure
on the exact joined trusted ESLint verification-failure/project-command-denial
message. Both worker processes exited successfully; this was not a timeout.
No diagnostic rerun or private artifact download was performed here.

Two synthetic regressions failed on main 4114d254 before this change: the exact
message lacked translation; unknown prose derived from a raw scanner record was
not checked by preflight. Two exact complete-message translations (bare and tool
prefixed) preserve NICO_ALLOW_PROJECT_COMMANDS=true and the unavailable meaning.
Preflight now checks the current renderer's derived unavailable prose, leaving
raw records untouched. It does not claim coverage of every late renderer field.

Verification: 60 tests passed across eight isolated modules, including both
production bootstraps, unknown-prose rejection, preflight/publication agreement,
input digest equality and unchanged score/finding/approval/delivery data. An
independent read-only review found no blockers. A combined-process batch had three
v87 parity failures also reproduced unchanged on baseline; all 12 v87 parity
checks pass in isolation. No test-order source workaround was added.

This establishes the exact translation repair and synthetic source preservation,
not a new production PDF, a full retained render, or standalone PDF detail parity.

Reconciled once with main d04ac7e48a60615c07c029bfee43ee2b3c1b891e after
PR1731 merged. The two affected Spanish regression modules and the inherited
exact service-occurrence security tests passed: 50 tests. Existing isolated
60-test evidence remains applicable to unchanged renderer changes. No diagnostic
assessment or deployment was requested.
