# Dependency evidence next steps

Local follow-up to PR1873, based on2ecf0cf6d8fd4d72f7f12a5217eaefaacbccae26; PR1873 remains stacked on PR1871. This change projects a bounded authored next-step code for dependency candidates from existing server-persisted state. It performs no new acquisition, parsing, qualification or disposition action.

Codes distinguish: missing supported scanner identity, missing/current-scope capture, missing usable lockfile observation, unavailable observation, unresolved matching and collected locked identity. Missing evidence does not prove parsing failure, package absence, budget exhaustion or that matching was attempted. Row and observed capture identities are checked before advising reconciliation. Only a separately qualified receipt permits collected-identity advice. Caller-supplied stored next-step strings are ignored.

English/es-MX advice preserves installation/advisory/runtime-use questions and existing human gates. UI association retains original canonical index and fingerprint; unmatched/duplicate/stale packets cannot supply the guidance. The collected-identity message additionally requires the matching identity object. Unknown authored codes are not rendered as prose.

Baseline7 tests failed because the field was absent. Final151 guarded backend tests and64 deterministic rendered component tests passed; TypeScript and diff checks passed. Zero final loader/network/SQLite guard events. No browser layout qualification or measured production workload reduction. Broad architecture/velocity scorecards remain unchanged.

## Integration status

The opening paragraph records this change's historical stacked origin. Both
dependency changes were integrated into main by merged PR #1877 (`71a21713`);
#1873 is no longer a runtime prerequisite awaiting integration. The original
#1874 branch now reconciles its history with accepted main `bf42c567` and targets
main directly. This reconciliation changes documentation only and retains all
current evidence, lexical-binding, handler, approval and delivery safeguards.

Historical test counts above are preserved as historical evidence. Current
release qualification does not imply observed workload reduction or autonomous
review correctness. Missing proof still requires human contextual review.
