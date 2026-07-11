# Unified Mid Assessment workflow

The supported Mid Assessment path is repository-first and uses one `midrun_*` identity from intake through delivery.

## Supported lifecycle

1. `POST /assessment/mid-run`
   - validates explicit authorization and repository access;
   - creates one Mid run ID;
   - captures the exact repository snapshot and commit SHA;
   - runs repository collection, scanner execution, evidence attachment, evidence-bound scoring, and truth-status calculation without generating an Express or Full report.
2. `POST /assessment/mid-run/{run_id}/evidence`
   - accepts the optional external evidence capability issued for that exact run;
   - keeps submitted QA, platform, architecture, stakeholder, and business context separate from direct repository proof;
   - invalidates later approval readiness when the truth model changes.
3. `GET /assessment/mid-run/{run_id}/review-exceptions`
   - collapses clean verified sections;
   - exposes failed tools, unavailable sources, conflicts, high-risk findings, limited conclusions, inference-based context, and material score changes.
4. `POST /assessment/mid-run/{run_id}/report/draft`
   - generates a separate Mid draft bound to the run, snapshot, truth model, review packet, and PDF hash;
   - keeps human review and client delivery mandatory.
5. `POST /assessment/mid-run/{run_id}/approval/request`
   - creates an exact-state approval record;
   - requires every current exception item to be acknowledged before approval;
   - generates a separate approved PDF while retaining the unchanged draft.
6. `POST /assessment/mid-run/{run_id}/delivery/access`
   - creates an expiring, download-limited grant for the exact approved artifact;
   - returns the raw token once and stores only its hash and fingerprint.
7. `POST /assessment/mid-run/delivery/redeem`
   - revalidates the artifact;
   - requires a named recipient and explicit acknowledgement;
   - returns the approved PDF and records an integrity-bound delivery receipt.

## Truth rules

Every section uses one of these statuses:

- Verified
- Verified with limitations
- Unavailable
- Failed
- Human review required

Missing or failed scanner execution is never converted into zero findings. Missing CI runtime evidence is never represented as healthy CI. Missing application/build access is never represented as passed functional QA or platform parity. User-supplied context is never treated as direct repository proof or allowed to change a score without human review.

Evidence coverage is calculated from explicit evidence units for the exact run. It is not a generic accuracy guarantee.

## Legacy migration

`POST /assessment/mid` is deprecated and disabled by default. It returns HTTP `410 Gone`, a successor link to `/assessment/mid-run`, and creates no run or artifact.

Temporary compatibility can be enabled only with the server-side environment variable:

```text
NICO_ENABLE_LEGACY_MID_MANUAL=true
```

Compatibility output remains explicitly labeled as deprecated, non-unified, and not snapshot-bound. It cannot authorize client delivery. The compatibility flag should be removed after dependent clients migrate to `/assessment/mid-run`.
