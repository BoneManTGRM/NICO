# Phase 7E live runtime verification

Observed production failure after Phase 7D deployment:

- Express remained at `truth_and_review_gates` and 96% beyond seven minutes.
- The page continued polling past the intended five-minute terminal boundary.
- The raw immutable run ID remained the primary mobile heading and overflowed the viewport.

Root cause addressed in this phase:

- Stall detection previously preferred the first pending item in the progress array over the backend's canonical `current_stage`. A stale pending item could therefore suppress truth-gate timeout detection even while the UI correctly displayed `truth_and_review_gates`.
- The friendly assessment naming helper was present but not connected to the rendered run-state heading.

Acceptance checks:

1. Express, Mid, and Full never display a lower accepted progress percentage or stage for the same run.
2. Canonical `current_stage=truth_and_review_gates` becomes terminal blocked after five unchanged minutes.
3. Terminal output includes blocking gate, reason, last successful checkpoint, and human-review requirement.
4. Raw run IDs remain visible only as technical detail and wrap safely on mobile.
5. Primary run heading uses a friendly tier label.
