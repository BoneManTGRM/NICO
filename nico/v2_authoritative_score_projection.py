from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping, MutableMapping

VERSION = "nico.v2.authoritative-score-projection.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def project_score_labels_in_place(canonical: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Place the canonical score pair inside the executive narrative.

    The old premium shell keeps its dashboard, while Markdown and HTML retain
    exact score labels required by cross-format verification. This is not a
    separate score-summary page and remains deterministic across repeated runs.
    """

    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical = next((score for raw in (
        truth.get("technical_score"), assessment.get("technical_score"),
        maturity.get("technical_score"), maturity.get("presented_score"), maturity.get("score"),
    ) if (score := _numeric(raw)) is not None), None)
    adjusted = next((score for raw in (
        truth.get("canonical_evidence_adjusted_score"),
        assessment.get("canonical_evidence_adjusted_score"), assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"), maturity.get("evidence_adjusted_score"), technical,
    ) if (score := _numeric(raw)) is not None), None)
    if technical is None or adjusted is None:
        return canonical

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or identity.get("report_language")
        or "en"
    ).casefold()
    spanish = language.startswith("es")
    sentence = (
        f"Par canónico de puntuación: Madurez técnica {technical}/100. Ajuste por evidencia {adjusted}/100."
        if spanish
        else f"Canonical score pair: Technical maturity {technical}/100. Evidence-Adjusted {adjusted}/100."
    )
    summary = _text(assessment.get("executive_summary"))
    summary = re.sub(
        r"(?:Canonical score pair: Technical maturity \d{1,3}/100\. Evidence-Adjusted \d{1,3}/100\.|"
        r"Par canónico de puntuación: Madurez técnica \d{1,3}/100\. Ajuste por evidencia \d{1,3}/100\.)",
        "",
        summary,
        flags=re.I,
    ).strip()
    assessment["executive_summary"] = f"{summary} {sentence}".strip()
    assessment["executive_score_projection"] = {
        "version": VERSION,
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "rendered_inside_executive_narrative": True,
        "separate_score_summary_page": False,
    }
    canonical["assessment"] = assessment
    return canonical


__all__ = ["VERSION", "project_score_labels_in_place"]
