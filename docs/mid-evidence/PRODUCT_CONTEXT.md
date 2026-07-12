# NICO Mid Evidence — Product Context

Status: version-controlled product context for human review. This document defines intended behavior and priorities; it is not direct proof that every implementation path satisfies them.

## Product purpose

NICO provides evidence-bound technical oversight for authorized repositories and related engineering systems. Its primary users are founders, owners, investors, agencies, and technical reviewers who need a plain-language view of what is working, what is risky, what evidence is missing, and what should be repaired next.

## Core product rules

- Assess only systems the operator owns or is explicitly authorized to review.
- Prefer direct repository, scanner, CI, deployment, and test evidence over inference.
- Keep exact-commit code evidence separate from time-window operational history.
- Never represent a scanner that did not run as a clean result.
- Keep missing, failed, timed-out, and human-review evidence states distinct.
- Do not raise a score merely because documentation was supplied.
- Require human review before report approval.
- Require a separately approved artifact before controlled client delivery.
- Keep raw secrets and delivery tokens out of retained evidence and audit records.

## Mid Assessment user outcome

A completed Mid Assessment should provide:

1. one run and one immutable repository snapshot;
2. measured evidence coverage independent of maturity scores;
3. technical section scores only where scoring evidence exists;
4. `NOT SCORED` for unavailable external-context categories;
5. a review-by-exception queue for material findings and evidence gaps;
6. a professional draft report bound to the run and review packet;
7. exact-state approval and a separate approved artifact;
8. controlled delivery with acknowledgement and receipts.

## Current constraints

- External product, stakeholder, and roadmap context requires human validation.
- Native mobile parity is not available without actual native builds.
- A green deployment does not prove functional correctness or security.
- A clean scanner result does not prove the absence of vulnerabilities.
- Existing saved runs remain bound to the evidence and code state captured when they were created.
