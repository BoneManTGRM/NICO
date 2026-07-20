# Production artifact evidence — 2026-07-20

The 17-page Express report generated at `2026-07-20T00:07:48Z` from commit `e3ac0f187c313e4cc836ddab24cae3fdfe0931ac` still rendered glyph score bars and combined Architecture/Velocity content.

Root cause: `express_report_dossier_export_v15.py` imported `_premium_pdf` by value before the v21 renderer patch was applied. The final report path called that stale reference, bypassing the live patched renderer.

Release criterion for this batch: the actual dossier export path must report `express_pdf_renderer_truth.status=complete`, retain `reportlab_vector_geometry`, and emit separate Architecture and Velocity decision records.
