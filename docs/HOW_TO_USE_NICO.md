# NICO Cybersecurity Specialist Operating Manual

NICO is shipped as an authenticated, specialist-operated Comprehensive technical assessment system. It collects repository evidence at an immutable revision, runs bounded analysis and scanners, generates cross-format reports, preserves unavailable evidence, and requires explicit human review before client delivery.

This production workflow is for an accountable cybersecurity professional. It does not depend on Cody or SARA to run, review, approve, or deliver an assessment.

## Production authority boundary

NICO may:

- acquire authorized read-only repository evidence
- bind the assessment to an exact commit
- run the configured bounded scanner and analysis pipeline
- generate canonical JSON, Markdown, HTML, and PDF artifacts
- create an exception-first technical review queue
- preserve review and delivery certificates for the exact artifact set

NICO may not:

- assess a repository without written authorization
- treat missing evidence as a pass
- modify the client repository
- push code, merge pull requests, or deploy client software
- silently repeat an ambiguous paid intake or human decision
- mark a report client-ready before exact-artifact review and delivery authorization

## Required production configuration

The hosting operator configures these secrets and identities before a specialist receives access:

- `DATABASE_URL`: durable PostgreSQL storage for run and review state
- `NICO_COMPREHENSIVE_OPERATOR_PASSWORD`: the bounded specialist login credential
- `NICO_OPERATOR_SESSION_SIGNING_SECRET`: an independent random secret of at least 32 bytes
- `NICO_ADMIN_TOKEN`: a separate site-administration credential that is not given to the specialist
- `NICO_RELEASE_COMMIT_SHA`: the exact deployed backend commit
- `NICO_FRONTEND_BUILD_COMMIT_SHA`: the exact deployed frontend commit

Optional bounded controls:

- `NICO_SPECIALIST_SESSION_TTL_SECONDS`, default 14,400 seconds
- `NICO_SPECIALIST_LOGIN_LIMIT_PER_MINUTE`, default 10
- `NICO_SPECIALIST_REQUEST_LIMIT_PER_MINUTE`, default 240
- `NICO_SPECIALIST_INTAKE_LIMIT_PER_HOUR`, default 12

`NICO_SARA_OPERATOR_PASSWORD` is retained only as a migration-compatible credential name. New handoffs use `NICO_COMPREHENSIVE_OPERATOR_PASSWORD`. Remove the legacy variable after the specialist credential has been rotated and verified.

The specialist password and session-signing secret must be different. The specialist password must also be different from `NICO_ADMIN_TOKEN`.

## Sign in

1. Open the production NICO site.
2. The root page redirects to **Cybersecurity specialist access**.
3. Enter the private NICO operator password.
4. NICO exchanges the password for a signed, short-lived, HttpOnly, SameSite=Strict session cookie.
5. The password is not stored in the URL, local storage, or session storage.
6. After the session expires, sign in again.

Do not share the specialist password by email, chat, screenshots, or client reports. Rotate it when a specialist leaves the engagement or when exposure is suspected.

## Supported assessment intake

The public site intake is designed for a repository that NICO can acquire through an authorized read-only provider path.

For each engagement, retain:

- client legal or accountable name
- project name
- primary technical contact
- access method
- written authorization and exact authorized scope
- repository identifier
- evidence supplied directly by the client
- requested report language

Never paste a provider token, password, private key, or secret into the browser intake form. Private-provider access must use a server-side read-only credential configured by the hosting operator. The browser must never receive that credential.

## Start a Comprehensive assessment

1. Confirm written authorization covers the exact repository and assessment scope.
2. Sign in to NICO.
3. Open **Comprehensive Assessment**.
4. Select the repository provider and enter the canonical repository URL or identifier.
5. Enter the client and project display names.
6. Complete or explicitly mark unavailable each engagement-context field.
7. Add client-supplied evidence only when its origin and meaning are known.
8. Confirm authorization.
9. Start the assessment once.
10. Record the generated `comprun_...` run ID.

NICO reserves the run identity before provider acquisition. A network timeout during intake can leave the upstream outcome uncertain. Do not start another paid assessment until the exact reserved run ID has been checked.

## Immutable run behavior

A valid run is bound to:

- repository
- exact commit SHA
- run ID
- evidence ledger ID
- customer and project scope
- report language
- engagement metadata digest

Do not replace a run with another revision during review. A new commit requires a new assessment.

The browser stores only the minimum run-recovery identity needed to resume the exact run. Closing the page or losing connectivity does not authorize creating a replacement run.

## Monitor and recover a run

The pipeline advances one bounded stage at a time. Scanner and report stages can take several minutes.

When the browser reports a transport timeout:

1. Keep the exact run ID.
2. Use **Check again** or reopen the exact run.
3. Let the idempotent status read recover durable truth.
4. Do not repeat an intake, continuation, review decision, or delivery authorization merely because the browser timed out.

A run is not deliverable when it is:

- running
- blocked
- failed
- timed out without recovered terminal truth
- missing durable storage proof
- missing final artifacts
- pending human review
- approved but pending separate delivery authorization

## Review scanner and evidence truth

At the terminal review boundary, open the exception-first reviewer queue for the exact run.

