# Report Score Evidence v15

This update improves the numbers in NICO Express reports by improving evidence interpretation, not by hiding risk.

## Targeted sections

- Dependency / Library Ecosystem.
- Secrets Exposure Review.

## Dependency scoring change

Hosted OSV warnings from manifest version ranges such as `>=` are now treated as broad-range warnings, not confirmed installed vulnerable packages. Exact lockfile or audit output is still required before making a final dependency-clean claim.

Expected effect: broad-range-only dependency findings move upward while staying yellow if JavaScript lockfile or audit evidence is missing.

## Secrets scoring change

Masked backend token parameter references, fixtures, and examples are classified as review-only instead of confirmed leaks. Full git-history scanning with gitleaks or trufflehog remains required before claiming full secret-clean status.

Expected effect: backend token variable false positives move upward while staying yellow until real secret-scanner evidence exists.

## Safety rule

The score can improve when false positives are classified correctly, but the report still keeps unavailable evidence visible and requires human review before client-facing delivery.
