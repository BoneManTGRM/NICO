# Operator approval of an exact NICO report

## Current continuation — one authenticated final action (2026-09-13)

This owner decision supersedes the historical two-interaction descriptions below:
**Approve and download final PDF** records exact-report approval and permission for
that edition together. Two bound receipts remain internal. There is one existing
review acknowledgement, no separate delivery control, and no automatic transmission.

PR #1592, branch `fix/one-action-approval-delivery`, was reconciled at head
`37bf0a636deeb006636378831b7a9a035a6a6ae2`, main
`f549dd2e4ed3f8be1ea2790e903d06f51b640538`. Runtime repair candidate:
`288dba56557c362cb823a2c4faf037cc63d01a21`, exact verified tree
`57361bdf173c306cb52bddd58d2b31b3e25f75c6` (matches locally tested commit
`d7e5160901566b2ef8733f59367d6ffac929f397`). Keep the existing PR draft.

**Not complete.** The prior tool-policy denial for modifying
`tests/test_review_artifact_approval_boundary_v1.py` remains unresolved. No write to
that file was attempted in this continuation. Its two obsolete source-contract
tests still fail; its four API/immutable-artifact checks pass. An independent
technical reviewer inspected the file and specified narrow replacement assertions
in the PR continuation. That technical review does not override tool policy.
No supported policy-resolution capability was exposed in this session.

The owner target is `comprun_490d6d5686053f9eb1036368f4c7fa21`, source edition / EN.
Source revision 55 and assessed commit `f549dd2e4ed3f8be1ea2790e903d06f51b640538`
are supplied screenshot observations, not fresh authenticated evidence. Do not use
the older run in the historical sections below. The secure browser sign-in attempt
returned `submission_failed`; the target record, receipts and PDF remain unverified.
No credential was extracted or copied and no production mutation was performed.

Production frontend and backend were both independently observed at main `f549dd2`:
Vercel `dpl_AzyAro6wZqVGGx7CXSavmMay5TXf`, READY, alias `app.nicoaudit.com`;
Railway `4b198570-42a7-48e7-be91-4d93bd808923`, SUCCESS. These releases contain
PR #1591's two-step UI. No merge, deployment, replacement assessment, approval,
permission or client transmission was performed by this continuation.

### Focused repairs and evidence

CI reconciliation, 2026-09-13: at `a20d644`, NICO CI run 34757873382 passed
quality and 11/12 shards. Shard 10 failed only the two unchanged obsolete
approval-boundary assertions. Security Audit 34757874575 additionally blocked one
unverified RailwayApp candidate: the deployment identifier documented above.
Its raw-value SHA-256 `583d7cd14d26cb9df88cbd31b72a31873c25f050af9988d8190617889d46f9cb`
matches fresh Railway deployment metadata for the successful `f549dd2` release.
The existing classifier now recognizes that exact digest only for RailwayApp in
this document; verified secrets and other values/paths/detectors still block.
All 13 gate tests pass, including adversarial checks for both known identifiers.
Re-evaluating the unchanged downloaded audit evidence passes with all 45
TruffleHog findings retained (3 exact nonsecret-identifier occurrences). ZIP hash:
`2a04ea877bbe393513727b853c50f59c5fd4e56ddeaceba90a85cf7cdb95c33a`.
Independent scoped review found no blocking issue. This re-evaluation is not a new
CI run or production proof; final-head checks remain required. The browser still
showed sign-in, and no target-report mutation was performed.

The workspace reconciles ambiguous mutation outcomes using the same authenticated
run/edition before any repeat POST. Persisted approval is reused; persisted delivery
permission leads to download-only recovery. Receipt canonical SHA-256, parent
approval, original manifest, returned run/digests and selected language are checked.
Late selection responses are rejected. The source read for Spanish preparation
remains valid without authorizing the Spanish edition. Operator labels explicitly
identify the operator decision and preserve specialist/QC truth.

