# NICO bounded release execution plan

Status: active for the current Express + Comprehensive release.
Integration branch: `nico-next`.
Production branch: `main`.

## Non-destructive rules

1. Do not delete existing branches, commits, files, features, records, evidence, reports, or customer data.
2. Do not force-push `main` or `nico-next`.
3. Do not create alphabetic batch branches for normal continuation work.
4. Commit all remaining work for this release to `nico-next`, using small reviewable commits.
5. Use one release pull request from `nico-next` to `main` after the complete acceptance gate passes.
6. Emergency production fixes may use a temporary `hotfix/<description>` branch, but must be merged back into both `main` and `nico-next`.
7. A new work item may be added only when tied to a reproducible defect, failed acceptance criterion, security requirement, or explicitly approved product requirement.
8. Every added work item must identify evidence, affected files or subsystem, tests, owner, and release criterion. Open-ended labels such as “next batch” are not sufficient.

## Fixed remaining release scope

The current release ends after the following work packages. These are work packages, not new branches.

### WP-1 — Scanner disposition truth

Status: complete.
Evidence: merged PR #671 at exact head `d5d2c57b2d7bab3f77ba967727c6efe7ff9ad808`; merge commit `57c3ff1409602f591c618cb9d7d611a3f0787f58`; all eight required exact-head workflows passed.

Purpose: complete the work currently represented by PR #671.

Acceptance criteria:
- [x] one canonical disposition exists for each scanner;
- [x] failed, timed-out, unavailable, and unknown scanners cannot be summarized as clean;
- [x] raw candidates are not presented as verified exposures;
- [x] exact-snapshot evidence outranks narrower evidence only when scope is explicitly recorded;
- [x] focused tests and all required exact-head workflows pass.

### WP-2 — Evidence-specific scoring and cross-format parity

Status: in progress.

Purpose: replace blanket score caps with explainable deductions grounded in evidence.

Acceptance criteria:
- [ ] every deduction identifies the triggering evidence and rule;
- [ ] no blanket 74-point cap remains unless explicitly required and documented;
- [ ] canonical score, dashboard, Markdown, HTML, and PDF agree exactly;
- [ ] not-scored controls never contribute numeric points;
- [ ] regression tests cover clean, partial, failed, unavailable, and mixed-evidence cases.

### WP-3 — Client-report compression and professional composition

Purpose: remove repetitive report content without removing immutable evidence.

Acceptance criteria:
- [ ] executive sections are decision-oriented and non-duplicative;
- [ ] findings, actions, roadmap, risks, and resourcing do not repeat the same paragraph under different headings;
- [ ] immutable evidence remains available in the evidence appendix;
- [ ] generated Express and Comprehensive reports contain no placeholders, `None/100`, contradictory status text, or empty decorative sections;
- [ ] visual and content checks pass for Markdown, HTML, and PDF.

### WP-4 — Production Comprehensive provider completion

Purpose: bind every required production capability to exact-SHA evidence without fabricated availability.

Acceptance criteria:
- [ ] each required capability is callable or returns a truthful blocked state;
- [ ] repository snapshot and repository-evidence providers bind to the authorized immutable commit SHA;
- [ ] identity remains stable across run, repository, commit, evidence ledger, customer, and project;
- [ ] missing durable storage or providers fail closed;
- [ ] no client delivery is enabled before required human review.

### WP-5 — Deployment, restart, and end-to-end proof

Purpose: prove the release on the deployed production path.

Acceptance criteria:
- [ ] one authorized Express run and one authorized Comprehensive run complete against exact immutable SHAs;
- [ ] workflow evidence records the exact deployed commit;
- [ ] restart recovery returns the same run identity, revision, and integrity hash;
- [ ] mobile assessment entry is responsive and shows only Express and Comprehensive;
- [ ] generated artifacts pass score parity, scanner truth, content quality, and delivery-gate checks;
- [ ] rollback procedure is documented and tested or dry-run verified.

### WP-6 — Release acceptance and closure

Purpose: establish a clear stopping condition.

Acceptance criteria:
- [ ] all WP-1 through WP-5 criteria are checked with evidence links;
- [ ] all required CI workflows pass on the exact `nico-next` head SHA;
- [ ] no unresolved release-blocking review thread remains;
- [ ] no known P0 or P1 defect remains;
- [ ] P2 defects are either fixed or explicitly deferred with owner and rationale;
- [ ] human reviewer approves the release;
- [ ] one release PR from `nico-next` to `main` is merged using the expected exact head SHA.

## Change-control rule

The fixed scope above may not be expanded silently. Any proposed WP-7 or later item must be recorded before implementation with:

- reproducible evidence or approved requirement;
- severity and customer impact;
- reason it blocks this release rather than a later release;
- precise acceptance criteria;
- estimated files and tests affected;
- explicit approval.

If those fields are absent, defer the item to the next release backlog.

## Required progress report

After each meaningful commit, update the release PR or tracking issue with:

- work package and criterion completed;
- exact commit SHA;
- tests run and results;
- remaining failed criteria;
- newly discovered defects, classified as blocker or deferred;
- confirmation that no new branch was created.

Progress is measured by passed acceptance criteria, not alphabetic batch count or number of commits.
