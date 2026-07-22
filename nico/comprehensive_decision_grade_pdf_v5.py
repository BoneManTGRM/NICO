from __future__ import annotations

# Compatibility import: v5 remains the stable production import path while the
# v6 renderer provides the compact executive report and reconciled appendix.
from nico.comprehensive_decision_grade_pdf_v6 import _build_pdf, _pdf_with_final_count

__all__ = ["_build_pdf", "_pdf_with_final_count"]
