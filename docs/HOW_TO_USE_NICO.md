# How to Use NICO

NICO is an authorized technical assessment, repair-intelligence, QA/parity, and retainer-ops platform. It is designed to collect evidence, explain risk, recommend fixes, and create approval-gated repair workflows. It does not replace human review.

## Golden rules

1. Only use NICO on systems you own or have written permission to assess.
2. Treat every result as evidence-bound, not magic truth.
3. Missing evidence must stay marked as unavailable.
4. Code changes should be suggestions or draft PRs only.
5. Never push directly to main or deploy automatically.
6. Human review is required before client delivery.

## Dashboard

Use the dashboard first to confirm the system is healthy.

Step by step:

1. Open `https://app.nicoaudit.com`.
2. Check Backend Health.
3. Confirm the backend says `ok`.
4. Review target coverage.
5. Check whether Express, Mid, and Retainer workflows have latest runs.
6. Review storage status.
7. If persistence is unavailable, understand that current results may not survive backend restart.

What to look for:

- Backend online
- Target coverage visible
- Storage status visible
- Latest workflow status visible
- No unavailable backend warnings

## Express Assessment

Use Express when a client wants a fast technical health assessment of a repository.

Step by step:

1. Get written authorization from the client.
2. Confirm the repo is owned by the client or explicitly authorized.
3. Enter repository as `owner/repo`, for example `BoneManTGRM/NICO`.
4. Add client name and project name if available.
5. Check the authorization box.
6. Run the Express assessment.
7. Review maturity signal.
8. Review every section:
   - Code Audit
   - Dependency / Library Ecosystem
   - Secrets Exposure Review
   - Static Analysis
   - CI/CD Analysis
   - Architecture & Technical Debt
   - Velocity / Complexity
9. Review unavailable-data notes.
10. Export Markdown, HTML, or PDF.
11. Human-review the final report before sending it to the client.

Good Express output should answer:

- Is the repo healthy?
- Are dependencies risky or unclear?
- Is CI/CD mature?
- Are there obvious architecture/debt risks?
- What should be fixed first?
- What evidence supports each conclusion?

## Scanner Worker

Use the scanner worker when you want deeper technical evidence from tool availability and, later, sandboxed scanner execution.

Current safe MVP behavior:

- Creates a job ID.
- Requires authorization.
- Checks scanner availability.
- Stores status and unavailable notes.
- Does not clone or modify code in this safe MVP phase.

Step by step:

1. Confirm customer authorization.
2. Submit repository, customer ID, project ID, authorized by, and scope.
3. Start worker scan.
4. Copy the returned `scan_id`.
5. Poll `/worker/scan/{scan_id}`.
6. Review scanner results.
7. Treat unavailable tools as missing evidence, not a pass.
8. Use the result in the client report only after human review.

Scanner statuses:

- `queued`: job accepted.
- `running`: job in progress.
- `complete`: job finished.
- `failed`: job failed safely.
- `unavailable`: tool or evidence unavailable.

## Mid Assessment

Use Mid when the client needs QA, platform parity, stakeholder context, and roadmap planning.

Step by step:

1. Collect QA evidence:
   - bug reports
   - screenshots
   - screen recordings
   - crash logs
   - reproduction steps
2. Collect platform parity notes:
   - iOS vs Android
   - web vs mobile
   - feature differences
   - copy differences
   - permission differences
3. Collect stakeholder notes:
   - goals
   - pain points
   - deadlines
   - business risks
4. Collect roadmap notes:
   - near-term fixes
   - medium-term product goals
   - dependencies
   - staffing constraints
5. Add known risks.
6. Run Mid workflow.
7. Review evidence readiness score.
8. Review unavailable-data notes.
9. Review QA checklist and parity checklist.
10. Human-review roadmap before client delivery.

Good Mid output should answer:

- What user flows are risky?
- What platform gaps exist?
- What stakeholder concerns matter?
- What should happen in the next 6 months?
- What evidence is still missing?

## Evidence Uploads

Use evidence uploads to attach client materials to a project/run.

Supported evidence:

- text notes
- markdown
- CSV
- JSON
- PDFs
- PNG/JPEG/WebP images
- MP4 videos

Step by step:

1. Choose customer/project.
2. Choose workflow run if available.
3. Upload evidence file.
4. Check upload response.
5. If text preview is extracted, review it.
6. If file is PDF/media, check unavailable notes.
7. Do not invent conclusions from unreadable files.
8. Attach useful evidence to Mid or report package.

Important limits:

- Files are treated as untrusted input.
- The safe MVP stores metadata and text preview only.
- Private file storage should be configured before retaining full customer uploads.

## Retainer Ops

Use Retainer Ops for ongoing customer support after an initial assessment.

Step by step:

1. Collect weekly delivery evidence:
   - commits
   - PRs
   - issues
   - blockers
   - release notes
   - roadmap progress
