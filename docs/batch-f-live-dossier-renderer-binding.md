# Batch F — Live dossier renderer binding

The production report generated at `2026-07-20T00:07:48Z` from merged main commit `e3ac0f187c313e4cc836ddab24cae3fdfe0931ac` remained visually unchanged because `express_report_dossier_export_v15.py` imported `_premium_pdf` by value before the vector renderer patch was installed.

Rebinding `premium._premium_pdf` alone therefore did not update the dossier exporter's static reference. This batch explicitly points the dossier exporter at the final live renderer and proves the actual production export path emits vector score geometry and separate Architecture and Velocity decision records.
