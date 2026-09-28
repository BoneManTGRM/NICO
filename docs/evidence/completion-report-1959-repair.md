# Completion report #1959 repair

Failure: GitHub Actions run 36481802955, job 109128984712, on
4ca111c0e1dc837158c69c0d6fc3056be75f9c89. Source acceptance artifact
10997013214 contains the 48-page report for
comprun_41b8b5f15484a0cfbdaa0c67922e7e69, assessed GitLab commit
ddd0f15ae83993f5cb66a927a28673882e99100b.

The binder required underscore field names, while the PDF rendered `Score effect:
None`, `Technical score effect: None`, `not actionable=0`, and `needs review=0`.
The parser now accepts both representations. Candidate-review `assurance-only`
narrative is neither positive proof of numeric-score separation nor a conflict;
explicit non-none numeric score effects still fail, including mixed legacy/current
representations.

The Spanish production proof filled a configurable repository field but supplied
fixed NICO/GitHub access and scope metadata. Fresh and retained-run proof paths now
configure these fields from the explicit target. The scope names the selected
snapshot rather than assuming a main branch. Canonical report identity is checked
against that target. Existing retained artifacts are not rewritten or reauthorized.

The completion binder now requires the source canonical JSON and checks its
repository and assessed commit against acceptance and structured audit evidence.
Both identity and engagement metadata must name the matching repository/provider,
and the PDF must retain those scope and access values. A stale source cannot pass
merely because the label parsing is repaired.

Verification:
- Seven new label cases reproduced failures before the parser change.
- The original PDF now passes the complete label/triage extraction contract.
- The original canonical JSON/PDF pair fails with `Completion report authorized
  scope repository mismatch`, as required.
- Focused tests cover legacy/current labels, conflicting effects, provider-bound
  scope, sequential target changes, stale metadata, PDF parity, binder subprocess
  output without application startup, and fresh/recovery proof entrypoints.

A fresh production proof and completion package are required after deployment.
The old report remains historical evidence and is not a corrected deliverable.
