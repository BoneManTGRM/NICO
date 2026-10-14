# Ordinary report regression verification — 2026-10-14

Base candidate: `506880a4cf9ffba28c9926b48b886ae35d15fa9c`, following local messaging/approval commit `3d6555e3e920545d841480d8dc297131df67cb55` on main `568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`.

## Results and exact scope

- Eight previously deselected cold-process cross-locale cases passed individually on exact base candidate. Both locale orders and four seed pairs ran with original child timeouts. See `manifest.json`, `cold-*.txt/xml`, and `run_checks.py`.
- Initial combined Python process: **175 passed, 23 failed, 8 deselected**. Original failure output is preserved in `ordinary-python.txt/xml`. Production bootstrap collection installs global rendering wrappers; minimal cache/localization unit fixtures assume isolated module execution. CI deliberately executes test files in separate processes. Do not treat this combined invocation as passing.
- The same 15-module selection run one file per process, as CI does: **199 passed**, with eight cold cases excluded because they already passed individually. This run included the evidence-preservation wrapper fix, before the subsequent whitespace/list-prefix expansion. See `isolated-manifest.json`, `run_isolated.py`, and `test_*.txt/xml`.
- Final affected approval/lifecycle/operator modules after whitespace/list expansion: **18 passed** (`approval-final.txt`). Counts overlap the preceding suite; do not add them. Independent lifecycle review ran **3 passed**, finding no remaining blockers.
- Four relevant JavaScript modules: **110 passed** on exact base candidate (`ordinary-javascript.txt`). TypeScript `npm --prefix apps/web run lint` passed (`typescript.txt`). Final changes affect Python approval presentation only.

## Ordinary regression reproduced and fixed

The installed production approval wrapper rewrote pending decisions embedded in Spanish technical evidence, even though the underlying builder preserved that evidence. Its validator also rejected preserved evidence. `approval-wrapper-before.txt` records reproduction. The fix scopes colon-form lifecycle labels to line/list/HTML text boundaries and validates actual JSON text/known lifecycle fields for those labels. Broad non-label checks still inspect serialized JSON, including keys. Actual approval labels remain corrected and stale labels remain rejected in JSON, Markdown, HTML and PDF. Structured approval decisions remain enforced; technical evidence decisions remain unchanged.

Independent review identified indented labels as a boundary case. `indented-before.txt` preserves the failing regression. Horizontal indentation and common list prefixes now remain recognized. Tests use a valid PDF and JSON package to reach the intended gate. No delivery authorization, approval receipt, historical PDF, hash verification or timeout was changed.

## Remaining production evidence / restrictions

Production remains at main `568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`; these are local commits only. Parent owns publication and production browser interactions. No push, PR, merge or deployment performed. Parent reports publication action review rejected publication pending exact approval; this task does not retry it.

The original Spanish request timed out: proxy 240002 ms before headers, backend preparation 468685.740 ms (render target 411226.413 ms). English retained download succeeded; Spanish rebuilt from the same retained assessment. Synthetic verification supports the absent-literal localization fast path in the preceding commit, but does not prove production completion within the deadline.

Actual retained-input local profiling was never run: the supported Library materialization helper failed to download the authorized ZIP (no file produced). Parent forbids further Library retries. Successful post-publication Spanish download, checksum verification, matching retained run/revision/target, restored UI and completion time remain unverified. No alternate report was substituted.

C++ remains paused; ordinary safeguards are not a restart of that project. Database pilot remains HOLD. No fresh assessment, purchase, secret retrieval or direct production/GitHub forbidden route used.
