from __future__ import annotations

import re
from typing import Any

VERSION = "nico.v2.future-approval-guidance-layout.v1"
_MARKER = "__nico_future_approval_guidance_layout_v1__"

# PDF text extraction can place page headers, footers, and line fragments between
# words that were one sentence in the source document. These patterns are bounded
# and clause-anchored: they remove only the known explanatory future-state or
# negative-automation sentence through both required finality terms. They do not
# remove a later, independent current-state assertion.
_GUIDANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bonly an authorized reviewer\b.{0,900}?\bchange the status\b"
        r".{0,900}?\bapproved final\b.{0,900}?\bclient delivery authorized\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bautomation cannot\b.{0,900}?\bchange this package\b"
        r".{0,900}?\bapproved final\b.{0,900}?\bclient delivery authorized\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bsolo un revisor autorizado\b.{0,900}?\bcambiar el estado\b"
        r".{0,900}?\bfinal aprobado\b.{0,900}?\bentrega al cliente autorizada\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bla automatizacion no puede\b.{0,900}?\bcambiar este paquete\b"
        r".{0,900}?\bfinal aprobado\b.{0,900}?\bentrega al cliente autorizada\b",
        re.DOTALL,
    ),
)

_FORBIDDEN_CURRENT_STATE_MARKERS = (
    "final report",
    "informe final",
    "automated final",
    "final aprobado",
    "approved final",
    "client delivery authorized",
    "entrega al cliente autorizada",
)


def _remove_bounded_future_guidance(value: str) -> str:
    from nico import v2_automated_draft_quality_compat_v1 as target

    current = target._semantic(value)
    for guidance in target._AUTHORIZED_FUTURE_STATE_GUIDANCE:
        current = current.replace(target._semantic(guidance), " ")
    for pattern in _GUIDANCE_PATTERNS:
        current = pattern.sub(" ", current)
    return " ".join(current.split())


def _contains_unapproved_finality(value: str) -> bool:
    current_state = _remove_bounded_future_guidance(value)
    return any(marker in current_state for marker in _FORBIDDEN_CURRENT_STATE_MARKERS)


def install_future_approval_guidance_layout_v1() -> dict[str, Any]:
    from nico import v2_automated_draft_quality_compat_v1 as target

    target.install_automated_draft_quality_compat()
    current = target._current_state_finality_scope
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bounded_layout_noise_supported": True,
            "current_finality_gate_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    setattr(_remove_bounded_future_guidance, _MARKER, True)
    setattr(_remove_bounded_future_guidance, "_nico_previous", current)
    target._current_state_finality_scope = _remove_bounded_future_guidance
    target._contains_unapproved_finality = _contains_unapproved_finality
    return {
        "status": "installed",
        "version": VERSION,
        "bounded_layout_noise_supported": True,
        "maximum_guidance_gap_characters": 2700,
        "exact_guidance_support_preserved": True,
        "english_guidance_supported": True,
        "spanish_guidance_supported": True,
        "second_current_state_assertion_remains_blocked": True,
        "standalone_delivery_authorization_remains_blocked": True,
        "current_finality_gate_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_contains_unapproved_finality",
    "_remove_bounded_future_guidance",
    "install_future_approval_guidance_layout_v1",
]
