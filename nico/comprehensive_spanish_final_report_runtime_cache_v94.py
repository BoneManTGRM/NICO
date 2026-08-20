from __future__ import annotations

import os
import threading
from collections import OrderedDict
from functools import lru_cache, wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive_spanish_final_report_runtime_cache.v94"
_TRANSLATION_CACHE_DEFAULT = 16384
_TRANSLATION_CACHE_MAX = 32768
_RENDER_INPUT_CACHE_DEFAULT = 2
_RENDER_INPUT_CACHE_MAX = 4
_FIELD_MARKER = "__nico_spanish_field_translation_cache_v94__"
_PRESENTATION_MARKER = "__nico_spanish_presentation_translation_cache_v94__"
_SAFE_MARKER = "__nico_spanish_safe_translation_cache_v94__"
_RENDER_INPUT_MARKER = "__nico_spanish_render_input_cache_v94__"

_RENDER_INPUT_LOCK = threading.RLock()
_RENDER_INPUT_CACHE: OrderedDict[
    int,
    tuple[
        Mapping[str, Any],
        tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str],
    ],
] = OrderedDict()
_RENDER_INPUT_HITS = 0
_RENDER_INPUT_MISSES = 0


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _translation_cache_size() -> int:
    return _bounded_int(
        "NICO_SPANISH_TRANSLATION_CACHE_SIZE",
        _TRANSLATION_CACHE_DEFAULT,
        1024,
        _TRANSLATION_CACHE_MAX,
    )


def _render_input_cache_size() -> int:
    return _bounded_int(
        "NICO_SPANISH_RENDER_INPUT_CACHE_SIZE",
        _RENDER_INPUT_CACHE_DEFAULT,
        1,
        _RENDER_INPUT_CACHE_MAX,
    )


def _cached_one_arg(
    current: Callable[[Any], str],
    *,
    marker: str,
) -> Callable[[Any], str]:
    if getattr(current, marker, False):
        return current

    @lru_cache(maxsize=_translation_cache_size())
    def cached_text(value: str) -> str:
        return current(value)

    @wraps(current)
    def wrapped(value: Any) -> str:
        return cached_text(str(value or ""))

    setattr(wrapped, marker, True)
    setattr(wrapped, "cache_info", cached_text.cache_info)
    setattr(wrapped, "cache_clear", cached_text.cache_clear)
    setattr(wrapped, "cache_parameters", cached_text.cache_parameters)
    return wrapped


def _cached_two_arg(
    current: Callable[[Any, Any], str],
    *,
    marker: str,
) -> Callable[[Any, Any], str]:
    if getattr(current, marker, False):
        return current

    @lru_cache(maxsize=_translation_cache_size())
    def cached_text(value: str, key: str) -> str:
        return current(value, key)

    @wraps(current)
    def wrapped(value: Any, key: Any = "") -> str:
        return cached_text(str(value or ""), str(key or ""))

    setattr(wrapped, marker, True)
    setattr(wrapped, "cache_info", cached_text.cache_info)
    setattr(wrapped, "cache_clear", cached_text.cache_clear)
    setattr(wrapped, "cache_parameters", cached_text.cache_parameters)
    return wrapped


def _cached_render_inputs(
    current: Callable[
        [Mapping[str, Any]],
        tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str],
    ],
) -> Callable[
    [Mapping[str, Any]],
    tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str],
]:
    if getattr(current, _RENDER_INPUT_MARKER, False):
        return current

    @wraps(current)
    def wrapped(
        canonical: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str]:
        global _RENDER_INPUT_HITS, _RENDER_INPUT_MISSES
        cache_key = id(canonical)
        with _RENDER_INPUT_LOCK:
            cached = _RENDER_INPUT_CACHE.get(cache_key)
            if cached is not None and cached[0] is canonical:
                _RENDER_INPUT_CACHE.move_to_end(cache_key)
                _RENDER_INPUT_HITS += 1
                return cached[1]

        rendered = current(canonical)
        with _RENDER_INPUT_LOCK:
            _RENDER_INPUT_MISSES += 1
            _RENDER_INPUT_CACHE[cache_key] = (canonical, rendered)
            _RENDER_INPUT_CACHE.move_to_end(cache_key)
            while len(_RENDER_INPUT_CACHE) > _render_input_cache_size():
                _RENDER_INPUT_CACHE.popitem(last=False)
        return rendered

    setattr(wrapped, _RENDER_INPUT_MARKER, True)
    return wrapped


def _cache_info(value: Any) -> dict[str, int]:
    getter = getattr(value, "cache_info", None)
    if not callable(getter):
        return {"hits": 0, "misses": 0, "maxsize": 0, "currsize": 0}
    info = getter()
    return {
        "hits": int(info.hits),
        "misses": int(info.misses),
        "maxsize": int(info.maxsize or 0),
        "currsize": int(info.currsize),
    }


