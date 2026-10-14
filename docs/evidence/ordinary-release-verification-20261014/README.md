# Ordinary release verification — 2026-10-14

Base: `568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`, initially clean local checkout. Parent reported both live deployments at this same main, with no staged Railway changes. This environment performed no production requests, secret retrieval, assessment, push, deployment, purchase, database pilot work, or C++ change.

## Changes proved locally

1. Both restored and continued approved runs previously mapped to phase `complete` but displayed the required-stage failure message. The retained pre-fix JavaScript log has four failures across English/Spanish and restore/continuation. Added localized completion copy only; existing terminal status mapping, pending review, failure states, and delivery authority are unchanged.
2. Future approval finalization previously preserved `Human approval: Pending` while recording approval, and replaced standalone reviewer placeholders with generic `Approved`. Synthetic regression reproduced the stale label before editing. Future finalization now corrects that label and points reviewer fields to the certificate. Approval record ID is explicitly `Not recorded` / `No registrado` because this certificate does not contain such an ID. Residual-risk acceptance and technical pending evidence remain unchanged. The future-finalization validator rejects stale approval labels. Existing approved artifacts are not rewritten, reapproved, or silently invalidated.

Independent read-only review found no issue with the completion fix. Approval review identified the initially misleading approval-record-ID certificate reference; corrected as above before commit, then independently re-reviewed with no further blocking finding. These are agent code reviews, not professional assessment approval.

## Verification

- `node --test tests/js/assessment-poll-exhaustion.test.cjs tests/js/review-pdf-download.test.cjs tests/js/pdf-proxy-stream-diagnostics.test.cjs`: 86 passed. Includes exact-run timeout recovery, locale separation, tamper rejection, and delivery gating. `javascript-after.txt`.
- `/workspace/nico-venv/bin/python -m pytest -q tests/test_comprehensive_approved_review_truth_v1.py tests/test_comprehensive_approved_lifecycle_consistency_v1.py tests/test_comprehensive_operator_presentation_v1.py tests/test_comprehensive_scanner_inventory_v1.py tests/test_scanner_status_record_retention.py --durations=5`: 82 passed before the final approval-ID wording correction; `python-after.txt`. Final affected approval tests: 16 passed after the correction, recorded separately in `approval-final.txt`.
- `npm --prefix apps/web run lint`: TypeScript passed; `typescript.txt`.
- Warm bilingual repeatability: 2 passed, 8 cold-process cases deliberately deselected (`pytest -q tests/test_cross_locale_pdf_repeatability_v1.py -k warm --durations=5`), 25.01 seconds. Existing prior audit's 240 Python / 183 JavaScript results are parent-supplied evidence, not newly rerun or added to these counts.
- One initial Python command named a nonexistent `test_comprehensive_approved_report_v1.py`; zero tests ran. Corrected selection is above. Initial scale fixture lacked raw totals and correctly failed candidate population validation; only the corrected reconciled fixture is retained here. Neither failure is counted as a pass.

## Spanish timeout: unresolved production evidence

Parent observed one request for `comprun_1279a7fb482daa07d2f69deaee14b319`, revision 66, target `b8cfbc354d4cb144a03f9159b9ac6c2c3ea83215`, beginning around 12:11:50 UTC. Spanish review download eventually showed the localized timeout guidance and re-enabled the button by 12:16 UTC; no file downloaded. Parent clicked once. This is a terminal failed download, not a proven root cause.

English retained PDF downloaded: 53 pages, SHA256 `9fcb63199e9feb3b2c2e92674d67ad552b3b7072bacd0e5da64848bdfc6894e8`. Spanish assessment UI restored the same target and scores. Parent owns authenticated production observation.

Source tracing: same-locale English can return `_frozen_source_pdf_response`; cross-locale Spanish follows `_render_target` through full canonical artifact rebuild and final navigation. Proxy artifact deadline remains 240 seconds; browser deadline remains 255 seconds. Neither deadline, hash check, run/commit/truth binding, approval gate, nor locale check was changed.

Small real-renderer synthetic cross-locale cases passed. A separate render-scale diagnostic with reconciled synthetic retained candidates completed 1 / 100 / 1,000 candidates in 4.396 / 3.871 / 6.574 seconds, all 22 pages. This fixture is not the production canonical tree or workload. A profiled small rebuild spent 13.282 seconds under profiling; PDF parsing and finalization account for much of that sample. These measurements do not reproduce or explain the production timeout and justify no speculative performance patch.

Next production evidence needed from the parent, without another assessment or bypass:

- Original request's `nico_pdf_proxy_transfer` entries: headers received or timeout outcome, headers latency, first-byte latency, bytes, framing/encoding.
- Original request's `NICO_REPORT_TIMING` entry for this run and `es-MX`: outcome/error type and inclusive `controller_status`, `frozen_pdf`, `render_target` / `installed_render_target`, PDF text phases. A missing terminal log is absence of evidence, not proof of a renderer failure.
- Correlate those timestamps with the single original request to determine whether the delay preceded backend headers, arose during rendering/retained input validation, or happened during response transfer. No direct production 403 or GitHub CLI Forbidden route was retried.

Spanish download remains a release-verification blocker. The two implemented corrections do not establish a fix for it or a ready-to-ship result.

## Historical evidence preserved

Parent reported SARA `comprun_0f78a7227b616e43e7a7dfa0e5253898` revision 49 with eight recorded completed scanners but missing raw bytes, plus unavailable pip-audit. ABA `comprun_736cb3a3f388848014ff30c137e717cf` revision 61 similarly had six completed/raw-missing and three unavailable/checksum-unavailable. Current inventory tests confirm recorded execution, retained-byte availability, and coverage are separate. No historical statuses were promoted or scanners rerun; migration/retention cause is unknown.

Historical approved SARA PDF SHA256 `9ef895cbe98b69fb5cd322eefe3aa964e9a9759f0339e6fe9fdd89ce2031c4e9` remains unchanged. Future finalizer repair does not rewrite it. Current English renderer already labels report page count `certificate excluded`; no arbitrary page-count evidence rewrite was added. Current publication pipeline already distinguishes retained scanner status records from raw execution evidence (base commit includes `3dcdb620`); bilingual rendered-output tests passed. Older frozen PDFs retain their old wording. Small hash typography and historical stakeholder-label inconsistencies remain observations, not new current-path fixes.
