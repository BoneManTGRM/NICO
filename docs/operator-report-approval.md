# Operator approval of an exact NICO report

## Approved design

An authenticated operator may approve an intact completed report while specialist
dispositions, independent QC, and escalations remain outstanding. Operator approval
is a separate receipt on the existing assessment, not a new assessment/product tier.
It never sets specialist `human_review_completed`, creates a legacy accepted
specialist edition, or grants client delivery. The exact reviewed source edition,
source commit, language, review ledger, and approved PDF are cryptographically bound.

The approved PDF has an operator-approval certificate followed by the unmodified
reviewed source pages. The certificate explains the historical draft markers in
those source pages and explicitly discloses outstanding review and QC. This avoids
rewriting a technical finding or falsely claiming completed professional work.

## Implementation and verification plan

1. Add an explicit operator-report decision to the existing authenticated review
   boundary, requiring exact-PDF acknowledgement and optimistic source identity.
2. Persist the operator receipt/package alongside the unchanged specialist state.
   Validate it on reads; source or ledger changes invalidate current approval while
   retaining the historical receipt. Keep localized editions isolated.
3. Project operator and specialist states separately; update Final Review and exact
   navigation, optional metadata, and the bounded technical-record display.
4. Prove the regression and blank/TEST/test matrix, source/ledger/PDF tampering,
   authentication, acknowledgement, stale/duplicate submissions, serialization
   readback, locale isolation, and strict delivery rejection using synthetic tests.
5. Merge only after applicable CI; verify frontend/backend deployments and the
   preserved production run read-only. The owner performs the final real approval.

## Checkpoint

Baseline main: `d8791dc9453aba9cfe1a6fb545d61e441cf6a45e`.
Preserved run: `comprun_7f93ed6903a84f8bee048469fbd4e63a`, last observed revision 64.
No production approval or delivery is authorized merely for implementation tests.
Existing repository pytest/TypeScript/build gates remain the verification surface;
toolchain migration and unrelated production-proof repairs are outside this change.

## Acceptance matrix (implementation checkpoint)

| Requirement | Implementation | Verification | Result |
| --- | --- | --- | --- |
| Optional metadata | Separate operator decision, trimmed optional values; no specialist role assertion | Five metadata cases through real artifact builder; TSX handler cases | Passed locally |
| Exact identity | Optimistic source identity, source-to-approved receipt and manifest; locale isolation | SQLite readback, PDF hashes and source-page text preservation, separate Spanish receipt | Passed locally |
| Outstanding work | Canonical exception-first disclosure; source report and ledger untouched | Pending candidate, QC and escalation fixture; retained specialist state | Passed locally |
| Failure boundaries | Authentication, explicit acknowledgement, source validation, optimistic save | Invalid auth, missing ack, stale run/revision/digest, corrupt/missing PDF, competing writers, failed-stage invalidation | Passed locally |
| Download retry | Retained verified operator edition on authenticated status read | POST then GET without another mutation; frontend download-failure case | Passed locally |
| Delivery | No legacy specialist acceptance/delivery credential issued | Delivery rejected; public status excludes operator PDF | Passed locally |
| Interaction | Run-aware navigation, bounded technical display, separate approval/QC labels | 25 TSX/helper checks; TypeScript and Next production build | Passed locally; production/mobile pending |
| Real owner acceptance | Preserved production run, no fabricated human act | Owner final action and approved bytes | Not performed; owner boundary |

Valid local evidence:
- `.venv/bin/python -m pytest -q tests/test_comprehensive_operator_approval_v1.py --maxfail=1`: exit 0, 16 passed.
- Focused frontend Python suite: exit 0, 28 passed (includes 25 actual TSX/helper cases).
- `apps/web: npm run lint`: exit 0.
- `apps/web: npm run build`: exit 0. Automatic generated tsconfig changes discarded; no toolchain change.
- `git diff --check` and compilation of the three changed backend modules: exit 0.

Independent audit corrected public operator-PDF exposure, localized preparation
identity comparison, and suppression of receipts after canonical report failure.
The existing API/specialist/localized suite also passed: 24 checks, exit 0.
An additional regression reproduced an explicit invalid password falling back to
public draft status (HTTP 200); the corrected authenticated-read boundary returns
403. Its targeted API suite passed: 9 checks, exit 0. Anonymous polling remains available.
CI at `d25b1fe2183ef7aa9d05d42d35709a2803782be2` passed quality and ten test
shards. Two shards each found one superseded frontend source assertion (browser
metadata trimming and specialist-only approval detection). The corrected assertion
files passed locally together: 11 checks, exit 0. No runtime code changed for this
test correction; existing runtime/artifact evidence remains valid.
Current branch: `fix/operator-approved-final-pdf`; PR #1588, not yet integrated.
Next: CI, merge and verify
the deployed frontend/backend identities, then prepare the owner's exact action.
No passwords, cookies, or other credentials are recorded here.

## Production iteration

PR #1588 merged as `906daf806154aa64fb686f24bab11998a14be6f6` with the same
verified tree `3ab8de9eaa1d877687bb20f1ec0518d19f39e52a`. Exact-head NICO CI run
34697477247 passed; the duplicate PR run 34697478822 also completed successfully.
Vercel deployment `dpl_FEvhn8jTuZzz8SY4oDatya1Dbuo2` is READY and serves
`app.nicoaudit.com`; Railway deployment `82eb5f88-2e22-4fe1-a482-44700f464557`
is SUCCESS. Both identify that merged commit.

Live browser inspection showed the new operator/specialist distinction and the
preserved run ID after hydration. It also reproduced one remaining identity loss:
the workflow banner's “Open Final Review” link still omitted the run. The follow-up
uses the existing safe navigation helper for that link, retaining run and edition
without forwarding credential parameters. Its rendered-component regression and
21 affected bilingual/navigation checks passed; TypeScript passed.

Current follow-up branch: `fix/final-review-callout-identity`. Next: integrate this
small navigation correction, verify the final deployments/link, refresh authenticated
report evidence, and hand the exact final action to the owner. No acknowledgement,
operator approval, or client delivery was performed on the preserved run.
