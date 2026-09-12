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

PR #1589 head `8df90b39427e511b6081b286928128ee11826b36` passed NICO CI
34698179296. Security Audit 34698192550 found one unverified RailwayApp candidate:
the deployment UUID recorded above. The raw candidate matched Railway's verified
deployment metadata, not a credential. A classification restricted to that exact
value hash, documentation path and detector retains the finding as a nonsecret
deployment identifier; verified values and other candidates still block. Twelve
security-gate tests passed, including those adversarial boundaries. Re-evaluating
the original scanner artifacts with the corrected classification passed without
rerunning scanners or changing their evidence. Final-head CI remains required.

A fresh authenticated draft download after #1588 deployment was 1,777,625 bytes,
SHA-256 `5af1750787ce9d4fc637c0dfb8ac1f4f9534696f3006df34a1c9871b3f7983c6`.
The browser's download-event observation timed out, but the actual downloaded file
was present and independently hashed. Download enabled the unchecked report
acknowledgement; the approval button stayed disabled. No approval was submitted.

## Approved presentation correction

The owner subsequently approved source revision 64, producing stored revision 65.
The real certificate and approved PDF were verified in production; the complete
identities and acceptance evidence are retained in PR #1589. That implementation
preserved all source pages behind a certificate, leaving the blue cover and report
headers visibly marked pending/draft. The owner's screenshots demonstrate this
remaining presentation defect; the earlier successful byte-binding checks did
not establish consistent lifecycle wording.

Branch `fix/operator-pdf-lifecycle` corrects only the approved PDF presentation.
The blue card becomes “Operator approval: Approved”; client delivery stays blocked.
Headers and the exact-approval table identify the recorded operator decision.
Specialist dispositions, QC, and risk acceptance stay incomplete where recorded.

The stored source package, original approval receipt, certified export, ledger,
revision, and audit history remain unchanged. An authenticated read derives a
deterministic presentation with its own schema and manifest, explicitly bound to
the original approval manifest, receipt, original approved PDF and reviewed source
PDF. The original receipt's approved-artifact digests continue to identify the
original certified export; the rendered manifest binds the corrected PDF. This is
not a new human approval. Existing approvals need only refresh/download, and locale
preparation uses the currently presented artifact identity while its parent binding
continues to identify the immutable original source approval.

Verification: 21 backend operator/presentation checks, 26 frontend checks and
TypeScript passed. A local rendering of the preserved source PDF retained all 45
pages and every non-text drawing operation, retained pending candidate-disposition
mentions, and removed stale draft headers. The blue cover was visually inspected.
Source/receipt tampering still invalidates operator approval. No scanner or owner
approval was rerun. Final CI, deployment and live corrected-PDF verification remain
pending at this checkpoint. The complete API rendering derivation is available in
the authenticated response; a bounded identity summary is shown in Technical review
record. No delivery authority is issued.


## Explicit client permission extension (current work)

The owner subsequently requested that tapping client approval change Blocked too.
The new explicit `delivery_kind=operator_report` action permits client release of
an intact, current operator-approved report with its disclosed unfinished work.
It does not certify completed specialist review/QC and does not send any report.
The previous specialist delivery path keeps its own rules. Operator report approval
alone still cannot authorize delivery.

The existing authenticated authorize-delivery endpoint accepts this bounded action
for source and separately approved locale editions. It requires explicit delivery
acknowledgement and the identity of the downloaded approved PDF. Optional metadata
remains optional. A separate immutable permission receipt and authorized PDF are
saved on the same run; optimistic revision protection prevents conflicting writes.
Identical retries reuse the receipt. The original assessment, operator approval,
source artifacts and specialist ledgers remain retained unchanged.

Final Review exposes the delivery acknowledgement and action after operator approval.
After a validated successful response, the screen shows Client delivery: Authorized
and downloads the corresponding hash-verified PDF. Its blue cover and lifecycle
headers also say Authorized. If downloading fails after permission persists, the
screen preserves that status and provides download-only retry. A stale identity,
invalid password, absent acknowledgement, corrupt artifact, or pending HTTP 200
response cannot create an authorized report.

Continuation: branch `fix/operator-client-authorization`, baseline
`b1841478b0db880074481e83c1fd1a36322a44c1`. The owner run remains at the previously
verified approval of source revision 64 (stored revision 65). This implementation
work does not itself submit the owner's client-delivery acknowledgement. Complete
CI/integration/deployment and inspect the real action before returning it to the
owner. The PR description will record final SHA/deployment evidence and any remaining
human action. Never rerun the assessment to test this transition.

Local extension evidence: 9 new backend authorization checks passed, including
authentication, optional metadata, stale identities, readback, idempotency, PDF
integrity, bilingual cover labels and isolated Spanish permission. The 41 affected
existing approval/presentation/controller/record/locale checks passed. All 29
frontend checks and TypeScript passed. A clearly labeled local rendering of the
retained source visually showed Approved / Authorized without changing scores.
This rendering is synthetic verification, not a production delivery receipt.
