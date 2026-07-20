from __future__ import annotations

import re
from typing import Any

VERSION = "nico.express_client_report_postprocessor.v31.compat"


def install_express_client_report_postprocessor_v31_compat() -> dict[str, Any]:
    from nico import express_client_report_postprocessor_v27 as target

    def replace_paragraph_section(markdown: str, heading: str, paragraph: str) -> str:
        replacement = f"## {heading}\n{paragraph}\n"
        # Stop at any following Markdown heading. The previous pattern stopped only
        # at another H2 and accidentally consumed H3 assessment sections placed
        # immediately after Executive Summary.
        pattern = rf"## {re.escape(heading)}\n[\s\S]*?(?=\n## |\n### |\Z)"
        if re.search(pattern, markdown):
            return re.sub(pattern, replacement.rstrip(), markdown)
        return markdown.rstrip() + "\n\n" + replacement

    previous_risk_register = target._risk_register

    def risk_register(result: dict[str, Any]) -> list[str]:
        risks = list(previous_risk_register(result))
        required = (
            "Scanner-clean claims require current-run artifacts to remain attached and parseable. "
            "Mitigation: retain the exact-run scanner artifacts, verify their digests, and block clean claims when an artifact is missing or unreadable."
        )
        if not any("scanner-clean claims require current-run artifacts" in str(item).casefold() for item in risks):
            risks.insert(0, required)
        return risks[:6]

    target._replace_paragraph_section = replace_paragraph_section
    target._risk_register = risk_register
    target.VERSION = "nico.express_client_report_postprocessor.v31"
    return {
        "status": "installed",
        "version": VERSION,
        "heading_boundary_preserved": True,
        "scanner_clean_risk_disclosure_preserved": True,
    }


__all__ = ["VERSION", "install_express_client_report_postprocessor_v31_compat"]
