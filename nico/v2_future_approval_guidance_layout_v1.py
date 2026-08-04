from __future__ import annotations

import re
from typing import Any

VERSION = "nico.v2.future-approval-guidance-layout.v1.3"
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

# These terms are sufficiently specific to be forbidden anywhere after approved
# future guidance is removed. Generic phrases such as "final report" are not in
# this tuple because repository evidence can truthfully contain PR titles, source
# paths, function names, and remediation notes that use those words.
_FORBIDDEN_CURRENT_STATE_MARKERS = (
    "automated final",
    "final aprobado",
    "approved final",
    "client delivery authorized",
    "entrega al cliente autorizada",
)

# Generic final-report wording is rejected only when it is actually presented as
# a lifecycle/status assertion. This preserves the fail-closed boundary while no
# longer treating source evidence such as "Diagnose final report blocker" as an
# assertion that the automated draft is final.
_CURRENT_FINAL_REPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bfinal report\b.{0,220}?\bpending human approval\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bfinal report\b.{0,220}?\bclient delivery\b"
        r".{0,120}?\b(?:blocked|not authorized|authorized)\b",
        re.DOTALL,
    ),
    re.compile(
        r"\binforme final\b.{0,220}?\baprobacion humana pendiente\b",
        re.DOTALL,
    ),
    re.compile(
        r"\binforme final\b.{0,220}?\bentrega\b"
        r".{0,120}?\b(?:bloqueada|autorizada)\b",
        re.DOTALL,
    ),
    re.compile(
        r"\bcurrent(?: report)? (?:status|state|finality)\b"
        r".{0,120}?\bfinal report\b",
        re.DOTALL,
    ),
    re.compile(
        r"\b(?:report status|report state|report finality)\b"
        r".{0,120}?\bfinal\b",
        re.DOTALL,
    ),
    re.compile(
        r"\b(?:estado|finalidad) del informe\b"
        r".{0,120}?\binforme final\b",
        re.DOTALL,
    ),
)

_STANDALONE_FINAL_REPORT_LINE = re.compile(
    r"^(?:final report|informe final)(?:\s*(?:[|:·—-])\s*.*)?$"
)


def _remove_bounded_future_guidance(value: str) -> str:
    from nico import v2_automated_draft_quality_compat_v1 as target

    current = target._semantic(value)
    for guidance in target._AUTHORIZED_FUTURE_STATE_GUIDANCE:
        current = current.replace(target._semantic(guidance), " ")
    for pattern in _GUIDANCE_PATTERNS:
        current = pattern.sub(" ", current)
    return " ".join(current.split())


def _contains_standalone_final_report_line(value: str) -> bool:
    from nico import v2_automated_draft_quality_compat_v1 as target

    for raw_line in str(value or "").splitlines():
        line = target._semantic(raw_line).strip(" \t•*-—|:")
        if line and _STANDALONE_FINAL_REPORT_LINE.fullmatch(line):
            return True
    return False


def _contains_unapproved_finality(value: str) -> bool:
    current_state = _remove_bounded_future_guidance(value)
    if any(marker in current_state for marker in _FORBIDDEN_CURRENT_STATE_MARKERS):
        return True
    if any(pattern.search(current_state) for pattern in _CURRENT_FINAL_REPORT_PATTERNS):
        return True
    return _contains_standalone_final_report_line(value)


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
        "source_evidence_final_report_wording_allowed": True,
        "status_scoped_final_report_detection": True,
        "second_current_state_assertion_remains_blocked": True,
        "standalone_delivery_authorization_remains_blocked": True,
        "standalone_final_report_status_remains_blocked": True,
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
    "_contains_standalone_final_report_line",
    "_contains_unapproved_finality",
    "_remove_bounded_future_guidance",
    "install_future_approval_guidance_layout_v1",
]
