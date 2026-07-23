# Branch governance

NICO uses short-lived pull-request branches. The default branch is protected and remains the only canonical production history.

## Required repository settings

- Protect the default branch from deletion and force pushes.
- Require pull requests before merging.
- Resolve review conversations before merging.
- Prefer squash merges for short-lived repair branches.
- Enable **Automatically delete head branches** after pull requests are merged.
- Do not bypass required human review or fail-closed evidence controls.

## Inventory workflow

Run **Branch Governance Inventory** manually from GitHub Actions. The workflow:

1. Fetches all remote branch refs read-only.
2. Reads open pull requests and branch-protection metadata.
3. Measures commits present on each branch but absent from the default branch.
4. Records the most recent commit time.
5. Produces CSV, JSON, Markdown, and a candidate text manifest.
6. Uploads the output as an immutable workflow artifact.

It does **not** delete, update, merge, or create Git refs.

## Classifications

| Classification | Meaning | Automatic deletion allowed? |
|---|---|---:|
| `ACTIVE_DEFAULT` | Canonical default branch | No |
| `OPEN_PR` | Branch is the head of an open pull request | No |
| `PROTECTED_OR_RELEASE` | GitHub protection or a release/recovery naming safeguard applies | No |
| `DEPLOYMENT_OR_RELEASE` | Name indicates production, deployment, recovery, backup, or archive use | No |
| `MERGED_SAFE_TO_DELETE` | Zero commits are absent from the default branch and no exclusion applies | Only after human approval |
| `STALE_WITH_UNMERGED_COMMITS` | Unique commits remain and the branch exceeds the stale threshold | No; inspect manually |
| `MANUAL_REVIEW` | Unique commits remain with recent activity | No; inspect manually |

## Approval-gated cleanup workflow

**Branch Governance Cleanup** always creates a fresh inventory before it processes any branch.

### Dry run

1. Select `dry-run`.
2. Choose a batch size from 1 to 100.
3. Run the workflow.
4. Download and review the retained inventory artifact.
5. Copy the exact manifest SHA-256 shown in the workflow summary.

Dry-run mode has write permission available to the job but the cleanup script never calls the branch-validation or deletion APIs.

### Execute one reviewed batch

1. Confirm the dry-run artifact is acceptable.
2. Rerun the workflow with `execute`.
3. Enter the exact reviewed manifest SHA-256.
4. Enter the exact confirmation phrase: `DELETE REVIEWED MERGED BRANCHES`.
5. Keep the batch size at 100 or lower.

Execution fails closed unless the fresh manifest hash is identical to the reviewed dry run. Immediately before each deletion, the workflow verifies that:

- The branch still exists at the exact inventoried head SHA.
- The branch is not protected.
- The branch has not acquired an open pull request.
- The fresh inventory still classifies it as `MERGED_SAFE_TO_DELETE`.

The workflow uploads a result artifact listing every validated and deleted ref. Regenerate the inventory after each batch before authorizing another one.

## Deletion policy

Deletion requires a reviewed inventory artifact. A branch is eligible only when all of the following are true:

- It is not the default branch.
- It has no open pull request.
- It is not protected.
- It is not identified as a release, deployment, recovery, backup, or archive branch.
- It contains zero commits absent from the current default branch.
- Its exact name appears in the reviewed `safe-delete-branches.txt` manifest.

Delete approved branches in batches of no more than 100. After each batch, regenerate the inventory and verify that open pull requests, deployment refs, and branches containing unique commits are unchanged.

## Branches containing unique commits

Do not combine or delete these branches automatically. Review the diff and intent. Then choose one evidence-backed disposition:

- Preserve the branch as active work.
- Open or retain a pull request.
- Cherry-pick still-valid work onto a clean branch.
- Tag an important historical tip before deletion.
- Record that the work is obsolete and approve deletion.

## Ongoing rule

Every new engineering task should use one bounded branch and one pull request. Once the pull request is merged, GitHub should delete the head branch automatically. Long-lived branches require an explicit documented purpose.
