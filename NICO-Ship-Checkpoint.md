# NICO — engineering verification only; release held

The owner's current instruction is to finish engineering and verification but NOT ship. Keep PR1644 and PR1645 unmerged and in draft until their evidence and review requirements are satisfied. Do not deploy, enable production workers, start production acceptance assessments, or record human approval/client delivery under this continuation. Release-only acceptance is deferred, not passed.

## Immutable continuity and scope

This remains the sole mission-ledger path. Preserve the complete C0–C19 predicates, review accumulator, source corrections, frozen Bitcoin scope, security/resource boundaries and historical evidence in the immediate [f48e0b28 ledger](https://github.com/BoneManTGRM/NICO/blob/f48e0b28349841980dc7b91eeab19d82dec9f0bf/NICO-Ship-Checkpoint.md), its f4abf2cb/predecessor chain, and the separate [PR1645 ledger](https://github.com/BoneManTGRM/NICO/blob/3a25652b8591d72ce096680d11f46e80912a9dfe/NICO-Ship-Checkpoint.md). Their stronger requirements are not replaced or waived by this checkpoint.

Parent f48e0b28349841980dc7b91eeab19d82dec9f0bf, tree0339af85f8287691624bb8275f0a4da750c6c706, existing branch fix/cpp-runtime-scratch-retention/PR1644. Main312693443b1e70c8a065de2c4e9ca329281d162a and PR1645/head3a25652b8591d72ce096680d11f46e80912a9dfe remain the last verified release/PDF refs. Do not reopen merged PR1641/1643, force push, replace branches or overwrite concurrent changes.

## Pending native work was not protected by cancel-in-progress=false

Observed diagnostic36187313110 is cancelled; qualification36187313096 is pending and preserved qualification36177497388 was still active at the direct read. Both workflow definitions use the same concurrency group and omitted queue. GitHub's documented default replaces an existing pending run even when cancel-in-progress=false. The cancellation is consistent with that configuration; its actor/annotation was not independently retrieved.

This bounded correction adds queue:max to BOTH existing workflows, retaining the same serial concurrency group and cancel-in-progress:false. It changes no workflow triggers, permissions, job bodies, commands, test/context membership, job timeouts, resource limits, image recipes, approval boundaries or production settings. No active run was cancelled and no manual campaign/retry was dispatched. New ordinary PR checks still require verification; a cancelled historical diagnostic remains cancelled and is not relabelled success.

## Exact-source local evidence

The identical three-case selection recorded two failures for absent queue settings and one pass, then three passes after the two configuration additions. The wider six-module command passed204 distinct cases with no failures/errors/skips, including these three. Its first run had202 passes and two setup failures because the scoped local archive had no Git HEAD; a local verification-baseline commit established that prerequisite and the unchanged test selection was rerun. No assertion or timeout was weakened.

Non-concurrency workflow objects are byte-derived and semantically unchanged. All three source/test blob hashes match the tested local bytes. The source archive is a verified scoped f4abf2cb archive; comparison to f48e0b28 shows the exercised inherited modules unchanged. The live diagnostic workflow preimage matches c7c0388635b88d2b27653ffce062511da16a5a6d exactly. This is not full-checkout, pinned hosted, independent-review or native-execution proof. Evidence: docs/evidence/pr1644-native-queue-20260925/verification.json. Python3.13.5 differs from hosted3.11; a pre-existing invalid-escape SyntaxWarning was retained in the RED log.

## Native and PDF gates remain open

Retain complete failed artifact10883294546/ZIP d4933e0120105b8427ebe813cfec2f8487e5d801b980e7cbfbc942adc0ffd41e and all predecessor archives. Its scoped baseline377/377, compiler475/475 and functional6/6 remain valid; ASan376/377 has cluster_linearize_tests timeout300.01s, static474/475 has the generated foo.capnp.proxy-server.c++ context timeout120.063s. Required UBSan/fuzz remain unexecuted in that artifact. No timeout fix or completed native qualification is established by this queue change.

The actual failing PDF run comprun_29c30048215275ecbac35d179f71a1ed/revision66/integrity2bf78b4f47ffda9ba792c509e65e08c5b90a44aacd29456aec84ee1a54b36710 is NICO self-assessment at faaa10b037eb58e4175561b96dadf0d929764df4, NOT Bitcoin. Its renderer-deadline failure and separate36-page decision PDF do not establish final-report completion. Actual-input replay/rendered inspection and applicable independent review remain open. This change does not include or retry the previously rejected report-replay diagnostic publication.

All C0–C19 whole-row states remain as documented in f48e0b28: C1 andC6 pass only their retained frozen scope; C5 andC7 fail on the latest inspected terminal artifact; other rows remain unproven. No production-only predicate is promoted because the owner has chosen not to ship.

## Next engineering dependency

Inspect terminal results of preserved qualification36177497388 and the ordinary successor/isolated workflows. Verify that hosted queue settings are accepted and waiting native work is retained. Diagnose only the remaining measured native failures; preserve all mandatory sanitizer/fuzz/static scope. Obtain actual-input PDF evidence through a supported permitted path and complete independent review. Stop before merge/deployment/production activation; do not call local queue tests or a green PR badge full capability completion.