The specialist reviews:

- failed scanner executions
- timed-out scanner executions
- unavailable tools or evidence
- secret-exposure candidates
- dependency and vulnerability candidates
- static-analysis candidates
- candidate lineage and deduplication
- evidence limitations
- score and assurance boundaries
- business or stakeholder statements that automation cannot verify

A low or zero review-work count is not automatically a pass. Confirm that the candidate register, scanner execution records, and unavailable-evidence disclosures reconcile with the final report.

## Download the pre-approval report

Before approval:

1. Open **Internal final review** for the exact run.
2. Identify the accountable reviewer and select an authorized cybersecurity reviewer role.
3. Open the exact review package.
4. Download the pre-approval PDF.
5. Verify the PDF opens and the displayed run, repository, commit, language, and artifact digest match the review screen.
6. Read the scorecard, findings, limitations, evidence appendix, and release-provenance page.
7. Confirm the browser-computed PDF digest matches the server-bound digest.

The pre-approval PDF must remain visibly marked as an automated draft pending human approval. It is not a client deliverable.

## Make the human review decision

The specialist has three bounded decisions:

### Approve

Approve only after reviewing the exact downloaded artifact. Approval creates an accepted edition and human-review certificate without changing the technical analysis.

### Request more evidence

Use this when evidence is insufficient. Record a specific reason. The unchanged report cannot later be approved. Start a new assessment with the requested evidence.

### Reject

Use this when the report is not fit for client delivery. Record a specific reason. Rejection remains bound to the exact artifact set.

Every decision must identify the reviewer, reviewer role, time, reason, exact artifact identity, and certificate digest.

## Review the approved final PDF

Approval and delivery authorization are separate.

After approval:

1. Download the generated **APPROVED FINAL** PDF.
2. Verify that its technical content still matches the reviewed report.
3. Verify the appended human-review certificate.
4. Verify the approved PDF digest and accepted-edition manifest digest.
5. Read the approved PDF itself before authorizing delivery.

Approval alone does not permit client delivery.

## Authorize client delivery

Authorize delivery only after reviewing the approved final PDF.

1. Confirm the exact approved PDF digest.
2. Confirm the accepted-edition manifest.
3. Confirm the delivery authorization statement.
4. Explicitly authorize client delivery.
5. Download the certified delivery ZIP.
6. Verify the ZIP opens and contains the expected report and certificate artifacts.
7. Send only the certified package or its approved final PDF to the client.

The delivered package must remain bound to the same repository, commit, run ID, evidence ledger, report language, approved PDF digest, reviewer certificate, and delivery certificate.

## Verify release provenance

Every generated report includes a **NICO Release Provenance** section in canonical JSON, Markdown, HTML, and PDF.

Before paid delivery, verify:

- `deployment_identity_established` is `true`
- `backend_build_commit` is the exact 40-character deployed commit
- `frontend_build_commit` is the exact 40-character deployed commit
- Railway deployment identity is present when supplied by the platform
- report renderer version is present
- OSV-Scanner, Gitleaks, TruffleHog, Semgrep, ESLint, and TypeScript versions are present or explicitly marked unavailable

An unavailable value must remain unavailable. Do not infer a deployment or scanner version from repository history alone.

## Confidentiality rules

Treat all run data and artifacts as client-confidential.

- Use one client and project scope per engagement.
- Do not reuse a run for another client.
- Do not send pre-approval artifacts externally.
- Do not place credentials in evidence fields, notes, filenames, or reports.
- Do not expose run IDs publicly even though a run ID is not sufficient authentication.
- Store written authorization and the final delivered package in the engagement record.
- Follow the client's retention and deletion requirements.

## Specialist handoff checklist

Before handing NICO to a cybersecurity professional, the hosting operator verifies:

- production frontend and backend are deployed from the same approved release
- PostgreSQL durability and container-replacement survival are green
- the specialist login page is the only public entry to assessment operations
- unauthenticated browser and direct-backend requests fail closed
- the specialist password works and does not grant site administration
- the independent session-signing secret is configured
- English and Mexican Spanish assessment routes are gated
- intake, exact-run status, continuation, reports, review, approval, and delivery require authentication
- CodeQL and security checks are green
- the complete CI suite is green
- one non-client smoke run reaches the human-review boundary
- one approved test artifact remains blocked until separate delivery authorization
- the certified ZIP validates after authorization
- release provenance appears in all four report formats
- rollback to the prior release is available

## Paid-engagement acceptance checklist

Do not begin a paid client run until all answers are yes:

1. Is written authorization retained?
2. Is the repository and scope exact?
3. Is read-only provider access working?
4. Is durable storage green?
5. Is the deployed release identity exact?
6. Is the specialist session authenticated?
7. Is the specialist prepared to review every exception and limitation?
8. Is there a secure delivery channel for the approved package?
9. Is the client aware that NICO does not modify or deploy their code?
10. Is rollback available if production verification fails?

## Operational non-goals

The shipped specialist workflow does not require Cody or SARA. It does not use NICO as an autonomous employee, does not permit unattended client delivery, and does not turn automated analysis into professional approval. The accountable cybersecurity specialist remains the reviewer and delivery authorizer.
