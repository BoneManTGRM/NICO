# NICO Easy Mode Workflow

Goal: make every major NICO section feel as simple as Express while keeping evidence-bound scoring.

## Principle

Each workflow should follow the same user pattern:

1. Confirm authorization.
2. Reuse repository, client, project, customer, and project IDs.
3. Click one primary action.
4. Review evidence, findings, unavailable notes, and human-review gates.
5. Export or approve only after evidence is complete.

## Why this matters

The Bernardo/Malamute quote describes three service layers:

- Express Technical Health Assessment: a two-week technical health assessment.
- Mid Technical Health Assessment: a six-week workflow adding QA, platform parity, stakeholder discovery, and roadmap planning.
- Ongoing Product Engineering Retainer: recurring product engineering operations, release, backlog, roadmap, and approval workflows.

NICO already has these workflow concepts. The product gap is ease of use: Express is repository-first, while Mid and Retainer still require more manual evidence text. Easy Mode closes that gap by seeding structured prompts from existing Express evidence without pretending that seeded prompts are verified proof.

## Current implementation

`GET /service-catalog/easy-mode`

Returns workflow cards for Express, Scanner Worker, Mid, Retainer, and Reports. Each card explains:

- target coverage
- minimum inputs
- one-click goal
- workflow steps
- evidence guardrails

`POST /service-catalog/easy-mode/intake`

Accepts existing Express/report evidence and returns structured prefill text for:

- Mid QA evidence
- Mid parity notes
- Mid stakeholder notes
- Mid roadmap notes
- Mid known risks
- Retainer commit summary
- Retainer PR summary
- Retainer issue summary
- Retainer blockers
- Retainer release notes
- Retainer roadmap notes

This is not proof. It is a guided intake seed. The user still needs to attach real QA, parity, stakeholder, release, and operating evidence for stronger scores.

## Next updates

1. Frontend Easy Mode panel
   - Add a single Easy Mode panel above all workflow sections.
   - Show the workflow cards from `/service-catalog/easy-mode`.
   - Add buttons: Run Express, Seed Mid/Retainer, Run Scanner, Create Report.

2. One-click full workflow orchestration
   - Add a backend endpoint that can run Express, seed Mid/Retainer, create a report package, and show final-review gates from one request.
   - Keep scanner execution asynchronous where needed.

3. Evidence upload by section
   - Add upload slots for QA screenshots, parity matrices, stakeholder notes, roadmap docs, release notes, and CI artifacts.
   - Map each upload to a workflow section automatically.

4. Per-section readiness meters
   - Show what is missing before the user runs a workflow.
   - Example: Mid parity is missing platform walkthrough proof; Retainer release readiness is missing smoke-test evidence.

5. Final-review/client-acceptance buttons
   - Put final-review and client-acceptance actions beside report package output.
   - Do not allow client-ready status until those gates pass.

## Guardrails

- Do not invent evidence.
- Do not mark seeded intake as verified proof.
- Do not hide unavailable evidence.
- Do not raise scores unless real artifacts support the lift.
- Keep human review required before client delivery.
