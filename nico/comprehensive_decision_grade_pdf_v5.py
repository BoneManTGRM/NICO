from __future__ import annotations

# Compatibility module retained for existing imports and historical contracts.
# The v6 renderer preserves the public function signatures while producing the
# compact executive report plus a separately structured evidence appendix.
from nico.comprehensive_premium_pdf_v6 import _build_pdf, _pdf_with_final_count

__all__ = ["_build_pdf", "_pdf_with_final_count"]
