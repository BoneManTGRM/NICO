# NICO High-End Realistic Target Plan

NICO is being upgraded toward the highest realistic service coverage targets for the Malamute-style quote while staying evidence-bound and human-reviewed.

## Coverage targets

| Service area | Target |
|---|---:|
| Express Technical Health Assessment | 90-95% |
| Mid Technical Health Assessment | 75-85% |
| Ongoing Product Engineering Retainer | 55-70% |
| Full client-ready replacement | 75-85% with human review |

These are not claims of 100% automation. Final client delivery still requires human validation, Q&A, stakeholder context, roadmap approval, and resourcing judgment.

## Express upgrades

Hosted Express now aims at the 90-95% target by adding:

- Recursive repository tree profiling
- Deeper text-file inspection
- GitHub commit and PR activity review
- GitHub Actions workflow configuration review
- GitHub Actions run-history summary when accessible
- Dependency manifest parsing
- OSV dependency lookup where exact versions are available
- Secret-pattern review with masked evidence
- Built-in static risk-pattern checks
- Architecture and technical-debt scoring
- Velocity / complexity signal
- Human-review-required flag
- Markdown, HTML, and PDF report output

## Mid upgrades

Hosted Mid workflow now supports the 75-85% target by accepting real evidence for:

- QA / functional review
- Platform parity notes
- Stakeholder discovery notes
- Roadmap notes
- Known risks

It generates:

- Mid maturity signal
- Evidence readiness score
- QA checklist
- Platform parity checklist
- Six-month roadmap draft
- Risk sections and unavailable-data notes
- Markdown and HTML workflow reports

Empty or missing evidence is marked as unavailable. NICO does not invent QA findings or stakeholder conclusions.

## Retainer Ops upgrades

Hosted Retainer Ops now supports the 55-70% target by accepting real operating evidence for:

- Commit summaries
- PR summaries
- Issue / bug summaries
- Blockers
- Release notes
- Roadmap progress

It generates:

- Weekly delivery status
- Evidence readiness score
- Backlog health
- Release readiness
- Monthly strategy signal
- Blocker / approval needs
- Release checklist
- Human approval queue
- Markdown and HTML workflow reports

## Safety and truth rules

- Defensive-only
- Authorized systems only
- Read-only by default
- Human approval for production-impacting actions
- No fake findings
- No placeholder results
- No invented vulnerabilities
- Missing evidence must be marked unavailable
- Final client-ready delivery requires human review

## Hosted endpoints

```text
GET  /health
GET  /targets
POST /assessment/github
POST /assessment/mid
POST /retainer/ops
GET  /assessment/latest
GET  /assessment/mid/latest
GET  /retainer/ops/latest
```

## Test coverage

The high-end service workflow tests cover:

- Authorization blocking
- Mid workflow report generation
- Mid evidence readiness
- Retainer report generation
- Retainer human approval queue

## Frontend sections

`app.nicoaudit.com` now exposes:

- Express Assessment
- Mid Assessment
- Retainer Ops
- Coverage targets
- Evidence-bound results
- Download PDF for Express reports
- Human approval and safety reminders
