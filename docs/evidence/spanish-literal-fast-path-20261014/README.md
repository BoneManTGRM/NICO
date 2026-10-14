# Spanish absent-literal fast return

Continues saved ordinary fixes at `3d6555e3e920545d841480d8dc297131df67cb55`, clean at start; no stale test/profiling processes found. Earlier fixes and evidence remain intact.

Parent production evidence for run `comprun_1279a7fb482daa07d2f69deaee14b319`, revision 66: response preparation 468685.740 ms; inclusive render_target 411226.413 ms, thread CPU 408086.259 ms; proxy deadline 240002 ms before headers. This establishes CPU-heavy response preparation exceeding the proxy deadline, but does not isolate a particular translation function as the cause.

## Narrow change and proof

`comprehensive_spanish_presentation_parity_v1._safe_replace` returns immediately when its case-sensitive source literal is absent. The canonical v87 module imports this same helper, so no duplicate implementation is changed. Its regex is only the escaped literal with optional ASCII boundary lookarounds; literal absence proves no match. Present literals retain the original boundary-aware regex/literal replacement path. Ordered replacement loops are unchanged, including replacements that introduce later source literals.

The new operational regression failed before editing because an absent literal dispatched a regex scan (`before.txt`). Post-change checks:

- 11 tests passed: new helper differential/ordered-replacement tests, actual localized report PDF observation equality against the legacy helper, and bilingual scanner status-record publication tests (`after.txt`). Differential test enumerates 3,072 source/boundary/replacement combinations.
- 29 existing tests passed: presentation parity, canonical report parity, evidence literals, and runtime-cache contracts (`contracts.txt`). Total 40 distinct focused tests.
- Independent read-only review found no issue; independently ran two helper tests and 6,144 additional pure-helper comparisons. Full renderer case was deliberately deselected in that independent invocation because the primary run already exercised it.
- Benchmark uses 20 synthetic strings, 79 existing phrase replacements, three repetitions: legacy 0.639 seconds; optimized 0.424 seconds, identical output. This is not a production-sized performance claim.
- Small real-renderer profile remains dominated by finalization/PDF parsing: 12.343 seconds total under profiling, phase17 rebuild 9.453 seconds, finalizer 7.008 seconds, PDF extract_text 5.899 seconds. These are inclusive timings and must not be summed. The earlier 13.282-second profile is a separate sample, not a controlled production speedup proof.

Side-effect review: only regex work/pattern-cache access for absent literals is skipped. No timeout, translation order, evidence filtering, response-cache admission, retained artifact, security/hash validation, approval, or delivery-authority behavior changes. No assessment, historical artifact rewrite, production call, secret access, C++ work, spending, push, or deployment occurred.

## Deliberately deferred cache candidate

`v2_premium_report_renderer` deep-copies canonical input for PDF and filters `client_human_evidence_` stages when `human_report_export_schema` is present. The localized-input cache is keyed by canonical object identity, so this does not share the Markdown entry. Sharing or mutating that entry without proving stage-specific output equivalence could reintroduce filtered stages. No such change was made; retained-response-cache exclusions also remain intact.

## Smallest remaining input

No actual revision-66 frozen report input was found in the selected workspace or temporary artifact filenames. Parent must provide an owner-approved local copy of that frozen canonical report (`reports.json` value), plus exact run/commit/canonical-truth binding, in private scratch storage. This permits actual `_render_target` profiling without rerunning scanners, changing historical state, or fetching an alternate report. To replay the entire retained endpoint rather than only rendering would additionally require its terminal report package/status snapshot.

The known Spanish production timeout remains unverified after this local optimization. Do not claim it fixed or the release ready to ship until actual-input performance and the exact production download are verified by the publication owner. No denied route was retried; the blocker is missing actual frozen input, not an approval denial.
