# Ordinary PDF investigation reason disclosure

Base: d3f1f5ae40bbe42c2c9ff20dcb72f46b5950a26d.

## Confirmed defects and bounded repair

The existing PDF disclosure called `display_investigation` with display-normalized identity. A source-bound register using default customer/project IDs lost its reason disclosure when cleanup replaced those IDs with `Not supplied`; the original aggregate investigation summary could still render because it used a different, explicitly retained-summary path. A before-fix reproduction confirmed detail present before cleanup and absent afterward. In addition, the renderer never emitted the coarse unresolved-reason counts.

Identity cleanup now preserves an original canonical five-field scope for candidate report disclosure before display normalization. The renderer validates its exact projection against current identity, then still validates the full register and every packet fingerprint. It never takes authority from the packet's self-declared scope. An older producer's valid measurement-report identity context may supply the same original canonical identity, but only through its existing independent validator. Malformed explicit candidate context cannot fall back. Already-normalized historical data lacking producer context remains unavailable, not guessed or rewritten.

Spanish rendering changes the authored missing display label to `No proporcionado`. Only the explicit Spanish projection may normalize that exact label back to `Not supplied` for identity validation. Actual customer/project identifiers, repository, run and commit are never translated or relaxed.

The ordinary PDF now includes validated unresolved totals, coarse closed-code reason counts, and a separately labelled subset of source-availability counts. Unknown/stale/malformed scope or fingerprints withhold counts and show an unavailable explanation. Raw reason text, source paths and scanner payloads are not copied into these disclosures. No investigation is launched while rendering. Scores, dispositions, budgets and approval/delivery controls are unchanged.

## Regression evidence

Tests use synthetic evidence and a synthetic run ID with the current commit and default customer/project shape. The full installed EN and es-MX PDF route retains 1,681 candidates, 899 completed bounded analyses and 782 unresolved: 595 source parsing unavailable (590 observed output-limit, 5 unretained), 68 identity mismatch, 44 ambiguous, 35 specialist, 24 unsupported/missing evidence and 16 line mismatch. Assertions inspect actual extracted final PDF text and validate exact artifact hashes, input nonmutation and human/client-delivery gates. This is a production-shaped regression, not a replay or modification of any historical assessment.

Additional tests cover every scope field in the display context, producer context and packet; malformed context; stale candidate fingerprints; legacy absence; producer measurement-context compatibility; Spanish missing-label parity; and foreign customer rejection.

## Separate output-limit proposal, not activated

Current capture retains supported AST statement/call observations for the entire parsed file. The investigator reads the candidate's exact line, binding and source hash. A potential bounded improvement is a versioned observation projection retaining the union of all safely validated candidate lines for each file, with explicit requested-line coverage and exact file identity. This must not omit candidates, interpret unretained lines as empty code, or create a second capture/budget. It requires consumer review, capped-inventory and unsupported-rule handling, and whole-population equivalence under the existing aggregate limits before implementation.

A synthetic file with 1,000 unrelated assignments showed no savings: the current parser already omits those statements. A separate 9,017-byte file with 1,000 unrelated calls and one candidate assertion produced 128,150 observation bytes; a candidate-line-only experimental view was 366 bytes and gave the identical result for that one selected candidate. This does not establish production coverage gains or correctness for the full candidate population. No selection/retention algorithm changes are in this patch.

## Spanish export limitation remains

Read-only provider timing evidence for the current deployed release showed an English retained read completing in 15.539 seconds and first Spanish preparation completing in 498.206 seconds. The Spanish retry returned `RetainedPdfBusy`; it did not launch another render. The proxy read deadline is 240 seconds and browser download deadline 255 seconds. Preparation completion does not establish HTTP/client delivery. The process-local computation guard releases on actual synchronous function exit; it is not a TTL to override.

Inclusive Spanish phases included artifact preparation 110.329 seconds, rendering 58.379 seconds, finalization 258.395 seconds, and installed completion 83.276 seconds. Inclusive measurements must not be summed. Earlier micro-optimizations did not solve this timeout. No deadline, concurrency, lease, cache, deployment or export request was changed here. A separate first-download usability/performance repair requires preserving exact-input binding and final validation, not extending limits or bypassing preparation.

Final local qualification: 28 disclosure tests passed, including both installed bilingual population-shaped PDFs; 247 related measurement, cleanup, identity, candidate finalization/export, scope and Spanish parity regressions passed (four existing pypdf deprecation warnings). Total distinct selected tests: 275. Independent read-only review found no blocker after reviewing strict Spanish missing-label handling. Local Python is 3.12; hosted exact-head Python 3.11 CI/security and deployed behavior remain pending. No deployment or historical-report write was performed.
