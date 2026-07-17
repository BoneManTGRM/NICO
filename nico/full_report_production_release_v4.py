from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from nico.full_report_render_qa_v3 import attach_full_render_qa, validate_full_bilingual_parity

VERSION = "full_report_production_release_v4"
REQUIRED_FORMATS = ("pdf", "html", "markdown")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_full_release_manifest(
    report: dict[str, Any],
    *,
    pages: Iterable[Any],
    locale: str,
    exports: dict[str, Any],
    human_review_complete: bool = False,
) -> dict[str, Any]:
    """Bind Full QA to concrete exports without granting implicit approval."""

    result = attach_full_render_qa(
        deepcopy(report),
        pages,
        locale=locale,
        human_review_complete=human_review_complete,
    )
    qa = _dict(result.get("full_render_qa"))
    export_state: dict[str, dict[str, Any]] = {}
    issues = list(_list(qa.get("issues")))

    for name in REQUIRED_FORMATS:
        value = exports.get(name)
        present = value is not None and value != b"" and _text(value) != ""
        export_state[name] = {
            "present": present,
            "content_type": {
                "pdf": "application/pdf",
                "html": "text/html",
                "markdown": "text/markdown",
            }[name],
        }
        if not present:
            issues.append(f"Required Full export missing: {name}")

    delivery_allowed = not issues and human_review_complete
    manifest = {
        "version": VERSION,
        "report_tier": "full",
        "locale": qa.get("locale"),
        "page_count": qa.get("page_count"),
        "render_qa_status": "pass" if not issues else "fail",
        "issues": issues,
        "exports": export_state,
        "human_review_complete": human_review_complete,
        "human_review_required": not human_review_complete,
        "client_delivery_allowed": delivery_allowed,
        "release_state": "approved" if delivery_allowed else "blocked",
    }
    result["full_production_release"] = manifest
    result["client_delivery_allowed"] = delivery_allowed
    result["human_review_required"] = not human_review_complete
    return result


def build_bilingual_release_gate(english: dict[str, Any], spanish: dict[str, Any]) -> dict[str, Any]:
    """Require exact structural parity before either locale may be released."""

    parity_issues = list(validate_full_bilingual_parity(english, spanish))
    english_release = _dict(english.get("full_production_release"))
    spanish_release = _dict(spanish.get("full_production_release"))

    if english_release.get("release_state") != "approved":
        parity_issues.append("English Full release is not approved.")
    if spanish_release.get("release_state") != "approved":
        parity_issues.append("Spanish Full release is not approved.")

    allowed = not parity_issues
    return {
        "version": VERSION,
        "status": "pass" if allowed else "fail",
        "issues": parity_issues,
        "english_release_allowed": allowed,
        "spanish_release_allowed": allowed,
        "client_delivery_allowed": allowed,
    }


__all__ = [
    "REQUIRED_FORMATS",
    "VERSION",
    "build_bilingual_release_gate",
    "build_full_release_manifest",
]
