# Lossless sparse prose flow

Whole-section `KeepTogether` in the installed sparse reflow renderer forced each
source section onto a fresh page when its full body could not fit the remaining
space. The renderer now appends those paragraphs normally. Existing heading
`keepWithNext`, body widow/orphan settings, fonts, leading, margins and spacing
remain unchanged. Installer diagnostics now report heading attachment rather than
claiming whole-section attachment.

The change does not alter page eligibility. Tables/charts and protected sections
remain excluded; required primary evidence remains retained. Worksheet rendering
and its effective minimum 9pt typography are untouched. Existing text-preservation,
canonical, manifest, approval, source and 60-page acceptance gates remain active.

## Reproduction and verification

The new EN/es regression uses four sparse prose sections containing 25 uniquely
identified evidence rows each. The baseline retains four physical pages; the
change produces three. Tests compare the full normalized text sequence exactly,
verify every source marker once, keep each heading with its first evidence row,
and check PDF text geometry with Poppler. An overlapping-text negative control
verifies the geometry oracle. Protected page content streams remain identical.

An ordinary composer fixture containing 55 protected primary pages, those four
sparse pages and two required component pages fails at 61 on the baseline. It
passes at exactly 60 after reflow. Adding another required page still rejects at
61. The fixture demonstrates a bounded lossless repair, not the unknown page
population of the retained production report.

Navigation checks verify canonical bookmarks point to actual section pages and
physical page labels remain continuous after installed final reflow. Existing
installed tests cover all worksheet content, >=9pt effective typography, canonical
immutability, exact artifact hashes, blocked delivery and Spanish parity.

Validation: 117 layout/composer/finalizer/navigation/exact-hash tests; 5 manifest
rebinding tests in a fresh process; 43 installed worksheet/Spanish parity tests.
All 165 passed. Four initial bilingual regression cases fail against the baseline
renderer. `git diff --check` passed.

A combined process also reproduces an existing order-dependent failure in
`test_preapproval_update_refreshes_visible_pdf_digests_and_preserves_original[es-MX]`:
the inherited Spanish validator expects an `Índice` title after other tests install
semantic navigation. The same failure occurs on the pristine b715b559 tree. Its
module passes all five tests in isolation. This patch does not change that separate
test/installer-state issue or weaken its validator.

## Local cost and limits

Five-iteration sparse reflow medians in seconds:

| Locale | Baseline pages / time | Changed pages / time | Composer baseline / changed |
| --- | --- | --- | --- |
| en | 4 / 0.0171 | 3 / 0.0255 | rejects 61 at 0.0830s / passes 60 at 0.1081s |
| es-MX | 4 / 0.0180 | 3 / 0.0262 | rejects 61 at 0.0836s / passes 60 at 0.1094s |

Peak process RSS stayed below 93 MiB in these probes. Successful reflow performs
the existing preservation check and PDF rewrite which the no-savings baseline
skipped. These local synthetic timings are not production latency predictions.

The exact production payload is unavailable. Its page savings and successful
completion remain unproven; the earlier proxy timeout is also not repaired here.
No production run, export, deployment or multi-volume integration was performed.
