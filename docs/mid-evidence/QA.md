# NICO Mid Evidence — QA Context

Status: version-controlled QA context for human review. The presence of tests and workflows is not proof that every user path or deployment is correct.

## Automated verification layers

- Python tests under `tests/` cover assessment identity, snapshot binding, scanner evidence, scoring rules, report generation, approval, delivery, and frontend source contracts.
- The Next.js application exposes `npm run lint` through TypeScript checking and `npm run build` for production compilation.
- Scanner workers can execute dependency, secret, static-analysis, test, and build tools when the deployed runtime supports them.
- Vercel and backend deployment status checks provide operational evidence, but deployment success is not equivalent to functional QA.

## Fresh Mid acceptance checks

A current Mid run should verify:

1. One immutable repository snapshot and commit SHA.
2. Dependency manifests plus at least one dependency scanner result or a named unavailable state.
3. Current-tree and full-history secret evidence with explicit coverage limits.
4. Built-in, Bandit, and Semgrep static evidence with material, review-only, and test-only dispositions.
5. CI configuration and observed runtime evidence kept distinct.
6. Complexity evidence bound to the captured snapshot.
7. A complete evidence ledger with no missing-tool state represented as clean.
8. A draft report and approval request tied to the same run, snapshot, truth model, and review packet.
9. No unscored section rendered with an empty `/100` denominator.
10. Mobile evidence details collapsed by default and available on demand.

## Manual QA still required

- Run the hosted Command Center on phone and desktop widths.
- Start a fresh Mid assessment and check status until complete.
- Open the review-by-exception packet.
- Generate and inspect Markdown, HTML, and PDF drafts.
- Verify approved-artifact and controlled-delivery workflows in a non-production test scope.
- Confirm browser session capability handling does not expose raw tokens.

## Platform boundary

NICO currently provides a browser interface. Native iOS and Android parity must remain unavailable unless real native builds or access instructions are supplied. A responsive web page is not evidence of native-platform parity.
