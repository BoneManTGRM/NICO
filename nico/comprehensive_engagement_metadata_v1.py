from __future__ import annotations

import hashlib
import json
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


def _text(value: Any, limit: int) -> str:
    """Return one bounded client-supplied text value without list repr leakage."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            normalized = _text(item, limit)
            if normalized:
                return normalized
        return ""
    normalized = " ".join(str(value or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _find(value: Any, key: str, *, limit: int) -> str:
    if isinstance(value, Mapping):
        if key in value:
            direct = _text(value.get(key), limit)
            if direct:
                return direct
        for nested in value.values():
            result = _find(nested, key, limit=limit)
            if result:
                return result
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            result = _find(nested, key, limit=limit)
            if result:
                return result
    return ""


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
        "client_name": _text(client_name, 180),
        "project_name": _text(project_name, 180),
        "primary_technical_contact": _find(
            human_evidence,
            "primary_technical_contact",
            limit=600,
        ),
        "access_method": _find(human_evidence, "access_method", limit=1200),
        "authorized_scope": _find(human_evidence, "authorized_scope", limit=4000),
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
        "client_name": _text(source.get("client_name"), 180),
        "project_name": _text(source.get("project_name"), 180),
        "primary_technical_contact": _text(
            source.get("primary_technical_contact"),
            600,
        ),
        "access_method": _text(source.get("access_method"), 1200),
        "authorized_scope": _text(source.get("authorized_scope"), 4000),
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
    }


__all__ = [
    "VERSION",
    "build_comprehensive_engagement_metadata",
    "display_identity_projection",
    "normalize_comprehensive_engagement_metadata",
    "verify_comprehensive_engagement_metadata",
]
