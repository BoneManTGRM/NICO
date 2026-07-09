# Bandit triage workflow

NICO treats Bandit findings as evidence-bound until each finding is either repaired or covered by a signed triage decision.

## Flow

1. Hosted scanner worker runs Bandit and attaches the current-run scanner artifact.
2. NICO creates a `nico.bandit_triage.v1` artifact with stable `finding_key` values for each Bandit result.
3. If findings need review, NICO emits a `bandit_triage_approval_template` with the exact keys to review.
4. A reviewer may attach a `nico.bandit_triage_approval.v1` artifact with a decision for each non-blocking finding.
5. Static Analysis can lift only when:
   - Bandit/Semgrep/ESLint/TypeScript are verified for the current report run, and
   - Bandit has zero blocker findings, and
   - every review-required non-blocker has a signed decision.

## Approval artifact shape

```json
{
  "artifact_schema": "nico.bandit_triage_approval.v1",
  "decisions": [
    {
      "finding_key": "bandit_<stable_hash>",
      "rule_id": "B101",
      "location": "tests/test_example.py:12",
      "decision": "false_positive",
      "reviewer": "security-reviewer",
      "justification": "Assert usage is confined to test code and is not reachable in production runtime."
    }
  ]
}
```

Allowed decisions for non-blocking findings:

- `false_positive`
- `accepted_risk`
- `mitigated`
- `not_applicable`

Real blocker findings are not cleared by approval alone. They require repair or a future explicit exception workflow with stronger signoff rules.
