from __future__ import annotations

import re
from typing import Any

VERSION = "nico.v2.future-approval-guidance-layout.v1.2"
_MARKER = "__nico_future_approval_guidance_layout_v1__"

# PDF text extraction can place page headers, footers, and line fragments between
# words that were one sentence in the source document. These patterns are bounded
# and clause-anchored: they remove only the known explanatory future-state or
# negative-automation sentence through both required finality terms. They do not
# remove a later, independent current-state assertion.
_GUIDANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bonly an authorized reviewer\b.{0,900}?\bmay\b.{0,300}?\bchange\b"
        r".{0,300}?\bstatus\b.{0,900}?\bapproved\b.{0,300}?\bfinal\b"
        r".{0,900}?\band\b.{0,300}?\bclient\b.{0,300}?\bdelivery\b"
        r".{0,300}?\bauthorized\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bautomation cannot\b.{0,900}?\bchange\b.{0,300}?\bpackage\b"
        r".{0,900}?\bapproved\b.{0,300}?\bfinal\b.{0,900}?\bor\b"
        r".{0,300}?\bclient\b.{0,300}?\bdelivery\b.{0,300}?\bauthorized\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bsolo un revisor autorizado\b.{0,900}?\bpuede\b.{0,300}?\bcambiar\b"
        r".{0,300}?\bestado\b.{0,900}?\bfinal\b.{0,300}?\baprobado\b"
        r".{0,900}?\by\b.{0,300}?\bentrega\b.{0,300}?\bal cliente\b"
        r".{0,300}?\bautorizada\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bla automatizacion no puede\b.{0,900}?\bcambiar\b"
        r".{0,300}?\beste paquete\b.{0,900}?\bfinal\b.{0,300}?\baprobado\b"
        r".{0,900}?\bni\b.{0,300}?\bentrega\b.{0,300}?\bal cliente\b"
        r".{0,300}?\bautorizada\b",
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


def _contract(*, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "version": VERSION,
        "bounded_layout_noise_supported": True,
        "token_level_layout_noise_supported": True,
        "maximum_clause_gap_characters": 900,
        "maximum_token_gap_characters": 300,
        "exact_guidance_support_preserved": True,
        "english_guidance_supported": True,
        "spanish_guidance_supported": True,
        "second_current_state_assertion_remains_blocked": True,
        "standalone_delivery_authorization_remains_blocked": True,
        "current_finality_gate_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_future_approval_guidance_layout_v1() -> dict[str, Any]:
    from nico import v2_automated_draft_quality_compat_v1 as target

    target.install_automated_draft_quality_compat()
    current = target._current_state_finality_scope
    if getattr(current, _MARKER, False):
        return _contract(status="already_installed")

    setattr(_remove_bounded_future_guidance, _MARKER, True)
    setattr(_remove_bounded_future_guidance, "_nico_previous", current)
    target._current_state_finality_scope = _remove_bounded_future_guidance
    target._contains_unapproved_finality = _contains_unapproved_finality
    return _contract(status="installed")


__all__ = [
    "VERSION",
    "_contains_unapproved_finality",
    "_remove_bounded_future_guidance",
    "install_future_approval_guidance_layout_v1",
]