The existing iPhone handoff retains its synchronous window until action completion,
closes unused windows on failure, and reports popup/presentation failures without
discarding permission. It no longer expires independently after 60 seconds.

Local environment: Python 3.12, repository-pinned Python/frontend dependencies.
CI uses Python 3.11; no CI result is inferred from this local evidence.

- `node --test tests/frontend/final_review_approval.test.cjs`: exit 0, 53 passed,
  none skipped. Real TSX and composed handoff, isolated React/DOM/network fixtures.
- Focused Python frontend suite (handoff, hydration, handler collection, workspace,
  independent metadata): exit 0, 28 passed; invokes the actual Node suite.
- Four backend suites (operator approval, presentation, delivery, localized edition):
  all 37 cases passed in the 65-case affected run. That run exited 1 for one obsolete
  frontend source assertion; the corrected frontend suite subsequently passed.
- Protected approval-boundary file: exit 1, 2 obsolete source assertions failed,
  4 API/immutable-artifact cases passed. It is unchanged.
- `npm run lint`, final `npm run build`, and `git diff --check`: exit 0.
- Independent read-only technical review reproduced response-loss, receipt-binding
  and handoff-timing defects, reviewed the fixes, and closed its substantiated
  findings. This is implementation review, not specialist assessment review.

### Requirement-to-evidence matrix

| AC | Implementation/evidence | Current result and limitation |
| --- | --- | --- |
| 1 | Combined handler; one acknowledgement; only authorized bytes presented | Isolated EN/es-MX pass; production pending |
| 2 | Existing approval reuse and no additional acknowledgement | Fixture pass; owner's target not authenticated |
| 3 | Authenticated reconciliation, receipt checks, reload tests; backend readback | Fixture/API pass; production receipts unknown |
| 4 | Real SHA-256, exact run/digests, source and parent binding | Fixture/API pass; actual final PDF hash unknown |
| 5 | Operator Approved / delivery Authorized; retained backend lifecycle rendering | Local pass; actual PDF/cover not inspected |
| 6 | No backend/source/ledger edits; existing preservation tests | Backend pass; no production mutation or comparison |
| 7 | Missing auth/ack, stale/corrupt/wrong-parent/run/edition responses rejected | Behavioral/API pass; two old contract tests unresolved |
| 8 | Duplicate ref, persisted-state reads after response loss; download recovery | Reordering fixtures pass; concurrent browser proof pending |
| 9 | EN/es-MX actions, isolated edition identity, source-to-Spanish preparation | Behavioral/backend pass; production editions pending |
| 10 | Synchronous handoff composed with handler; explicit failure cleanup | Mocked iPhone surface only; real Chromium/WebKit/iPhone unverified |
| 11 | Existing authenticated endpoints; no transmission added; backend exposure tests | Local pass; no production mutation/transmission occurred |
| 12 | Existing PR retained; current deployed identities read | Blocked before integration; no production acceptance |

Iteration results: **minimal case** reproduced saved-approval/response-loss and
wrong-parent/wrong-run false success; **fixed conditions** retained the same fixture
source and initial lifecycle without rerunning an assessment; **critique** used the
independent technical reviewer and repaired its substantiated findings;
**reordering** exercised duplicate taps, lost responses, unavailable reconciliation,
late selection, approved source then Spanish preparation, reload, and handoff timing.
The strongest browser results are composed fixture tests, not browser emulation
or physical-device proof.

Next unresolved action: resolve the denied test-edit boundary and replace only the
two obsolete source-contract functions with the reviewed combined-action contract,
leaving API and immutable-artifact tests unchanged. Then require final-head CI,
merge/deploy through existing infrastructure, authenticate the exact target, and
verify receipts, actual authorized PDF/provenance/cover, reload and real browsers.
Do not reapprove a valid report or infer target receipt identities from fixtures.

## Historical implementation and evidence

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
