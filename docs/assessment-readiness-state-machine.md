# Assessment readiness state machine

- `idle`: intake can be configured.
- `checking`: readiness and durable storage are being verified; no run exists.
- `starting`: readiness passed and intake creation is in progress.
- `running`: an exact run exists and is continuing.
- `unavailable`: service or configuration is temporarily unavailable; this is not automatically a failed run.
- `failed`: a created run or non-retryable creation request failed.
- `review_required`: automated stages completed and expert review is required.
- `complete`: reserved for completed lifecycles that do not require the review gate.
- `timed_out`: bounded status polling ended without claiming a terminal result.

Retry without a run ID repeats preflight. Retry with a run ID reads and continues that exact run rather than creating another intake.
