# Fuzz abort and evidence retention correction

The previous executor ran the remaining corpus and campaign after a timed-out,
truncated, or nonzero replay. It also retained replay results only after the
campaign returned, losing completed replay evidence if the shared deadline
prevented the next command from starting. Both behaviors were reproduced against
parent 3cbe702 without native Bitcoin execution.

Replay rows are now appended to the evidence immediately. Any failed replay
aborts subsequent execution. A completed campaign row is retained before metric
parsing. The prefix validator checks exact ordered operation identity, command,
output digest and timing for retained replays. A real worker_runtime_deadline
between fuzz operations is accepted only for v4 with the full 6000-second elapsed
budget; it remains incomplete, with no fabricated failed native operation.
Earlier completed sanitizer failures remain recorded as the first failure.

Verification: 1351 passed, one local native-toolchain skip, 27 new fault and
corruption cases. Independent reviewer ran 232 affected tests, all passing,
and reviewed the remaining full PR production/workflow diff. Data-only validation
of retained run 36235924285 reproduces its exact original summary, including
failed UBSan and failed fuzz build. No test population, timeout, toolchain,
qualification or approval gate was relaxed. This is not Bitcoin fuzz execution.

The candidate still requires terminal native evidence and report acceptance.
See verification.json for exact source and JUnit hashes.
