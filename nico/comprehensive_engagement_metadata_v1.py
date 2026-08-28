from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_engagement_metadata.v1"
_FIELDS = (
    "client_name",
    "project_name",
    "primary_technical_contact",
    "access_method",
    "authorized_scope",
)
_LINE_BREAK_RE = re.compile(r"\r\n|[\r\n\v\f\x85\u2028\u2029]")


def _literal(value: Any, limit: int) -> str:
    """Return one bounded client literal without rewriting visible user intent."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            literal = _literal(item, limit)
            if literal:
                return literal
        return ""
    literal = "" if value is None else str(value)
    if not literal.strip():
        return ""
    if len(literal) > limit:
        raise ValueError(f"engagement_metadata_value_exceeds_{limit}_characters")
    return literal


def markdown_literal_markup(value: Any, limit: int) -> str:
    """Encode one exact client literal as inert, visibly faithful Markdown HTML."""

    literal = _literal(value, limit)
    escaped = html.escape(literal, quote=False)
    rendered = _LINE_BREAK_RE.sub("<br/>", escaped)
    return f'<span data-nico-client-literal="true">{rendered}</span>'


def reportlab_literal_markup(value: Any, limit: int) -> str:
    """Escape one client literal while preserving visible U+0020 space runs."""

    literal = _literal(value, limit)
    lines = _LINE_BREAK_RE.split(literal)

    def render_line(line: str) -> str:
        pieces: list[str] = []
        cursor = 0
        for match in re.finditer(r" +", line):
            pieces.append(html.escape(line[cursor : match.start()]))
            count = len(match.group(0))
            at_boundary = match.start() == 0 or match.end() == len(line)
            if at_boundary:
                pieces.append("&nbsp;" * count)
            elif count == 1:
                pieces.append(" ")
            else:
                # Retain one ordinary break opportunity without losing the run.
                pieces.append("&nbsp;" * (count - 1) + " ")
            cursor = match.end()
        pieces.append(html.escape(line[cursor:]))
        return "".join(pieces)

    return "<br/>".join(render_line(line) for line in lines)


def _stakeholder_context_evidence(value: Any) -> Mapping[str, Any]:
    """Return only the canonical stakeholder-context evidence namespace."""

    if not isinstance(value, Mapping):
        return {}
    source = value
    module: Any = source.get("stakeholder_context")
    modules = source.get("modules")
    if isinstance(modules, Mapping):
        module = modules.get("stakeholder_context")
    elif isinstance(modules, Sequence) and not isinstance(
        modules,
        (str, bytes, bytearray),
    ):
        module = next(
            (
                item
                for item in modules
                if isinstance(item, Mapping)
                and str(item.get("module_id") or "") == "stakeholder_context"
            ),
            None,
        )
    elif str(source.get("module_id") or "") == "stakeholder_context":
        module = source
    if not isinstance(module, Mapping):
        return {}
    evidence = module.get("evidence")
    return evidence if isinstance(evidence, Mapping) else {}


def _engagement_evidence_literal(value: Any, key: str, *, limit: int) -> str:
    return _literal(_stakeholder_context_evidence(value).get(key), limit)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_comprehensive_engagement_metadata(
    *,
    client_name: Any = "",
    project_name: Any = "",
    human_evidence: Any = None,
) -> dict[str, Any]:
    """Normalize the user-supplied engagement display/context snapshot once.

    This object is descriptive engagement metadata. It never replaces customer_id,
    project_id, workspace/run identity, repository identity, or immutable commit truth.
    Missing values remain empty and are never inferred from repository metadata.
    """

    payload = {
        "artifact_schema": VERSION,
        "client_name": _literal(client_name, 180),
        "project_name": _literal(project_name, 180),
        "primary_technical_contact": _engagement_evidence_literal(
            human_evidence,
            "primary_technical_contact",
            limit=600,
        ),
        "access_method": _engagement_evidence_literal(
            human_evidence,
            "access_method",
            limit=1200,
        ),
        "authorized_scope": _engagement_evidence_literal(
            human_evidence,
            "authorized_scope",
            limit=4000,
        ),
        "source": "client_supplied_intake",
        "repository_inference_prohibited": True,
        "directly_scored": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    payload["engagement_metadata_sha256"] = _canonical_hash(payload)
    return payload


def normalize_comprehensive_engagement_metadata(value: Any) -> dict[str, Any]:
    """Validate/copy an already-normalized snapshot without reconstructing facts."""

    if not isinstance(value, Mapping):
        return {}
    source = deepcopy(dict(value))
    if str(source.get("artifact_schema") or "") != VERSION:
        return {}
    normalized = {
        "artifact_schema": VERSION,
        "client_name": _literal(source.get("client_name"), 180),
        "project_name": _literal(source.get("project_name"), 180),
        "primary_technical_contact": _literal(
            source.get("primary_technical_contact"),
            600,
        ),
        "access_method": _literal(source.get("access_method"), 1200),
        "authorized_scope": _literal(source.get("authorized_scope"), 4000),
        "source": "client_supplied_intake",
        "repository_inference_prohibited": True,
        "directly_scored": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    normalized["engagement_metadata_sha256"] = _canonical_hash(normalized)
    return normalized


def verify_comprehensive_engagement_metadata(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    candidate = dict(value)
    claimed = str(candidate.pop("engagement_metadata_sha256", "") or "")
    if not claimed or claimed != _canonical_hash(candidate):
        return False
    normalized = normalize_comprehensive_engagement_metadata(value)
    return bool(normalized and normalized == dict(value))


def display_identity_projection(value: Any) -> dict[str, str]:
    normalized = normalize_comprehensive_engagement_metadata(value)
    if not normalized:
        return {}
    return {
        "customer_name": str(normalized.get("client_name") or ""),
        "project_name": str(normalized.get("project_name") or ""),
        "primary_technical_contact": str(
            normalized.get("primary_technical_contact") or ""
        ),
        "access_method": str(normalized.get("access_method") or ""),
        "authorized_scope": str(normalized.get("authorized_scope") or ""),
    }


__all__ = [
    "VERSION",
    "build_comprehensive_engagement_metadata",
    "display_identity_projection",
    "markdown_literal_markup",
    "normalize_comprehensive_engagement_metadata",
    "reportlab_literal_markup",
    "verify_comprehensive_engagement_metadata",
]
