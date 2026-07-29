from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico import v2_scanner_evidence_completion as completion

VERSION = "nico.v2.scanner-evidence-context-normalization.v1"
_MARKER = "__nico_v2_scanner_context_normalization_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _path_text(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("path", "file", "file_path", "manifest", "lockfile", "source"):
            if _text(value.get(key)):
                return _text(value.get(key))
        return ""
    return _text(value)


def normalized_package_context(value: Mapping[str, Any], inherited: Mapping[str, Any]) -> dict[str, Any]:
    context = deepcopy(dict(inherited))
    package = value.get("package")
    if isinstance(package, Mapping):
        if _text(package.get("name")):
            context["package"] = _text(package.get("name"))
        if _text(package.get("ecosystem")):
            context["ecosystem"] = _text(package.get("ecosystem"))
        if _text(package.get("version")):
            context["installed_version"] = _text(package.get("version"))
    elif _text(package):
        context["package"] = _text(package)

    for source, target in (
        ("name", "package"),
        ("version", "installed_version"),
        ("installed_version", "installed_version"),
        ("ecosystem", "ecosystem"),
    ):
        candidate = _text(value.get(source))
        if candidate and not _text(context.get(target)):
            context[target] = candidate
    for source in ("source", "path", "manifest", "lockfile"):
        candidate = _path_text(value.get(source))
        if candidate and not _text(context.get("dependency_path")):
            context["dependency_path"] = candidate
    return context


def install_v2_scanner_evidence_context_normalization() -> dict[str, Any]:
    current = completion._package_context
    if getattr(current, _MARKER, False):
        bound = current is normalized_package_context
        return {
            "status": "already_installed" if bound else "blocked",
            "version": VERSION,
            "bound": bound,
            "nested_source_path_normalized": bound,
            "nested_manifest_path_normalized": bound,
        }
    setattr(normalized_package_context, _MARKER, True)
    setattr(normalized_package_context, "_nico_previous", current)
    completion._package_context = normalized_package_context
    bound = completion._package_context is normalized_package_context
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "nested_source_path_normalized": bound,
        "nested_manifest_path_normalized": bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "normalized_package_context",
    "install_v2_scanner_evidence_context_normalization",
]
