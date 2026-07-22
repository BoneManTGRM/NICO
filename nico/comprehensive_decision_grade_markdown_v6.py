from __future__ import annotations

import re
from typing import Any

from nico.comprehensive_decision_grade_markdown_v5 import (
    _build_markdown as _build_markdown_v5,
    _clean_evidence,
    _clean_limitation,
    _decision_summary,
    _decorate_assessment,
    _limitation_metrics,
    _markdown_table,
    _roadmap_from_stages,
    _staffing_from_stages,
    _stage_summaries,
)


def _escape(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_escape(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _build_markdown(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> str:
    rendered = _build_markdown_v5(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    executive = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    weights = [item for item in assessment.get("scoring_weight_table") or [] if isinstance(item, dict)]

    risk_block = "## Executive Risk Register\n\n" + _table(
        ["Priority", "Consolidated risk", "Business impact", "Confidence", "Recommended action"],
        [[item.get("priority"), item.get("title"), item.get("impact"), item.get("confidence"), item.get("recommendation")] for item in executive]
        or [["—", "No consolidated risk retained", "Human review remains required", "—", "Verify evidence completeness"]],
    ) + "\n\n## Detailed Findings Register"
    rendered = re.sub(
        r"## Executive Risk Register\n.*?\n## Detailed Findings Register",
        risk_block,
        rendered,
        flags=re.S,
    )

    weighting_block = "\n\n## Weighted Maturity Calculation\n\n" + _table(
        ["Control", "Weight", "Score", "Contribution", "Included", "Assurance"],
        [[item.get("control"), item.get("weight_display"), item.get("score") if item.get("score") is not None else "—", item.get("weighted_contribution") if item.get("weighted_contribution") is not None else "—", "Yes" if item.get("included") else "No", item.get("assurance")] for item in weights],
    )
    rendered = rendered.replace("\n## Executive Risk Register", weighting_block + "\n\n## Executive Risk Register", 1)
    rendered = rendered.replace(
        "Technical score, evidence assurance, and client-delivery authorization are independent.",
        "Technical score, evidence assurance, and client-delivery authorization are independent. Unscored controls are excluded from weighted maturity rather than treated as zero.",
        1,
    )
    return rendered


__all__ = [
    "_build_markdown",
    "_clean_evidence",
    "_clean_limitation",
    "_decision_summary",
    "_decorate_assessment",
    "_limitation_metrics",
    "_roadmap_from_stages",
    "_staffing_from_stages",
    "_stage_summaries",
]
