# Phase 12C negative evidence cases

The production evidence manifest must reject:

1. A staging SHA that differs from production or the requested release SHA.
2. A second verification pass created from another commit.
3. Missing Express, Mid, or Full evidence.
4. English-only or Spanish-only artifact sets.
5. Missing PDF, HTML, or Markdown output.
6. Artifact identity without a SHA-256 digest, or a digest without an identity.
7. Cross-tier artifact reuse or contamination.
8. Missing mobile-download, smoke-test, or manual-inspection evidence.
9. Unhealthy deployment state, stale deployment identity, or partial evidence packets.
10. Any remaining critical or high defect.

These cases are release blockers, not warnings.
