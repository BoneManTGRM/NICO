# NICO — primary-page conservation repair; qualification remains open

Continue existing PR1644 and PR1645. This is engineering work, not merge approval or shipping. Preserve all C0–C19 requirements, immutable source/population binding, resource/isolation limits, retained failures, independent review, and genuine approval/delivery boundaries.

## Immutable continuity

Parent PDF commit: de28b4f5729eae566d15b9295595f09b58a4cf51, tree7587e56e56f4bb112ee699f4d4f4a6bd4671be26. Preserve its entire [checkpoint and predecessor/review chain](https://github.com/BoneManTGRM/NICO/blob/de28b4f5729eae566d15b9295595f09b58a4cf51/NICO-Ship-Checkpoint.md), not just this summary. The runtime branch remains b7a16195e56fc550025fd9e86bcbdb0aa8bdbe85 with its [ledger](https://github.com/BoneManTGRM/NICO/blob/b7a16195e56fc550025fd9e86bcbdb0aa8bdbe85/NICO-Ship-Checkpoint.md) and [latest inspected terminal native evidence](https://github.com/BoneManTGRM/NICO/pull/1644#issuecomment-5840481815). Main remains312693443b1e70c8a065de2c4e9ca329281d162a. Reconcile this single ledger before integration; no replacement PR or force push.

## Newly reproduced and corrected content loss

On v3.8/blob7163098426c5ed02b8104bcacff51a38d621aa61, the final page-wide finding heuristic overrides explicit primary-section recognition or the prior decision to retain an unclassified page after the legacy register. A roadmap/work-package page containing a finding reference can therefore vanish.

V3.9 preserves those earlier primary-page decisions against that final heuristic. Existing footer-only, duplicate cover, appendix, replaced companion, register/approval, and60-page budget rules remain unchanged. Standalone legacy finding cards still get replaced. No finding, score, source population, native command, execution limit, authentication, or approval rule changes.

The identical nine-case selection records8fail/1pass before and9pass after. The29-case affected selection includes those nine; six disjoint real-finalization/reuse cases also pass:35 distinct cases, zero failures/errors/skips. No prior count is added. The two real80-finding controls retain source locations, input immutability and pending-approval state. Four synthetic PDFs restore one missing primary page (3to4pages); all previously retained cover/register/gate pages match visually and in text. Restored EN/es-MX primary pages were inspected and no off-page words found.

Evidence: docs/evidence/pr1645-primary-finding-references-20260925/verification.json. Local scoped Python3.13.5/pytest9.0.2/pypdf5.9.0/reportlab4.4.9 is not full-checkout or pinned hosted parity. The standalone render helper initially lacked PYTHONPATH; it was corrected before before/after rendering, and this setup error is not a behavioral RED. An independent supplied-code critique found the bounded fix sound; its29-case subtotal includes the nine new cases, despite its wording. The reviewer did not execute tests or review the full PR.

## Checks and remaining work

Before this correction, de28 NICO CI36196180741, Security Audit Evidence36196180920 and CodeQL36196180798 passed. This new candidate still requires its own hosted checks. The actual failed self-assessment input has not been replayed; the previously rejected diagnostic has not been rerouted, and the401/private-login handoff boundaries remain unchanged.

PR1644's latest inspected terminal run36187313096 still has baseline377/377, compiler475/475, functional6/6, ASan376/377 and static474/475, with UBSan/fuzz unexecuted. The active full run36188616532 and queued isolated diagnostic36188616676 are unchanged. No native timing/resource correction is claimed here.

C1/C6 retain only their prior scoped passes; C5/C7 retain failed native evidence; remaining incomplete C0–C19 rows stay unproven. Actual native/isolated outcomes, measured fixes, legitimate actual-input PDF replay, rendered verification and complete applicable independent review remain required. Production-only acceptance is deferred by the shipping hold, not passed. No merge, deployment, assessment continuation, database mutation, report approval or client delivery occurs.
