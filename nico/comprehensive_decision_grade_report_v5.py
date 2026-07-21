from __future__ import annotations

"""Stable import surface for the decision-grade Comprehensive report builder.

The implementation is split across the model, assessment, Markdown/PDF package,
HTML, and roadmap modules.  This module intentionally exposes one canonical
builder name for production bootstrap and tests.
"""

from nico.comprehensive_decision_grade_markdown_v5 import build_comprehensive_report_package
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION

__all__ = [
    "APPENDIX_HEADING",
    "REVIEW_HEADING",
    "VERSION",
    "build_comprehensive_report_package",
]
