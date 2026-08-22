from __future__ import annotations

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as presentation
from nico.spanish_cross_format_score_parity_v1 import (
    _install_spanish_presentation_score_summary_contract,
)


def _base_summary(
    *,
    adjusted: str = "93",
    technical: str = "93",
    review: int = 680,
    material: int = 0,
) -> str:
    return (
        "Technical maturity remains based on exact-commit technical controls. "
        f"Evidence-Adjusted readiness is {adjusted}/100 versus technical maturity "
        f"{technical}/100. NICO retains {review} review-required candidates and "
        f"{material} confirmed material findings as explicit review context. "
        "Candidate volume, clustering and reviewer workload do not change numeric "
        "security or readiness scores."
    )


def _extended_summary(**kwargs: object) -> str:
    return (
        _base_summary(**kwargs)
        + " Candidate volume and reviewer workload are operational review metrics "
        "and have no numeric technical-maturity or Evidence-Adjusted score effect."
    )


def test_extended_current_score_summary_is_fully_localized_without_value_drift() -> None:
    installation = _install_spanish_presentation_score_summary_contract()
    assert installation["bound"] is True

    translated = presentation._translate_presentation_field(
        _extended_summary(adjusted="91.5", technical="94", review=37, material=2),
        "summary",
    )

    assert "La madurez técnica sigue basándose" in translated
    assert "91.5/100" in translated
    assert "94/100" in translated
    assert "37 candidatos que requieren revisión" in translated
    assert "2 hallazgos materiales confirmados" in translated
    assert "métricas operativas de revisión" in translated
    assert "Technical maturity" not in translated
    assert "Candidate volume" not in translated
    assert "Evidence-Adjusted" not in translated


def test_original_score_summary_contract_remains_supported() -> None:
    translated = presentation._translate_presentation_field(
        _base_summary(adjusted="88", technical="90", review=14, material=1),
        "summary",
    )

    assert "88/100" in translated
    assert "90/100" in translated
    assert "14 candidatos que requieren revisión" in translated
    assert "1 hallazgos materiales confirmados" in translated
    assert "Technical maturity" not in translated


def test_unknown_score_summary_extension_still_fails_closed() -> None:
    unsupported = (
        _base_summary()
        + " Candidate volume may automatically improve the client readiness score."
    )

    with pytest.raises(ValueError, match="unrecognized Spanish presentation contract"):
        presentation._translate_presentation_field(unsupported, "summary")


def test_score_summary_contract_installation_is_idempotent() -> None:
    first = _install_spanish_presentation_score_summary_contract()
    second = _install_spanish_presentation_score_summary_contract()

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["status"] == "already_installed"
