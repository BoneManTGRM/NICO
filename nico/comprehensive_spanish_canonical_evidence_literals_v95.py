from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-canonical-evidence-literals.v95"
_MARKER = "__nico_spanish_canonical_evidence_literals_v95__"

# A stage summary can flatten retained evidence into strings of the form
# ``machine.path: exact value``. The outer field is named ``evidence`` even when the
# original leaf is immutable machine/provenance data. Treating every flattened value
# as renderer-owned prose made es-MX publication fail on repository-specific PR titles,
# commit messages, and scanner truth-model metadata.
_SERIALIZED_EVIDENCE_RE = re.compile(
    r"^(?P<path>[A-Za-z0-9_.\[\]-]+):\s+(?P<value>.+)$",
    re.DOTALL,
)
_INDEX_RE = re.compile(r"\[\d+\]")

# v87 owns the authoritative presentation-field vocabulary. These additional rich
# finding fields are guarded by the v93 preflight even though they are not in v87's
# legacy strict set.
_ADDITIONAL_PRESENTATION_FIELDS = {
    "cost_of_inaction",
    "owner_role",
    "residual_risk",
    "technical_consequence",
    "technical_impact",
}

# ``title`` is normally presentation prose, but titles captured from remote repository
# history are exact source evidence. Keep the exemption bounded to provenance paths;
# report-owned titles and summaries still use the strict Spanish translator.
_EXACT_SOURCE_TITLE_PATH_TOKENS = (
    "pull_request",
    "pull_requests",
    "sample_pull_requests",
    "release",
    "releases",
)

_ORIGINAL_FIELD_TRANSLATOR: Callable[[str, str], str] | None = None


def _normalized_source_leaf(path: str) -> str:
    leaf = str(path or "").rsplit(".", 1)[-1]
    return _INDEX_RE.sub("", leaf).strip().casefold()


def _remote_exact_title_path(path: str) -> bool:
    normalized = str(path or "").casefold()
    if _normalized_source_leaf(normalized) != "title":
        return False
    return any(token in normalized for token in _EXACT_SOURCE_TITLE_PATH_TOKENS)


def serialized_canonical_evidence_literal(value: Any, key: Any) -> bool:
    """Return True only for flattened evidence whose original leaf is machine truth.

    Unknown report-owned presentation prose remains fail-closed. The decision is based
    on the original flattened source path, not on whether a string merely looks English,
    so arbitrary English prose cannot bypass localization by living under ``evidence``.
    """

    if str(key or "").strip().casefold() != "evidence":
        return False
    text = str(value or "")
    match = _SERIALIZED_EVIDENCE_RE.fullmatch(text.strip())
    if match is None:
        return False

    source_path = match.group("path")
    source_leaf = _normalized_source_leaf(source_path)
    if not source_leaf:
        return False

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    presentation_fields = {
        str(item).casefold() for item in canonical._PRESENTATION_PROSE_FIELDS
    } | _ADDITIONAL_PRESENTATION_FIELDS

    # If the original leaf was not presentation prose before stage-summary flattening,
    # it is canonical evidence and must remain byte-for-byte unchanged. This covers
    # commit_message and truth_model without enumerating repository-specific values.
    if source_leaf not in presentation_fields:
        return True

    # Captured pull-request/release titles are repository evidence even though ``title``
    # is also used by report-owned presentation objects elsewhere.
    if source_leaf == "title" and _remote_exact_title_path(source_path):
        return True

    return False


def install_comprehensive_spanish_canonical_evidence_literals_v95() -> dict[str, Any]:
    """Preserve flattened canonical evidence while retaining strict Spanish prose gates."""

    global _ORIGINAL_FIELD_TRANSLATOR

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    installer = getattr(v88, "install_comprehensive_spanish_exit_criteria_v88", None)
    if callable(installer):
        installer()

    current = getattr(v88, "_translate_canonical_field_v88", None)
    if not callable(current):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_canonical_field_translator_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    if getattr(current, _MARKER, False):
        field = current
    else:
        if _ORIGINAL_FIELD_TRANSLATOR is None:
            _ORIGINAL_FIELD_TRANSLATOR = current
        base = _ORIGINAL_FIELD_TRANSLATOR
        if base is None:
            raise RuntimeError("Spanish canonical evidence guard has no base translator")

        @wraps(base)
        def field(value: str, key: str) -> str:
            if serialized_canonical_evidence_literal(value, key):
                return str(value or "")
            return base(value, key)

        setattr(field, _MARKER, True)
        setattr(field, "_nico_previous", base)
        v88._translate_canonical_field_v88 = field

    # v88's call-time binder resolves its own global translator. Rebind through that
    # authority so detached workers cannot restore the unguarded alias later.
    binder = getattr(v88, "_bind_translation_surfaces", None)
    if callable(binder):
        binder()
    canonical._translate_presentation_field = v88._translate_canonical_field_v88

    bound = bool(
        getattr(v88._translate_canonical_field_v88, _MARKER, False)
        and canonical._translate_presentation_field
        is v88._translate_canonical_field_v88
    )
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "serialized_machine_evidence_preserved": True,
        "remote_repository_titles_preserved": True,
        "report_owned_presentation_prose_still_fail_closed": True,
        "canonical_evidence_byte_preserving": True,
        "score_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "english_report_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_canonical_evidence_literals_v95",
    "serialized_canonical_evidence_literal",
]
