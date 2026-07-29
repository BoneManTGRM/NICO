# NICO v2 migration checklist

This PR establishes the replacement contracts and adapter. Production migration is complete only when all items below are satisfied in code and CI.

- [ ] Final Comprehensive generation calls `apply_v2_pipeline` before persistence or response serialization.
- [ ] No later layer mutates findings, scanner results, lifecycle state, Markdown, PDF, CSV, or canonical hashes.
- [ ] API status responses expose `assessment_state` as the authoritative lifecycle field.
- [ ] Web UI derives banner, review label, client-ready label, and actions from `assessment_state` only.
- [ ] Scanner workers persist normalized `ScannerResult` records for Bandit, ESLint, Gitleaks, TruffleHog, Semgrep, TypeScript, npm-audit, pip-audit, and OSV.
- [ ] Production image contains every required scanner binary and version evidence.
- [ ] Each required scanner produces an exact-SHA artifact and SHA-256.
- [ ] Exit-code handling is tested using real scanner fixtures.
- [ ] JSON, Markdown, PDF, CSV, and UI expose the same canonical truth SHA-256.
- [ ] Production smoke test generates a fresh report and rejects duplicate findings, repeated criteria, contradictory states, and duplicated filename suffixes.
- [ ] Legacy Phase 9 through Phase 17 post-generation mutation paths are disabled or removed.
