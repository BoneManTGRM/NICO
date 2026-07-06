# NICO Super User-Friendly Workflow Plan

Goal: make NICO usable without understanding every backend endpoint, paste box, or report format.

## Current usability problem

Express is understandable because it has one clear input: repository plus authorization. The rest of NICO still feels like disconnected paste boxes: Scanner Worker, Reports, Client Job Mode, Repair Intelligence, Approvals, runtime config, and exports.

## New product model

Replace disconnected sections with one guided workflow:

1. Start a job
2. Confirm authorization
3. Add target repository
4. Run Scanner Worker
5. Run Express
6. Review findings
7. Create repair plan
8. Create client package
9. Export report
10. Human signoff

## Main dashboard layout

### 1. Start Here

A single card that asks:

- What are you doing?
  - Quick repo health check
  - Client Express assessment
  - Full client package
  - Repair a failed check
  - Monitor retainer project

NICO should then show only the fields needed for that task.

### 2. Guided Job Wizard

A stepper UI:

- Step 1: Scope
- Step 2: Authorization
- Step 3: Evidence
- Step 4: Scan
- Step 5: Express assessment
- Step 6: Repair recommendations
- Step 7: Client package
- Step 8: Export and signoff

Each step should show:

- what it does
- why it matters
- what to paste or upload
- what can go wrong
- whether it is required or optional

### 3. Replace Paste Boxes With Labeled Evidence Cards

Current paste boxes should become evidence cards:

- Repository URL
- Authorization statement
- Client notes
- CI/CD logs
- Quote or scope
- Product artifact
- Manual QA notes
- Human review notes

Each card should have examples and accepted formats.

### 4. Clear Status Language

Use plain labels:

- Not started
- Needs authorization
- Running
- Evidence missing
- Needs repair
- Ready for human review
- Client-ready after signoff

Avoid making users interpret internal statuses like `gray`, `blocked`, `unavailable`, or raw JSON unless they expand advanced mode.

### 5. One Final Action Button Per Step

Each step should have only one primary action:

- Save scope
- Confirm authorization
- Run scanner
- Run Express
- Generate repairs
- Build package
- Export report

Secondary/debug actions should move under Advanced.

## Reports UX

Report export should have clear choices:

- Client PDF
- Technical Markdown
- HTML preview
- JSON evidence package

Each export should say whether it is:

- Draft
- Human-review required
- Client-ready after signoff

## Repair UX

When NICO finds issues, it should show:

- Finding
- Evidence
- Why it matters
- Suggested fix
- Risk of fix
- Test plan
- Rollback plan
- Create repair PR button

NICO should not hide missing evidence and should not auto-merge production changes.

## Immediate implementation order

1. Fix report correctness and obvious false positives.
2. Add a Start Here / Guided Workflow page.
3. Add a Client Package Builder page using `/client-job/package` and `/client-job/export`.
4. Add upload-style evidence cards.
5. Add final signoff screen.

## Non-negotiable safety rules

- Authorized systems only.
- No browser-exposed credentials.
- Missing evidence remains visible.
- Reports are drafts until human review.
- Production-impacting repairs require approval.
