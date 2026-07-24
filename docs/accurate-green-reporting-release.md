# Accurate Green Reporting Release Acceptance

This release fixes presentation contradictions and exposes the evidence required to earn green. It does not manufacture clean evidence.

## Required checks

- Existing NICO CI, CodeQL, security, resilience, persistence, and report contracts pass.
- Express Markdown and HTML replace legacy status-colored headings such as `YELLOW (89/100)` with the technical band and retain evidence assurance separately.
- The live assessment UI reprocesses score badges after every React update and presents separate score and assurance badges.
- A control is listed as verified green only when score >= 80, assurance is VERIFIED, and canonical disposition is GREEN.
- Non-green controls include explicit closure requirements derived from retained findings, unavailable evidence, and score constraints.
- Human review and client delivery remain blocked until authorized approval.

## Post-merge validation

- Deploy the exact merge SHA to Vercel and Railway.
- Complete two consecutive Express and Comprehensive production acceptance passes.
- Generate a new Express report from the merge SHA and verify UI, Markdown, HTML, JSON, and PDF parity.
- Confirm genuine scanner blockers remain visible until repaired and rerun.
