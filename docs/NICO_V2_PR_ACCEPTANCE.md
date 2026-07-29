# NICO v2 PR acceptance gates

Do not merge this release merely because unit tests pass. The release is accepted only when:

1. A fresh production assessment is created from the deployed commit.
2. Bandit, ESLint, Gitleaks, and TruffleHog each show a normalized state backed by an exact-SHA artifact or a concrete execution failure reason.
3. A findings exit code is not represented as an execution failure.
4. The production PDF contains no duplicate semantic findings or repeated acceptance criteria.
5. The PDF filename contains the approval-state suffix exactly once.
6. A complete package awaiting approval is displayed as `review_required`, never `failed`.
7. Internal review is displayed as required, not awaiting an unstarted stage.
8. JSON, Markdown, PDF, CSV, API status, and UI all expose the same canonical truth SHA-256.
9. The deployed UI successfully copies embedded Markdown on iPhone Safari.
10. A release verifier fails the deployment when any condition above is violated.
