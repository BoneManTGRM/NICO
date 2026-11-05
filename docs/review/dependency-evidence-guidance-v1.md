# Dependency evidence next steps

Local follow-up to PR1873, based on2ecf0cf6d8fd4d72f7f12a5217eaefaacbccae26; PR1873 remains stacked on PR1871. This change projects a bounded authored next-step code for dependency candidates from existing server-persisted state. It performs no new acquisition, parsing, qualification or disposition action.

Codes distinguish: missing supported scanner identity, missing/current-scope capture, missing usable lockfile observation, unavailable observation, unresolved matching and collected locked identity. Missing evidence does not prove parsing failure, package absence, budget exhaustion or that matching was attempted. Row and observed capture identities are checked before advising reconciliation. Only a separately qualified receipt permits collected-identity advice. Caller-supplied stored next-step strings are ignored.

English/es-MX advice preserves installation/advisory/runtime-use questions and existing human gates. UI association retains original canonical index and fingerprint; unmatched/duplicate/stale packets cannot supply the guidance. The collected-identity message additionally requires the matching identity object. Unknown authored codes are not rendered as prose.

Baseline7 tests failed because the field was absent. Final151 guarded backend tests and64 deterministic rendered component tests passed; TypeScript and diff checks passed. Zero final loader/network/SQLite guard events. No browser layout qualification or measured production workload reduction. Broad architecture/velocity scorecards remain unchanged.
