# Saved review recovery when browser history rejects writes

Base: 6d546133652135ac2cb4ddc1689531850ae36bc1. Local isolated branch fix/assessment-recovery-history. Unpublished reset commit afd48a715 remains untouched in its own worktree.

A synthetic source-matched terminal payload (review_required, terminal=true, human_review_required=true, client_delivery_allowed=false) is received successfully by the actual recovery hook. If history.replaceState throws during writePersistedRun, the hook previously catches that local exception as a service issue before publishing the recovered result. Initial four-case regression: two normal-history passes, two rejected-history failures (English and Spanish), showing unavailable instead of review_required. This proves a source defect, not the cause of the live run; its actual assessment response and browser exception were not observed.

Fix: skip an unchanged URL and catch only the optional history replacement failure. Store the exact-run identity as before; do not alter server response, terminal authority, findings, approval or delivery. Use the absolute URL derived from current location to preserve origin. No navigation fallback or network mutation is added.

Verification: six focused JavaScript checks plus 34 existing polling/recovery checks pass (40 total). Tests include preserved identity, commit, findings, review/delivery flags, one GET without POST, zero writes for unchanged URL, and simultaneous storage/history failure with an existing exact-run URL. npm run lint (tsc --noEmit) passed. Selected Python checks did not run: default interpreter has no pytest. No dependencies installed. Independent approval_review reviewed source and ran initial four cases successfully; no blockers. Two extra cases were then added and passed.

Limit: if both storage and history writes are denied while no exact-run URL exists, durable browser recovery remains unavailable; this change preserves the current server result, not a guarantee of persistence under browser denial.

English review PDF source route: /api/nico/assessment/comprehensive-run/{run_id}/localized-report/en/pdf. Supported assessment UI action: Download review PDF. Its handler checks identity, canonical-truth binding, PDF SHA-256 and pending approval/blocked delivery headers before saving bytes. No production retrieval or live-run diagnosis was performed.

## Combined ordinary UI repair

Rechecked live main at 6d546133652135ac2cb4ddc1689531850ae36bc1 on October 15; open PRs were 1712, 1722 and 1727, none overlapping this ordinary UI repair. Branch fix/assessment-recovery-and-reset combines preserved reset commit afd48a715 with history recovery commit b15cd8b2. Both original worktrees/commits remain intact. No conflict: clearPersistedRun retains its explicit same-origin reset navigation fallback, while writePersistedRun tolerates history denial without navigation. Existing legitimate same-run recovery remains enabled; stale timeout events cannot override reset or selection of another run.

Combined validation: 46 JavaScript tests pass, no skips; npm run lint (tsc --noEmit) passes. New pytest wrapper tests/test_assessment_recovery_history_and_reset.py ensures ordinary hosted test discovery invokes both new six-case JavaScript suites. The wrapper was run directly using Python stdlib and passed; this is not a pytest-run claim. Local pytest is unavailable. Existing dependency installation was reused; exact-lock dependency installation, full Python checks and Next build are left to standard CI. No checks weakened, no manual workflow dispatch. Independent reviewer found no combined source blocker.

Publication target is a draft PR only. Production acceptance and actual live-run cause remain unverified. No assessment start/resume, merge, deployment, report inspection, C++ or database pilot action.
