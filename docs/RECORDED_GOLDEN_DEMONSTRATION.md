# Recorded Synthetic Golden Demonstration

The `Recorded Golden Demonstration` workflow converts the canonical synthetic golden-fixture manifest into bounded JSON and Markdown demonstration artifacts.

The workflow builds the artifacts twice and requires byte-for-byte equality. Each output records source hashes, exact synthetic identities, evidence-state counts, finding and repair-candidate counts, fixture-only score status, review status, delivery status, and the declared coverage dimensions.

## Truth boundary

The demonstration is deterministic and recorded, but it is still synthetic. It does not prove:

- a deployed Express, Mid, or Full assessment succeeded;
- a live repository was scanned;
- a finding exists in production;
- a score is certified;
- a repair was approved or executed;
- a report is client-ready; or
- production delivery is allowed.

Every included fixture must remain non-live, review-required, unapproved, non-client-ready, delivery-blocked, non-certifying, and unable to authorize automatic production changes. Any weakened boundary causes the demonstration build to fail closed.

Authorized live deployment proof remains the responsibility of the manual `Production Assessment Smoke` workflow and separate human evidence review.
