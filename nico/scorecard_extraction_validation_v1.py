from __future__ import annotations

import io
import re
import unicodedata
from typing import Any, Mapping

import nico.v2_report_quality_repairs as quality
import nico.v2_report_quality_runtime_compat as runtime_compat

VERSION = "nico.scorecard-extraction-validation.v1"
_ORIGINAL_VALIDATE = quality._validate_final_pdf
_INSTALLED = False


def _normalized(value: Any) -> str:
    """Normalize PDF extraction without weakening semantic row identity."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_like = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_like.casefold()).strip()


def _scorecard_window(
    pdf: bytes,
    canonical: Mapping[str, Any],
) -> str:
    """Return exactly the rendered scorecard page range, including continuations."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    heading = _normalized("Canonical Technical Scorecard")
    starts = [
        index for index, text in enumerate(page_texts) if heading in _normalized(text)
    ]
    if len(starts) != 1:
        raise ValueError(
            "final premium PDF must contain exactly one technical scorecard"
        )

    expected_pdf = quality._scorecard_page(canonical)
    expected_page_count = len(PdfReader(io.BytesIO(expected_pdf)).pages)
    if expected_page_count < 1:
        raise ValueError("canonical scorecard renderer produced no pages")

    start = starts[0]
    stop = start + expected_page_count
    if stop > len(page_texts):
        raise ValueError("final premium PDF truncated the technical scorecard")
    return "\n".join(page_texts[start:stop])


def _verify_all_rows(
    pdf: bytes,
    canonical: Mapping[str, Any],
    expected_sections: list[Mapping[str, Any]],
) -> None:
    scorecard_text = _normalized(_scorecard_window(pdf, canonical))
    for section in expected_sections:
        label = quality._text(section.get("label") or section.get("id"))
        normalized_label = _normalized(label)
        if normalized_label and normalized_label not in scorecard_text:
            raise ValueError(f"scorecard omitted canonical control row: {label}")

        score = section.get("presented_score", section.get("score"))
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            score_label = f"{int(round(score))}/100"
            if _normalized(score_label) not in scorecard_text:
                raise ValueError(
                    f"scorecard omitted canonical score {score_label} for {label}"
                )


def validate_final_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    expected_sections: list[Mapping[str, Any]],
    spanish: bool,
) -> None:
    """Preserve the original gate and repair only PDF extraction false negatives."""
    try:
        _ORIGINAL_VALIDATE(
            pdf,
            canonical,
            expected_sections=expected_sections,
            spanish=spanish,
        )
        return
    except ValueError as exc:
        message = str(exc)
        extraction_failure = message.startswith(
            "scorecard omitted canonical control row:"
        ) or message.startswith("scorecard omitted canonical score ")
        if spanish or not expected_sections or not extraction_failure:
            raise

    # The original validator has already passed PDF validity, control-character,
    # finality, approval, and immutable-identity checks. Re-verify every scorecard
    # row and score against the exact generated page range using extraction-safe
    # normalization. Any real omission remains a hard publication failure.
    _verify_all_rows(pdf, canonical, expected_sections)


def install_scorecard_extraction_validation() -> dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"status": "already_installed", "version": VERSION}

    quality._validate_final_pdf = validate_final_pdf
    # runtime_compat imported the validator by value, so rebind its module global.
    runtime_compat._validate_final_pdf = validate_final_pdf
    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "raw_exact_match_retained_as_primary": True,
        "wrapped_label_normalization_enabled": True,
        "all_canonical_rows_and_scores_required": True,
        "scorecard_page_range_bounded_to_renderer_output": True,
    }


__all__ = [
    "VERSION",
    "install_scorecard_extraction_validation",
    "validate_final_pdf",
]