def release_comprehensive_spanish_render_input_cache_v94() -> int:
    """Release heavyweight canonical/render projections after one final-report attempt.

    Translation caches contain only bounded strings and remain reusable. Render-input
    entries retain the complete canonical object and its localized projection, so they
    are attempt-scoped and must not survive the serialized final-report boundary.
    """

    with _RENDER_INPUT_LOCK:
        released = len(_RENDER_INPUT_CACHE)
        _RENDER_INPUT_CACHE.clear()
    return released


def spanish_final_report_runtime_cache_status() -> dict[str, Any]:
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    with _RENDER_INPUT_LOCK:
        render_entries = len(_RENDER_INPUT_CACHE)
        render_hits = _RENDER_INPUT_HITS
        render_misses = _RENDER_INPUT_MISSES

    field = getattr(v88, "_translate_canonical_field_v88", None)
    presentation = getattr(v88, "_translate_presentation_v88", None)
    safe = getattr(v88, "_presentation_safe_es_v88", None)
    render_inputs = getattr(canonical, "_render_inputs", None)
    bound = bool(
        callable(field)
        and getattr(field, _FIELD_MARKER, False)
        and callable(presentation)
        and getattr(presentation, _PRESENTATION_MARKER, False)
        and callable(safe)
        and getattr(safe, _SAFE_MARKER, False)
        and callable(render_inputs)
        and getattr(render_inputs, _RENDER_INPUT_MARKER, False)
        and getattr(canonical, "_translate_presentation_field", None) is field
        and getattr(canonical, "_translate_presentation", None) is presentation
    )
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "translation_cache_size": _translation_cache_size(),
        "render_input_cache_size": _render_input_cache_size(),
        "field_translation_cache": _cache_info(field),
        "presentation_translation_cache": _cache_info(presentation),
        "safe_translation_cache": _cache_info(safe),
        "render_input_cache_entries": render_entries,
        "render_input_cache_hits": render_hits,
        "render_input_cache_misses": render_misses,
        "preflight_translation_results_reused_by_renderer": True,
        "markdown_pdf_localized_inputs_reused_for_same_canonical_object": True,
        "render_input_cache_attempt_scoped": True,
        "bounded_process_memory": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_spanish_final_report_runtime_cache_v94() -> dict[str, Any]:
    """Cache repeated es-MX presentation work without changing report truth.

    The Spanish production path intentionally validates report-bound presentation
    strings before publication. The same translation functions are then invoked again
    while Markdown and PDF are rendered, and the canonical Spanish render inputs are
    rebuilt independently for those two artifacts. Large Comprehensive assessments can
    therefore spend the final-report window repeating deterministic localization work.

    Bind bounded process-local caches after the existing v88/v89/v90 compatibility
    installers. Missing translations still raise through the original strict functions;
    this only reuses successful deterministic results and the already-localized input
    projection for the same immutable canonical object.
    """

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_exit_criteria_v88 as v88
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    installer = getattr(v88, "install_comprehensive_spanish_exit_criteria_v88", None)
    if callable(installer):
        installer()

    current_field = getattr(v88, "_translate_canonical_field_v88", None)
    current_presentation = getattr(v88, "_translate_presentation_v88", None)
    current_safe = getattr(v88, "_presentation_safe_es_v88", None)
    current_render_inputs = getattr(canonical, "_render_inputs", None)
    if not all(
        callable(value)
        for value in (
            current_field,
            current_presentation,
            current_safe,
            current_render_inputs,
        )
    ):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_report_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    field = _cached_two_arg(current_field, marker=_FIELD_MARKER)
    localized = _cached_one_arg(
        current_presentation,
        marker=_PRESENTATION_MARKER,
    )
    safe = _cached_one_arg(current_safe, marker=_SAFE_MARKER)
    render_inputs = _cached_render_inputs(current_render_inputs)

    v88._translate_canonical_field_v88 = field
    v88._translate_presentation_v88 = localized
    v88._presentation_safe_es_v88 = safe
    canonical._translate_presentation_field = field
    canonical._translate_presentation = localized
    canonical._render_inputs = render_inputs
    presentation._safe_es = safe

    binder = getattr(v88, "_bind_translation_surfaces", None)
    if callable(binder):
        binder()

    state = spanish_final_report_runtime_cache_status()
    if state.get("bound") is not True:
        return {
            **state,
            "status": "blocked",
            "reason": "spanish_report_runtime_cache_binding_failed",
        }
    return state


def reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests() -> None:
    global _RENDER_INPUT_HITS, _RENDER_INPUT_MISSES
    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    for name in (
        "_translate_canonical_field_v88",
        "_translate_presentation_v88",
        "_presentation_safe_es_v88",
    ):
        value = getattr(v88, name, None)
        clear = getattr(value, "cache_clear", None)
        if callable(clear):
            clear()
    release_comprehensive_spanish_render_input_cache_v94()
    with _RENDER_INPUT_LOCK:
        _RENDER_INPUT_HITS = 0
        _RENDER_INPUT_MISSES = 0


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_final_report_runtime_cache_v94",
    "release_comprehensive_spanish_render_input_cache_v94",
    "reset_comprehensive_spanish_final_report_runtime_cache_v94_for_tests",
    "spanish_final_report_runtime_cache_status",
]
