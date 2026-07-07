# Guided Workflow v12

This update adds a plain-language NICO workflow page at `/guided-workflow`.

## Purpose

NICO had strong backend workflows, but users still had to understand paste boxes, endpoints, report packages, scanners, approvals, and repair suggestions. The guided page explains the clean order of operations.

## Recommended client workflow

1. Start a job.
2. Confirm authorization.
3. Add the target repository.
4. Collect evidence.
5. Run Scanner Worker when possible.
6. Run Express.
7. Review findings and unavailable evidence.
8. Create repair suggestions only for real findings.
9. Build a client package.
10. Export and human-review before client delivery.

## Job modes shown

- Quick repo health check.
- Client Express assessment.
- Repair failed check.
- Retainer project.

## Evidence cards shown

- Repository.
- Authorization.
- Scanner result.
- Express result.
- Repair notes.
- Client package.

## Safety rule

The page keeps the rule that scores are not the final answer. Client delivery still requires human review, clear authorization, and review of unavailable evidence.
