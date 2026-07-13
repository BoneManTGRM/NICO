# Hosted Smoke Tier Proof

The hosted smoke gate requires a passing `production_assessment_smoke` artifact before it can report full readiness.

The accepted artifact must be produced by the authorized production assessment smoke runner and must prove:

- the evidence is an authorized live deployment run, not a synthetic fixture;
- repository authorization was explicitly confirmed;
- Express, Mid, and Full are all present and passed;
- each tier issued exactly one start request;
- Mid and Full retained a non-empty exact run ID;
- Mid and Full polled only the status route for that exact run;
- human review remained required for every tier; and
- no tier claimed to be client-ready.

A missing tier, duplicate start, changed continuation identity, synthetic artifact, absent authorization, or weakened review boundary fails the hosted smoke gate. The artifact remains deployment evidence only; it does not certify scanner completeness, report correctness, security, or client-delivery approval.
