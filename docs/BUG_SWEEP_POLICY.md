# Bug Sweep Policy

A repository-wide bug sweep is iterative. Passing tests reduce known risk but do not prove the absence of every defect.

## Required workflow

1. Reproduce or identify a specific contradiction, failure, unsafe default, or missing invariant.
2. Bind the defect to an exact branch head and affected code path.
3. Add focused regression coverage before or with the repair.
4. Preserve authorization, immutable evidence, human review, and client-delivery gates.
5. Run the complete required CI and production-acceptance suite.
6. Merge only when the exact head is green and mergeable.
7. Reassess the deployed path rather than assuming a merged change is active in production.

## Prohibited shortcuts

- No fabricated scanner success.
- No suppression of failed stages merely to reach a terminal state.
- No automatic approval or client delivery.
- No score changes without traceable arithmetic and evidence.
- No broad exception handling that converts unknown failures to success.
- No claim that the system has no remaining defects.
