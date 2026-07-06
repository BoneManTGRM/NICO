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

## Commercial MVP additions

This phase adds safe commercial foundations without breaking the existing hosted deployment:

- Storage abstraction with in-memory fallback and Postgres-compatible schema
- Safe scanner-worker MVP with asynchronous job IDs and availability checks
- Evidence upload metadata and text-preview handling
- Approval queue with pending / approved / rejected / needs_more_evidence states
- Draft PR request gate that blocks unless an approval item is approved
- Client-ready Markdown / HTML / JSON report package helpers
- Customer role helpers and tenant scoping helpers
- GitHub App architecture stubs for selected-repository read-only install flow

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
- Draft PR creation remains approval-gated and unavailable until write integration is explicitly enabled

## Hosted endpoints

```text
GET  /health
GET  /targets
GET  /storage/schema
POST /assessment/github
POST /assessment/mid
POST /retainer/ops
POST /worker/scan
GET  /worker/scan/{scan_id}
POST /evidence/upload
GET  /evidence/{project_id}
POST /reports/package
GET  /reports/{run_id}
POST /reports/{run_id}/export
GET  /approvals
POST /approvals
POST /approvals/{approval_id}/approve
POST /approvals/{approval_id}/reject
POST /approvals/{approval_id}/needs-more-evidence
POST /github/draft-pr
GET  /github/app/plan
POST /github/app/installations
GET  /assessment/latest
GET  /assessment/mid/latest
GET  /retainer/ops/latest
```

## Test coverage

The high-end service workflow tests cover:

- Authorization blocking
- Scanner worker authorization and job IDs
- Mid workflow report generation
- Mid evidence readiness
- Retainer report generation
- Retainer human approval queue
- Approval blocking before draft PR requests
- Storage fallback and schema availability
- Evidence upload validation
- Tenant scope helpers
- Customer role helpers
- Health and targets endpoints

## Frontend sections

`app.nicoaudit.com` currently exposes:

- Express Assessment
- Mid Assessment
- Retainer Ops
- Coverage targets
- Evidence-bound results
- Download PDF for Express reports
- Human approval and safety reminders

Next frontend pass should expose the new worker, evidence, approvals, reports package, and GitHub App plan endpoints.
