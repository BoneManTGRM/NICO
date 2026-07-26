# NICO Comprehensive Maturity Metrics

Targets in this file are release gates, not current marketing claims.

## Measurement rules

A maturity metric is valid only when:

1. Its numerator and denominator are explicit.
2. The benchmark corpus and version are recorded.
3. Success and failure cases are included.
4. Measurement is produced automatically.
5. The same target is met on three consecutive complete runs.
6. Runs start from a clean documented environment.
7. Required checks are green.
8. Evidence artifacts are retained with checksums.
9. No unresolved Critical or High benchmark regression remains.
10. Exclusions are documented and cannot be used to manipulate the result.

Manual client-only context, stakeholder interviews, unavailable third-party evidence, and decisions intentionally reserved for humans must be reported separately rather than removed silently or counted as automation failures.

## Target metrics

### Evidence collection and normalization

- Target: **98%**
- Numerator: standard evidence items automatically collected, validated, tied to the immutable baseline, and normalized successfully.
- Denominator: all standard evidence items technically collectable through configured integrations for the benchmark scope.
- Failure conditions: wrong commit, missing provenance, failed validation, malformed normalization, silent tool omission, or unavailable required evidence represented as complete.

### Repeatable technical analysis

- Minimum target: **95%**
- Goal: **98%**
- Numerator: benchmark repeatable-analysis tasks completed automatically with accepted evidence and expected output classification.
- Denominator: repeatable repository, dependency, architecture, CI/CD, quality, security, testing, reliability, and maturity tasks applicable to the benchmark.
- Exclusion: professional judgment intentionally reserved for humans.

### Finding and recommendation preparation

- Target: **95%**
- Numerator: material benchmark findings entering human review with traceable evidence, severity recommendation, confidence, evidence strength, business impact, remediation guidance, acceptance criteria, verification procedure, and residual risk.
- Denominator: all material benchmark findings expected by the approved answer manifest.

### Report production

- Target: **99%**
- Numerator: required delivery sections and artifacts produced from canonical data without manual copy-and-paste assembly.
- Denominator: all required sections and artifacts for the benchmark engagement.

### Cross-format invariant compliance

- Target: **99.5%** across benchmark checks; **100% required for each deliverable release**.
- Numerator: passing canonical identity, score, severity, count, finality, roadmap, evidence, and delivery-state invariant checks.
- Denominator: all applicable invariant checks.
- Delivery rule: any known failed invariant blocks delivery regardless of aggregate percentage.

### Material claim evidence support

- Target: **100%**
- Numerator: material factual claims supported by traceable evidence or explicitly classified as inference, limitation, or client-provided context.
- Denominator: all material factual claims in all client-facing artifacts.

### Remediation planning

- Target: **95%**
- Numerator: material findings with implementation-ready plans before human review.
- Denominator: all material findings requiring remediation.

### Routine case progression

- Target: **95%**
- Numerator: applicable routine transitions, evidence requests, scanner starts, retries, report generation, quality checks, status updates, and next actions prepared or executed automatically and correctly.
- Denominator: all routine progression actions in the benchmark engagement.

### Continuing assurance

- Target: **95%**
- Numerator: applicable baseline comparisons and material delta analyses completed automatically with correct escalation behavior.
- Denominator: all routine monitoring and delta-analysis tasks in the benchmark.

### Eligible controlled patch development

- Target: **80%**
- Numerator: eligible low-to-moderate-risk benchmark repairs for which NICO creates a correct specification, branch, patch, tests, draft pull request, reviewer packet, and verification evidence without manual implementation.
- Denominator: benchmark repairs classified as eligible under the risk policy.
- Exclusion: protected high-risk changes requiring explicit human implementation or approval.

## Human-time targets

After functional maturity is proven:

- Standard engagement: **8–16 total human review hours**.
- Complex engagement: **16–30 total human review hours**.
- Routine continuing assurance: **1–3 human hours per client per month**.
- Manual report assembly: near zero.
- Manual evidence reconciliation: exception only.

Time measurement must distinguish review, client discovery, technical judgment, rework caused by NICO, and unrelated administrative time.

## Benchmark corpus contract

The versioned corpus must include:

- clean repository;
- known application vulnerabilities;
- authorization defects;
- dependency vulnerabilities;
- synthetic leaked test secrets;
- weak CI/CD;
- insufficient tests;
- architecture problems;
- incomplete evidence;
- required scanner failure;
- conflicting scanner conclusions;
- multiple repositories;
- large repository;
- previously assessed repository with controlled changes;
- slow analyzer;
- timeout and retry;
- partial persistence or queue interruption;
- cross-tenant access attempts;
- report score or finality drift;
- eligible remediation patches;
- protected remediation changes that must stop for approval.

Each seeded issue requires a stable expected-answer manifest covering detection, evidence, severity range, expected limitations, duplicate grouping, remediation, and verification.

## Historical results

No target in this file is currently recorded as achieved. Populate this section only from retained automated benchmark evidence.
