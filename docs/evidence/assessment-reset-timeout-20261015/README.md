# Ordinary assessment reset: local synthetic verification

Base: main6d546133652135ac2cb4ddc1689531850ae36bc1.
Branch: fix/assessment-reset-timeout. No publication, CI dispatch, deployment,
production requests or browser actions. The user's active assessment was untouched.

The actual useAssessmentRun hook and layout-level ComprehensiveStuckRunRecovery
are mounted in an owned synthetic hook/event harness. A pending old lifecycle
request times out after Start new assessment. Before correction its global timeout
listener restored the old run_id, deleted new_assessment, and could cause pageshow
to resume it. A delayed old timeout could also overwrite a newer selected run.
The original four tests failed three cases; legitimate same-run recovery passed.
The third failure demonstrated that a thrown history.replaceState aborted reset
before clearing the visible result. This proves conditional code defects, not the
cause of the user's observed iPhone incident.

Only two production files change:
- ComprehensiveStuckRunRecovery.tsx ignores timeout events when the URL explicitly
  requests a new assessment or names a different run. It does not dismiss valid
  recovery for the current run or change request budgets.
- assessmentRunPersistence.ts falls back to location.replace(url.href) when reset's
  history replacement throws. The absolute URL preserves the current origin even
  for a double-leading-slash pathname. The reset marker suppresses saved restoration.

No changes to storage deletion behavior, authentication, durable report storage,
assessment creation, scoring, approval/delivery gates, C++ or database pilot.

Commands (existing installed dependencies only):

    NICO_TEST_WEB_ROOT=/workspace/NICO/apps/web node --test tests/js/assessment-reset-timeout.test.cjs
    NODE_PATH=/workspace/NICO/apps/web/node_modules node --test tests/js/assessment-poll-exhaustion.test.cjs
    PYTHONDONTWRITEBYTECODE=1 /workspace/nico-venv/bin/python -m pytest -p no:cacheprovider -q tests/test_comprehensive_stuck_run_recovery_guard.py tests/test_assessment_active_run_reset_contract.py tests/test_mobile_active_run_reset_clearance_v1.py

Results:6new integration regressions pass,26existing polling/lifecycle tests pass,
and23existing reset/recovery/mobile contract tests pass. Zero failures/skips in
these candidate runs; Python emitted one pre-existing syntax warning. Baseline and
candidate output are retained alongside this note. The final six tests expand the
original four with current-run fallback preservation and the same-origin edge case.
Independent read-only reviewer ran all6final regressions and found no blockers.
git diff --check passed.

Limitations: synthetic DOM/events and injected network replies, no real browser or
Safari validation, no full frontend build/typecheck, and no proof that this was the
actual phone failure. Browser history fallback is tested by injected exception;
real navigation is not exercised. Same-origin policy, active workflow and durable
reports are not modified by any verification action.
