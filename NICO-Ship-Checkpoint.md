# September 26 — exact final-PDF availability and authenticated observation

Continue PR1644 and PR1645 through completion; owner explicitly authorizes merging both when ready. All evidence and acceptance requirements below remain. No merge/deployment/approval/client delivery performed.

The actual run comprun_34a469900baa742c0d557f42634b318f is now authenticated in the review UI: revision67, retained report digest f24f7e38ce4c654c8a1c7b55f0d834cc1a03688ae717d695daa0342ba206937c. Its supported review download returned “The completed assessment response did not contain the exact PDF artifact.” Authentication is cleared; actual final PDF recovery and replay are not.

See docs/evidence/pr1645-final-pdf-availability/verification.json. The UI no longer equates retained metadata with an available final PDF. New14 policy cases and full70 frontend handlers passed; TypeScript check passed. Independent full-repository scoped review found no blocking implementation defect, with102 focused Python tests and70 frontend tests passed. This review does not verify actual-input replay, physical iPhone behavior, or native C++ qualification. Older limited-review statements below remain historical.

PR1644 at3cbe702 still awaits terminal run36241917330 evidence and disposition of its retained UBSan result. Final combined integration and hosted verification remain required. No earlier failure or requirement is erased.

---

# NICO — report recovery published; primary continuation conservation completed locally

Continue existing PR1644 and PR1645. All original C0–C19 requirements, source/population/resource/isolation boundaries, historical failures, full applicable independent review and human approval/delivery requirements remain binding. Shipping remains held. No synthetic/local result permits merge or production acceptance.

## Immutable continuity

This report correction starts from c7320fe02c7252bbc824025c0ca048c01b0cba5a / tree8d582b024db08a82e2e655d7329c3fc6cbebb6e5. Preserve its complete [checkpoint and all prior evidence](https://github.com/BoneManTGRM/NICO/blob/c7320fe02c7252bbc824025c0ca048c01b0cba5a/NICO-Ship-Checkpoint.md), including watchdog, primary-page/footer/register conservation, single-composition, security and review dispositions. The C++ branch remains0c8ed5758cfae7ef66eb749655dc2ea9e9fe8c81; preserve its [checkpoint](https://github.com/BoneManTGRM/NICO/blob/0c8ed5758cfae7ef66eb749655dc2ea9e9fe8c81/NICO-Ship-Checkpoint.md) and all frozen native receipts. Main remains312693443b1e70c8a065de2c4e9ca329281d162a. Reconcile this sole shared ledger before integration; no replacement branch or force push.

## Watchdog publication and both CI event types

The previously prepared watchdog repair is committed at c7320fe0. Fresh fault-injection reproduced two failures on unchanged source and39 affected passes after correction, original tests unchanged. Both c732 CI aggregate gates now passed: push36209551628/job108314518137 and PR36209554405/job108314845098. This supersedes the earlier claim that no write operation was available for that patch. It does not prove the sole cause of the exact earlier hosted1.5second failure or the production self-assessment timeout. Preserve the old red push run36198806448 and successful same-head PR run36198809918 separately.

## Primary continuation defect and correction

Wider review reproduced a material remaining case: after retaining a known or unclassified primary section start after the legacy register, v3.9 could discard the next primary page if it referenced a finding and lacked a repeated heading. The same loss occurred after a shared register/primary boundary page. Preserve the primary-tail decision across pages until a new explicit legacy register rederives that state. Existing standalone-card, companion, appendix, duplicate-cover and60page fail-closed behavior remains unchanged. Required content may exceed the budget and fail visibly; it must not be dropped silently.

Twelve identical cases show10 missing-primary failures/2passing reset controls on v3.9, then12passes on v3.10. Seventy-one affected composition/footer/status/CI cases pass, including the twelve; six disjoint real-finalizer/reuse cases pass:77distinct total. All prior test blobs match the branch originals, including22conservation,8real-footer,9primary-reference and existing CI assertions. Real180-finding and80-finding controls preserve findings/source locations and human boundaries. Local scoped dependencies are not hosted parity.

Four synthetic before/after controls restore4→5pages each. All20 resulting pages were rendered and checked for off-page words;16previously retained pages remain identical in extracted text and pixels. Restored English and es-MX heading/footer controls were visually inspected. These are explicitly owned test PDFs, not actual production reports. Exact hashes/commands/disjoint counts are retained in docs/evidence/pr1645-primary-continuation/verification.json.

## Review and actual-input limitations

A read-only independent agent was supplied all five production-change areas of this PDF PR plus required context. Its proposed state/control-flow/provenance findings were withdrawn when contradicted by actual Python semantics and tests. Some inaccurate explanatory wording remained and is not adopted as evidence. The reviewer did not fetch the repository or execute artifacts; full-capability independent approval remains open. Preserve all earlier verified findings and dispositions.

The normal supported status read for comprun_34a469900baa742c0d557f42634b318f again returned401 specialist_authentication_required at2026-09-26T02:03:17Z. Library lookups did not obtain this exact immutable input; unrelated exports are not replacements. The older comprun_29c30048215275ecbac35d179f71a1ed/revision66 remains a distinct NICO self-assessment, not Bitcoin; its separate core decision PDF is not final Comprehensive completion. No protected credential was extracted and no authentication/privacy check was disabled. The previously denied production-record diagnostic and larger-timeout fixture were not rerouted or executed.

## Remaining native and merge gates

Existing C++ full run36207402575 continues to determine the0c8ed575 scheduling policy's qualification. Its owned integration passed; no final native result is claimed here. All required sanitizer/static/fuzz executions, instrumentation and source/result bindings remain mandatory. No manual duplicate, cancellation or timeout relaxation was made by this report correction.

Verify both new-head push and PR suites, terminal native evidence, legitimate actual-input report replay and EN/es-MX inspection, complete applicable independent review, and shared-ledger integration before merge. Production-only gates remain deferred by the shipping hold, not passed. No deployment, production configuration/database/assessment mutation, report approval or client delivery was performed.