2. Run Retainer Ops workflow.
3. Review Weekly Delivery Status.
4. Review Backlog Health.
5. Review Release Readiness.
6. Review Monthly Strategy.
7. Review Blockers / Approval Needs.
8. Export weekly or monthly report.
9. Human-review before sending to client.

Good Retainer output should answer:

- What changed this week?
- What is blocked?
- What is risky?
- What should be fixed next?
- What needs client approval?

## Repair Intelligence

Use Repair Intelligence when NICO finds a problem and you want a safer suggested fix.

Step by step:

1. Start from a finding, failed test, unavailable evidence, or scanner result.
2. Provide the issue description.
3. Attach evidence.
4. List affected files or systems if known.
5. Request repair suggestion.
6. Review suggested strategy.
7. Review risk level.
8. Review test plan.
9. Review rollback plan.
10. If the fix looks appropriate, create an approval item.
11. Only after approval, request a draft PR path.

Good repair suggestions include:

- evidence
- root-cause hypothesis
- affected files
- minimal proposed change
- test plan
- rollback plan
- risk level
- human approval gate

Bad repair behavior:

- editing main directly
- deploying automatically
- claiming untested fixes are verified
- creating PRs without approval
- inventing root cause without evidence

## Approval Queue

Use the approval queue before any code-change workflow.

Step by step:

1. Create approval item.
2. Include requested action.
3. Add evidence.
4. Add affected files or systems.
5. Set risk level.
6. Add test plan.
7. Add rollback plan.
8. Human reviewer approves, rejects, or asks for more evidence.
9. Only approved items can move toward draft PR request.
10. Keep audit trail.

Approval states:

- `pending`: waiting for decision.
- `approved`: human allowed the next step.
- `rejected`: do not proceed.
- `needs_more_evidence`: collect more proof.
- `expired`: old or stale approval.
- `executed`: approved action was completed.

## Draft PR Request

Use this only after approval.

Step by step:

1. Confirm approval item status is `approved`.
2. Confirm requested action is appropriate.
3. Confirm affected files are known.
4. Confirm test plan exists.
5. Confirm rollback plan exists.
6. Request draft PR.
7. In the safe MVP, GitHub write integration remains unavailable and no branch/PR is created.
8. When GitHub write integration is enabled later, NICO should create only a draft branch and draft PR.

Strict policy:

- never push to main
- never auto-merge
- never deploy
- never edit production systems
- never create PRs without approval

## Reports

Use reports to prepare client-ready deliverables.

Step by step:

1. Choose report type:
   - Executive report
   - Technical report
   - Risk register
   - Evidence appendix
   - Roadmap
   - Retainer weekly status
   - Retainer monthly strategy
2. Confirm client name and project name.
3. Confirm repository/source scope.
4. Confirm authorization statement.
5. Include maturity signal.
6. Include evidence readiness.
7. Include findings and risks.
8. Include unavailable-data notes.
9. Include next steps.
10. Export Markdown, HTML, JSON, or PDF where available.
11. Human-review before client delivery.

## GitHub App Plan

Use this when preparing real customer onboarding.

Step by step:

1. Start with read-only permissions.
2. Allow selected repositories only.
3. Do not expose installation tokens to browser.
4. Store installation metadata.
5. Keep write permissions disabled by default.
6. Enable draft PR permissions only after customer approval and implementation review.

Recommended initial permissions:

- metadata read
- contents read
- pull requests read
- issues read
- actions read
- checks read

Optional later permissions:

- contents write for draft repair branches only
- pull requests write for draft PR creation only
- issues write for approval-gated issue creation only

## Customer and tenant controls

Use these controls before working with real customers.

Step by step:

1. Assign each customer a `customer_id`.
2. Assign each project a `project_id`.
3. Scope every repo, report, evidence item, scanner job, and approval item to customer/project.
4. Use roles:
   - owner
   - admin
   - reviewer
   - viewer
5. Only owners/admins should run scans.
6. Only approved reviewers/admins/owners should approve actions.
7. Never mix customer data.

## Recommended real-customer workflow

1. Customer signs authorization.
2. Customer selects repository/project scope.
3. Run Express.
4. Upload QA/client evidence.
5. Run Mid if needed.
6. Create report package.
7. Review findings with client.
8. Create repair suggestions.
9. Add approval queue items.
10. After approval, create draft PR requests.
11. CI runs.
12. Human reviews.
13. Customer merges.
14. Retainer Ops tracks progress weekly/monthly.

## What NICO should sell

NICO should be sold as:

> An authorized technical assessment and repair-intelligence platform that gives clients evidence-backed clarity, risk ranking, repair recommendations, reports, and approval-gated remediation workflows.

Do not sell NICO as:

> A tool that automatically replaces engineers or rewrites production code without review.
