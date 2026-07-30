from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter
from typing import Any, Mapping

import nico.v2_report_quality_repairs as quality
import nico.v2_report_quality_runtime_compat as runtime_compat

VERSION = "nico.scorecard-extraction-validation.v2"
_ORIGINAL_VALIDATE = quality._validate_final_pdf
_INSTALLED = False


def _normalized(value: Any) -> str:
    """Normalize PDF extraction without weakening semantic row identity."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_like = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_like.casefold()).strip()


def _tokens(value: Any) -> Counter[str]:
    return Counter(_normalized(value).split())


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


def _required_row_tokens(
    expected_sections: list[Mapping[str, Any]],
) -> Counter[str]:
    required: Counter[str] = Counter()
    for section in expected_sections:
        label = quality._text(section.get("label") or section.get("id"))
        required.update(_tokens(label))
        score = section.get("presented_score", section.get("score"))
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            required.update(_tokens(f"{int(round(score))}/100"))
        else:
            required.update(_tokens("NOT SCORED"))
    return required


def _contains_required_tokens(actual: Counter[str], required: Counter[str]) -> bool:
    return all(actual[token] >= count for token, count in required.items())


def _verify_all_rows(
    pdf: bytes,
    canonical: Mapping[str, Any],
    expected_sections: list[Mapping[str, Any]],
) -> None:
    """Verify every canonical row without depending on PDF column extraction order.

    ReportLab and pypdf can interleave cells from the same table row when a label
    wraps around a slash or a column boundary. The canonical renderer itself is used
    to determine the exact scorecard page range, then the validator requires the
    complete multiset of canonical label and score tokens. Whitespace, punctuation,
    Unicode composition, line wrapping, and extraction order cannot create a false
    missing-row result, while a genuinely omitted row or score remains blocking.
    """

    scorecard_text = _scorecard_window(pdf, canonical)
    actual = _tokens(scorecard_text)
    required = _required_row_tokens(expected_sections)
    if _contains_required_tokens(actual, required):
        return

    # Preserve precise diagnostics for the first genuinely absent row or score.
    for section in expected_sections:
        label = quality._text(section.get("label") or section.get("id"))
        label_tokens = _tokens(label)
        if label_tokens and not _contains_required_tokens(actual, label_tokens):
            raise ValueError(f"scorecard omitted canonical control row: {label}")

        score = section.get("presented_score", section.get("score"))
        score_label = (
            f"{int(round(score))}/100"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else "NOT SCORED"
        )
        if not _contains_required_tokens(actual, _tokens(score_label)):
            raise ValueError(
                f"scorecard omitted canonical score {score_label} for {label}"
            )

    raise ValueError(
        "scorecard canonical row-token parity did not match the rendered scorecard"
    )


def validate_final_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    expected_sections: list[Mapping[str, Any]],
    spanish: bool,
) -> None:
    """Preserve all original gates and repair only extraction-order false negatives."""
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
        extraction_failure = (
            message.startswith("scorecard omitted canonical control row:")
            or message.startswith("scorecard omitted canonical score ")
            or message == "final premium PDF must contain exactly one technical scorecard"
        )
        if not expected_sections or not extraction_failure:
            raise

    # The original validator already passed PDF validity, control-character,
    # finality, approval, and immutable-identity checks before reaching the
    # scorecard extraction assertion. Re-verify the exact generated scorecard
    # page range with order-independent canonical row and score requirements.
    _verify_all_rows(pdf, canonical, expected_sections)


def install_scorecard_extraction_validation() -> dict[str, Any]:
    global _INSTALLED
    contract = {
        "version": VERSION,
        "raw_exact_match_retained_as_primary": True,
        "wrapped_label_normalization_enabled": True,
        "column_extraction_order_independent": True,
        "multi_page_scorecard_supported": True,
        "all_canonical_rows_and_scores_required": True,
        "scorecard_page_range_bounded_to_renderer_output": True,
        "spanish_and_english_supported": True,
    }
    if _INSTALLED:
        # Rebind on every installation request. Production bootstraps intentionally
        # call this last so a prior compatibility installer cannot restore the
        # brittle raw-substring validator afterward.
        quality._validate_final_pdf = validate_final_pdf
        runtime_compat._validate_final_pdf = validate_final_pdf
        return {"status": "already_installed", **contract}

    quality._validate_final_pdf = validate_final_pdf
    # runtime_compat imported the validator by value, so rebind its module global.
    runtime_compat._validate_final_pdf = validate_final_pdf
    _INSTALLED = True
    return {"status": "installed", **contract}


__all__ = [
    "VERSION",
    "install_scorecard_extraction_validation",
    "validate_final_pdf",
]
