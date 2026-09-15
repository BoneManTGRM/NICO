# Authorized phase font correction — 2026-09-15

Status: implementation and local regression qualified; production download and final acceptance remain pending. This does not declare shipment.

## Reproduced defect

The isolated final-report worker installs embedded Vera fonts under historical Helvetica aliases. The API process serving retained authorized editions does not inherit that installation. PR1615's phase presenter regenerated its overlay under whichever aliases happened to exist in that process. A fresh API process therefore produced unembedded, visibly smaller English phase text and rejected the worker-created Spanish overlay because its subset-encoded accents differed.

Two fresh-process regressions failed against the previous implementation: English `Unembedded phase font` and Spanish `authorized_phase_overlay_not_uniquely_identified`. Existing single-process phase tests had passed and did not cover this transition.

## Bounded correction

Use separate presenter-owned embedded aliases, recognize the exact known worker/API overlays, and require embedded fonts before reusing an already-current overlay. Preserve the original default renderer and all historical Helvetica aliases. Keep authority validation, unknown-content rejection, retained source, approval, delivery receipt, and revision unchanged. Identify new presentation bytes as `nico.authorized_lifecycle_presentation.v3` with the original manifest as parent.

No new assessment, human approval, delivery permission, specialist completion, or transmission is created. The temporary source/dependency recovery workflow is excluded from this candidate tree.

## Local evidence

Production-pinned pypdf 6.16.2 and ReportLab 5.0.1; local Python 3.13 (protected CI must separately qualify its Python environment).

Focused plus phase/delivery integration command: `python -m pytest tests/test_authorized_phase_font_process_boundary.py tests/test_authorized_phase_presentation.py tests/test_comprehensive_four_phase_report_v1.py tests/test_comprehensive_operator_delivery_v1.py tests/test_four_phase_completion_report_extender_v1.py -q` — 33 passed. 28 existing pypdf reader-owned-page deprecation warnings remain; this patch does not change the historical renderer to suppress them.

Engineering replay of the retained actual delivery-68 export verifies original manifest and both receipt hashes, unchanged canonical/Markdown/HTML/source identity, unchanged historical aliases/default overlay bytes, exact input immutability, correct detached artifact digests, and repeat-derivation equality. All 49 pages render; only physical page 4 changes in text and pixels. The other 48 pages and the area above the owned matrix on page 4 are pixel-identical. Corrected phase text is AUTHORIZED and its used fonts are embedded.

Original PDF: 1,976,107 bytes, SHA-256 `1aed2a0af3b5822abba3e2e2171a8987cfa76ad241908c2e97e4af70fa618391`.
Local replay PDF: 2,016,082 bytes, SHA-256 `38b51b182b09c0e5878075aac6c8e320b6d06aad50d11b0b3994ea2f9bb83e08`.

These are local replay results, not proof of new production retrieval. Required next: protected CI/integration, deployed identity verification, authenticated ordinary retrieval of the same delivery-authorized revision 68, and final all-page inspection. No owner reapproval is needed for this presentation-only correction.
