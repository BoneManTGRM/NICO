from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-current-copy-worker.v98"
_ONE_ARG_MARKER = "__nico_spanish_current_copy_worker_one_v98__"
_TWO_ARG_MARKER = "__nico_spanish_current_copy_worker_two_v98__"


def _current_report_phrase_pairs() -> tuple[tuple[str, str], ...]:
    """Return the final-report leak contract from the authoritative parity module."""

    from nico.comprehensive_current_report_truth_parity_v1 import _ES_PHRASES

    return tuple(
        sorted(
            ((str(source), str(target)) for source, target in _ES_PHRASES.items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def localize_current_report_copy_v98(value: Any) -> str:
    """Translate only registered NICO-authored current-report presentation fragments.

    The isolated final-report process must see the same bounded localization contract
    as the parent process. This helper intentionally performs literal replacement only
    for phrases already approved by the current report truth-parity validator. Any
    other English remains untouched and therefore continues into the existing strict
    Spanish translator, which fails closed rather than silently publishing mixed copy.
    """

    text = str(value or "")
    for source, target in _current_report_phrase_pairs():
        text = text.replace(source, target)
    return text


def _wrap_one_arg(current: Callable[[Any], str]) -> Callable[[Any], str]:
    if getattr(current, _ONE_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any) -> str:
        return current(localize_current_report_copy_v98(value))

    setattr(wrapped, _ONE_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def _wrap_two_arg(current: Callable[[Any, Any], str]) -> Callable[[Any, Any], str]:
    if getattr(current, _TWO_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any, key: Any = "") -> str:
        return current(localize_current_report_copy_v98(value), key)

    setattr(wrapped, _TWO_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def install_comprehensive_spanish_current_copy_worker_v98() -> dict[str, Any]:
    """Bind current report localization before the isolated renderer cache freezes."""

    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    baseline = v88.install_comprehensive_spanish_exit_criteria_v88()
    if baseline.get("bound") is not True:
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_v88_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    current_field = getattr(v88, "_translate_canonical_field_v88", None)
    current_presentation = getattr(v88, "_translate_presentation_v88", None)
    current_safe = getattr(v88, "_presentation_safe_es_v88", None)
    if not all(callable(value) for value in (current_field, current_presentation, current_safe)):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_current_copy_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    field = _wrap_two_arg(current_field)
    presentation = _wrap_one_arg(current_presentation)
    safe = _wrap_one_arg(current_safe)
    v88._translate_canonical_field_v88 = field
    v88._translate_presentation_v88 = presentation
    v88._presentation_safe_es_v88 = safe

    binder = getattr(v88, "_bind_translation_surfaces", None)
    if callable(binder):
        binder()

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation_module

    bound = bool(
        canonical._translate_presentation_field is field
        and canonical._translate_presentation is presentation
        and presentation_module._safe_es is safe
    )
    sample = localize_current_report_copy_v98(
        "Material confirmado findings: 0. Strengthen architecture boundaries, "
        "test/release automation, functional QA evidence, and remediation verification."
    )
    sample_ok = (
        "Material confirmado findings" not in sample
        and "Strengthen architecture boundaries" not in sample
        and "Hallazgos materiales confirmados" in sample
        and "Reforzar los límites de arquitectura" in sample
    )

    return {
        "status": "installed" if bound and sample_ok else "blocked",
        "version": VERSION,
        "bound": bound,
        "current_report_copy_contract_bound": sample_ok,
        "worker_safe_before_renderer_cache": True,
        "unknown_prose_still_delegates_fail_closed": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "english_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_current_copy_worker_v98",
    "localize_current_report_copy_v98",
]
